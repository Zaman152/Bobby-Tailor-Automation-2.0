"""
Entry point. Run once or on a schedule.

Usage:
  python main.py                         # Run once for all projects
  python main.py --project-id 7409312    # Run once for a specific project
  python main.py --schedule              # Run on cron schedule (RUN_SCHEDULE in .env)
"""
import asyncio
import argparse
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from scraper import run_all_projects, run_project_scrape
from config import RUN_SCHEDULE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("output/run.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)


async def scheduled_job():
    logger.info("Scheduled run triggered")
    await run_all_projects()


async def main():
    parser = argparse.ArgumentParser(description="StackCT Automated Estimation Scraper")
    parser.add_argument("--project-id", type=int, help="Run for a specific project ID")
    parser.add_argument("--project-name", type=str, default="Project", help="Project name label")
    parser.add_argument("--schedule", action="store_true", help="Run on schedule")
    args = parser.parse_args()

    import os
    os.makedirs("output", exist_ok=True)

    if args.schedule:
        logger.info(f"Starting scheduler with cron: {RUN_SCHEDULE}")
        scheduler = AsyncIOScheduler()
        scheduler.add_job(scheduled_job, CronTrigger.from_crontab(RUN_SCHEDULE))
        scheduler.start()
        logger.info("Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down scheduler")
            scheduler.shutdown()

    elif args.project_id:
        await run_project_scrape(args.project_id, args.project_name)

    else:
        await run_all_projects()


if __name__ == "__main__":
    asyncio.run(main())
