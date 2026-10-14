"""
Who gets which notification, and when.

- "Your shift starts soon": SHIFT_REMINDER_MINUTES before shift start, to an
  employee who hasn't checked in for that shift.
- "You're still checked in": CHECKOUT_REMINDER_MINUTES after shift end, to an
  employee whose check-in is still open.
- "New task: …": when an admin assigns a task.

Each reminder is recorded in notifications_sent, so the job can run as often
as it likes (every 5 minutes is the plan) without sending one twice.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.notification import NotificationPreference, NotificationSent, PushDevice
from app.models.user import User
from app.services import push_service
from app.services.attendance_service import LOCAL_TZ

KINDS = ("shift_start", "check_out", "new_task")
# A check-out reminder for a shift that ended long ago is no longer useful.
STALE_AFTER = timedelta(hours=12)
# Any check-in this long before a shift starts counts as being in for it.
EARLY_CHECK_IN = timedelta(hours=12)


# ---------------------------------------------------------------- devices

def register_device(db: Session, user_id: int, token: str, platform: str) -> None:
    """Saves this phone's token for the signed-in person (moving it if someone else used the phone)."""
    device = db.query(PushDevice).filter(PushDevice.token == token).first()
    if device is None:
        db.add(PushDevice(user_id=user_id, token=token, platform=platform))
    else:
        device.user_id = user_id
        device.platform = platform
        device.last_seen_at = datetime.now(LOCAL_TZ)
    db.commit()


def unregister_device(db: Session, user_id: int, token: str) -> None:
    """At sign-out: the phone gets nothing more for this person."""
    db.query(PushDevice).filter(PushDevice.token == token, PushDevice.user_id == user_id).delete(
        synchronize_session=False
    )
    db.commit()


# ---------------------------------------------------------------- preferences

def get_preferences(db: Session, user_id: int) -> dict:
    pref = db.get(NotificationPreference, user_id)
    return {kind: (getattr(pref, kind) if pref else True) for kind in KINDS}


def set_preferences(db: Session, user_id: int, values: dict) -> dict:
    pref = db.get(NotificationPreference, user_id)
    if pref is None:
        pref = NotificationPreference(user_id=user_id, shift_start=True, check_out=True, new_task=True)
        db.add(pref)
    for kind in KINDS:
        if values.get(kind) is not None:
            setattr(pref, kind, bool(values[kind]))
    db.commit()
    return get_preferences(db, user_id)


# ---------------------------------------------------------------- sending

def _wants(db: Session, user_id: int, kind: str) -> bool:
    return get_preferences(db, user_id)[kind]


def _messages(db: Session, user_id: int, title: str, body: str, data: dict) -> list[dict]:
    tokens = [d.token for d in db.query(PushDevice).filter(PushDevice.user_id == user_id)]
    return [
        {"to": token, "title": title, "body": body, "data": data, "sound": "default", "channelId": "reminders"}
        for token in tokens
    ]


def _claim(db: Session, user_id: int, kind: str, ref: str) -> bool:
    """Records the reminder as sent; False if it already was (another run got there first)."""
    db.add(NotificationSent(user_id=user_id, kind=kind, ref=ref))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def notify_new_task(db: Session, employee_id: int, task_id: int, title: str) -> int:
    """Called right after an admin assigns a task."""
    if not _wants(db, employee_id, "new_task"):
        return 0
    messages = _messages(db, employee_id, f"New task: {title}", "Tap to open it.", {"url": f"/task/{task_id}"})
    return push_service.send(db, messages)


def _shift_start_after(now: datetime, start: time) -> datetime:
    """The next start of a shift at `start`, from `now` (today's, or tomorrow's if it has passed)."""
    today = datetime.combine(now.date(), start, tzinfo=LOCAL_TZ)
    return today if today > now else today + timedelta(days=1)


def _shift_end_for(check_in: datetime, start: time, end: time) -> datetime:
    """When the shift that `check_in` belongs to ends (overnight shifts end the next day)."""
    local = check_in.astimezone(LOCAL_TZ)
    shift_day: date = local.date()
    # Checked in just after midnight for a shift that started the evening before.
    if end < start and local.time() < end:
        shift_day -= timedelta(days=1)
    starts = datetime.combine(shift_day, start, tzinfo=LOCAL_TZ)
    ends = datetime.combine(shift_day, end, tzinfo=LOCAL_TZ)
    if ends <= starts:
        ends += timedelta(days=1)
    return ends


def due_reminders(db: Session, now: datetime) -> list[tuple[int, str, str, str, str]]:
    """
    Reminders due at `now`, as (user_id, kind, ref, title, body). Only for
    active employees with a shift and at least one registered phone.
    """
    now = now.astimezone(LOCAL_TZ)
    with_phones = {d.user_id for d in db.query(PushDevice.user_id).distinct()}
    if not with_phones:
        return []

    employees = (
        db.query(Employee)
        .join(User, User.org_id == Employee.user_id)
        .filter(Employee.user_id.in_(with_phones), Employee.shift_id.isnot(None), User.is_active.is_(True))
        .all()
    )
    before = timedelta(minutes=settings.shift_reminder_minutes)
    after = timedelta(minutes=settings.checkout_reminder_minutes)
    due = []

    for employee in employees:
        shift = employee.shift
        if shift is None:
            continue
        open_record = (
            db.query(Attendance)
            .filter(Attendance.employee_id == employee.user_id, Attendance.check_out.is_(None))
            .order_by(Attendance.check_in.desc())
            .first()
        )

        # Shift starting soon, and not checked in for it.
        starts = _shift_start_after(now, shift.shift_start_time)
        if starts - now <= before and open_record is None:
            already_in = (
                db.query(Attendance.id)
                .filter(Attendance.employee_id == employee.user_id, Attendance.check_in >= starts - EARLY_CHECK_IN)
                .first()
            )
            if already_in is None:
                due.append((
                    employee.user_id,
                    "shift_start",
                    starts.date().isoformat(),
                    "Your shift starts soon",
                    f"{shift.shift_name} starts at {shift.shift_start_time.strftime('%H:%M')}. Check in when you arrive.",
                ))

        # Still checked in well after the shift ended.
        if open_record is not None:
            ends = _shift_end_for(open_record.check_in, shift.shift_start_time, shift.shift_end_time)
            if ends + after <= now < ends + after + STALE_AFTER:
                due.append((
                    employee.user_id,
                    "check_out",
                    str(open_record.id),
                    "You're still checked in",
                    f"Your shift ended at {shift.shift_end_time.strftime('%H:%M')}. Check out if you've left.",
                ))
    return due


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    """The job: sends what is due, once each. Returns how many messages Expo accepted."""
    if not settings.notifications_enabled:
        return 0
    now = now or datetime.now(LOCAL_TZ)
    sent = 0
    for user_id, kind, ref, title, body in due_reminders(db, now):
        if not _wants(db, user_id, kind):
            continue
        if not _claim(db, user_id, kind, ref):
            continue
        sent += push_service.send(db, _messages(db, user_id, title, body, {"url": "/"}))
    push_service.check_receipts(db)
    return sent
