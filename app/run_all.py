import asyncio
import logging
import threading
import uvicorn

from app.core.logging import setup_logging
from app.core.settings_service import system_state
from app.db.models import get_service_control_state
from app.bot.main import build_bot_from_db
from app.worker.main import build_worker

setup_logging()
logger = logging.getLogger("run_all")


def start_web():
    uvicorn.run(
        "app.web.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


async def supervisor_loop():
    bot_task = None
    worker_task = None
    bot_client = None

    last_bot_generation = None
    last_worker_generation = None

    while True:
        try:
            state = system_state()
            control = get_service_control_state()

            runtime_ready = state["runtime_config_complete"]

            desired_bot = runtime_ready and control["bot_enabled"]
            desired_worker = runtime_ready and control["worker_enabled"]

            bot_generation = control["bot_generation"]
            worker_generation = control["worker_generation"]

            if desired_bot:
                if bot_task is None or bot_task.done() or last_bot_generation != bot_generation:
                    if bot_task and not bot_task.done():
                        logger.info("Stopping bot due to restart request/config change")
                        bot_task.cancel()
                        try:
                            await bot_task
                        except Exception:
                            pass

                    bot_client, token = build_bot_from_db()
                    bot_task = asyncio.create_task(bot_client.start(token))
                    last_bot_generation = bot_generation
                    logger.info(f"Bot started (generation {bot_generation})")
            else:
                if bot_task and not bot_task.done():
                    logger.info("Stopping bot because it is disabled or config is incomplete")
                    bot_task.cancel()
                    try:
                        await bot_task
                    except Exception:
                        pass
                    bot_task = None
                    bot_client = None

            if desired_worker:
                if worker_task is None or worker_task.done() or last_worker_generation != worker_generation:
                    if worker_task and not worker_task.done():
                        logger.info("Stopping worker due to restart request/config change")
                        worker_task.cancel()
                        try:
                            await worker_task
                        except Exception:
                            pass

                    worker = build_worker(bot_client=bot_client)
                    worker_task = asyncio.create_task(worker.start())
                    last_worker_generation = worker_generation
                    logger.info(f"Worker started (generation {worker_generation})")
            else:
                if worker_task and not worker_task.done():
                    logger.info("Stopping worker because it is disabled or config is incomplete")
                    worker_task.cancel()
                    try:
                        await worker_task
                    except Exception:
                        pass
                    worker_task = None

            if bot_task and bot_task.done():
                try:
                    exc = bot_task.exception()
                    if exc:
                        logger.exception("Bot task crashed", exc_info=exc)
                except Exception:
                    pass
                bot_task = None

            if worker_task and worker_task.done():
                try:
                    exc = worker_task.exception()
                    if exc:
                        logger.exception("Worker task crashed", exc_info=exc)
                except Exception:
                    pass
                worker_task = None

        except Exception:
            logger.exception("Supervisor loop error")

        await asyncio.sleep(3)


if __name__ == "__main__":
    web_thread = threading.Thread(target=start_web, daemon=True)
    web_thread.start()

    asyncio.run(supervisor_loop())