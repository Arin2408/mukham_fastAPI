"""
Sending through Expo's push service, which delivers to Android (Firebase)
and iPhone (Apple). See docs.expo.dev/push-notifications/sending-notifications:
up to 100 messages a request; each answer is a "ticket"; about 15 minutes
later the ticket's "receipt" says whether it was delivered. A token Expo
reports as DeviceNotRegistered (app uninstalled) is removed.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import PushDevice, PushTicket


log = logging.getLogger(__name__)

BATCH = 100
RECEIPT_BATCH = 1000
RECEIPT_AFTER = timedelta(minutes=15)
RECEIPTS_EXPIRE = timedelta(hours=24)


def _headers() -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"
    return headers


def _post(url: str, payload) -> dict | None:
    """POST with up to 3 tries on rate limits and server errors."""
    for attempt in range(3):
        try:
            response = httpx.post(url, json=payload, headers=_headers(), timeout=15)
        except httpx.HTTPError as exc:
            log.warning("Expo push request failed: %s", exc)
        else:
            if response.status_code == 429 or response.status_code >= 500:
                log.warning("Expo push service answered %s", response.status_code)
            elif response.status_code >= 400:
                log.error("Expo push refused the request (%s): %s", response.status_code, response.text[:300])
                return None
            else:
                return response.json()
        time.sleep(2 ** attempt)
    return None


def _forget(db: Session, tokens: set[str]) -> None:
    if tokens:
        db.query(PushDevice).filter(PushDevice.token.in_(tokens)).delete(synchronize_session=False)


def send(db: Session, messages: list[dict]) -> tuple[int, bool]:
    """
    Sends Expo messages ({"to": token, "title", "body", "data", ...}).
    Returns how many Expo accepted, and whether Expo answered at all: False
    means no batch got through (network down, Expo failing), so the same
    messages can be tried again later without anyone getting them twice.
    Commits ticket and device changes.
    """
    if not settings.notifications_enabled or not messages:
        return 0, True

    accepted = 0
    reached = False
    dead: set[str] = set()
    for start in range(0, len(messages), BATCH):
        batch = messages[start : start + BATCH]
        answer = _post(settings.expo_push_url, batch)
        if answer is None:
            continue
        reached = True
        for message, ticket in zip(batch, answer.get("data", [])):
            if ticket.get("status") == "ok" and ticket.get("id"):
                accepted += 1
                db.merge(PushTicket(id=ticket["id"], token=message["to"]))
            elif (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                dead.add(message["to"])
            else:
                log.warning("Expo push ticket error: %s", ticket.get("message"))
    _forget(db, dead)
    db.commit()
    return accepted, reached


def check_receipts(db: Session, now: datetime | None = None) -> int:
    """Reads receipts for tickets older than 15 minutes; removes tokens of uninstalled apps."""
    now = now or datetime.now(timezone.utc)
    db.query(PushTicket).filter(PushTicket.created_at < now - RECEIPTS_EXPIRE).delete(synchronize_session=False)
    due = db.query(PushTicket).filter(PushTicket.created_at <= now - RECEIPT_AFTER).limit(RECEIPT_BATCH).all()
    if not due:
        db.commit()
        return 0

    answer = _post(settings.expo_receipts_url, {"ids": [t.id for t in due]})
    if answer is None:
        db.commit()
        return 0

    receipts = answer.get("data", {})
    dead = {
        t.token
        for t in due
        if ((receipts.get(t.id) or {}).get("details") or {}).get("error") == "DeviceNotRegistered"
    }
    _forget(db, dead)
    # Checked tickets (and any Expo no longer knows) are done with.
    db.query(PushTicket).filter(PushTicket.id.in_([t.id for t in due])).delete(synchronize_session=False)
    db.commit()
    return len(dead)
