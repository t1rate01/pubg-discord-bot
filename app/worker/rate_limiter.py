import time


class PubgRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        self.remote_limit: int | None = None
        self.remote_remaining: int | None = None
        self.remote_reset_epoch: int | None = None

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def wait_if_needed(self):
        now = time.time()

        if (
            self.remote_remaining is not None
            and self.remote_remaining <= 0
            and self.remote_reset_epoch is not None
            and now < self.remote_reset_epoch
        ):
            sleep_seconds = max(0.0, self.remote_reset_epoch - now + 0.25)
            print(f"⏳ PUBG rate limit exhausted, waiting {sleep_seconds:.2f}s until reset")
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
            print(
                "📊 PUBG rate limit headers: "
                f"limit={self.remote_limit} "
                f"remaining={self.remote_remaining} "
                f"reset={self.remote_reset_epoch}"
            )

    def handle_429_and_wait(self, response):
        self.update_from_response(response)

        now = time.time()

        if self.remote_reset_epoch is not None and now < self.remote_reset_epoch:
            sleep_seconds = max(0.0, self.remote_reset_epoch - now + 0.25)
        else:
            sleep_seconds = float(self.window_seconds)

        print(f"🚦 PUBG returned 429, sleeping {sleep_seconds:.2f}s before retry")
        time.sleep(sleep_seconds)

        self.remote_remaining = None
        self.remote_reset_epoch = None