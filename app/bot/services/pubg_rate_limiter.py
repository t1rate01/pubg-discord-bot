import logging
import time

from app.db.models import get_runtime_config

logger = logging.getLogger("pubg_rate_limiter")


class PubgRateLimiter:
    def __init__(self):
        self.remote_limit: int | None = None
        self.remote_remaining: int | None = None
        self.remote_reset_epoch: int | None = None

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _window_seconds(self) -> int:
        return int(get_runtime_config()["pubg_rate_limit_window_seconds"])

    def wait_if_needed(self):
        now = time.time()

        if (
            self.remote_remaining is not None
            and self.remote_remaining <= 0
            and self.remote_reset_epoch is not None
            and now < self.remote_reset_epoch
        ):
            sleep_seconds = max(0.0, self.remote_reset_epoch - now + 0.25)
            logger.info("PUBG rate limit exhausted, waiting %.2fs until reset", sleep_seconds)
            time.sleep(sleep_seconds)

            self.remote_remaining = None
            self.remote_reset_epoch = None

    def update_from_response(self, response):
        limit = self._safe_int(response.headers.get("X-RateLimit-Limit"))
        remaining = self._safe_int(response.headers.get("X-RateLimit-Remaining"))
        reset_epoch = self._safe_int(response.headers.get("X-RateLimit-Reset"))

        if limit is not None:
            self.remote_limit = limit
        if remaining is not None:
            self.remote_remaining = remaining
        if reset_epoch is not None:
            self.remote_reset_epoch = reset_epoch

        if limit is not None or remaining is not None or reset_epoch is not None:
            logger.info(
                "PUBG rate headers limit=%s remaining=%s reset=%s",
                self.remote_limit,
                self.remote_remaining,
                self.remote_reset_epoch,
            )

    def handle_429_and_wait(self, response):
        self.update_from_response(response)

        now = time.time()

        if self.remote_reset_epoch is not None and now < self.remote_reset_epoch:
            sleep_seconds = max(0.0, self.remote_reset_epoch - now + 0.25)
        else:
            sleep_seconds = float(self._window_seconds())

        logger.warning("PUBG returned 429, sleeping %.2fs before retry", sleep_seconds)
        time.sleep(sleep_seconds)

        self.remote_remaining = None
        self.remote_reset_epoch = None