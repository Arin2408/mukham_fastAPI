"""
Sends the shift reminders that are due, and checks Expo's delivery receipts.

Run every 5 minutes (each reminder is sent once, however often this runs):
    python -m scripts.send_notifications            # once, e.g. from cron
    python -m scripts.send_notifications --every 300   # keep running, for development

Cron example (from fastapi_backend/):
    */5 * * * * cd /path/to/fastapi_backend && ../.venv/bin/python -m scripts.send_notifications
"""

import argparse
import logging
import time

from app.db.session import SessionLocal
from app.services.notification_service import send_due_reminders


def run_once() -> int:
    db = SessionLocal()
    try:
        return send_due_reminders(db)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--every", type=int, default=0, help="seconds between runs; 0 = run once")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        sent = run_once()
        logging.info("Reminders sent: %s", sent)
        if not args.every:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
