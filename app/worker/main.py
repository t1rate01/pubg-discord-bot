import logging

from app.worker.job_worker import JobWorker

logger = logging.getLogger("worker_main")


def build_worker(bot_client=None) -> JobWorker:
    logger.info("Building job worker")
    return JobWorker(bot_client=bot_client)