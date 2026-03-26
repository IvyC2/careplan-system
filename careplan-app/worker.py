import logging
import os
import time

import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "careplan_project.settings")
django.setup()

from careplan_app.queue import process_one_careplan_task  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_worker() -> None:
    logger.info("Worker started.")
    while True:
        processed = process_one_careplan_task()
        if not processed:
            logger.info("No task in queue. Sleeping for 5 seconds.")
            time.sleep(5)


if __name__ == "__main__":
    run_worker()
