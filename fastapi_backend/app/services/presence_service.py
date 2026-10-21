"""
Out-of-office time during a shift, from the phone's background geofence.

After check-in the app asks for the office area (presence_region) and has
Android watch it. Each time the phone leaves or comes back, the app sends
the event with the time it happened (record_presence), even if that is later,
after a signal gap. The admin sees each day's time outside (summarize).

"on" / "off" record whether tracking could run at all: an employee who
refuses location "Allow all the time" shows as tracking off, not as
never having left.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.presence import PresenceEvent


EVENTS = ("exit", "enter", "on", "off")

# A phone clock running a little fast is fine; a time further ahead is not
# believed and is taken as "now".
CLOCK_SKEW = timedelta(minutes=2)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _open_attendance(db: Session, employee: Employee) -> Attendance | None:
    return (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.user_id,
            Attendance.check_out.is_(None),
        )
        .order_by(Attendance.check_in.desc())
        .first()
    )


def presence_region(db: Session, employee: Employee) -> dict | None:
    """The office area to watch, while the employee is checked in at one."""
    attendance = _open_attendance(db, employee)
    if attendance is None or attendance.check_in_location is None:
        return None

    office = attendance.check_in_location
    return {
        "attendance_id": attendance.id,
        "latitude": float(office.latitude),
        "longitude": float(office.longitude),
        "radius_meters": office.radius_meters,
    }


def record_presence(
    db: Session,
    employee: Employee,
    event: str,
    occurred_at: datetime,
    now: datetime | None = None,
) -> bool:
    """
    Store one event for the open check-in. False (nothing stored) when there
    is no open check-in, or the event repeats the last one of its kind
    (Android can report the same exit twice).
    """
    if event not in EVENTS:
        raise ValueError("Invalid presence event.")

    attendance = _open_attendance(db, employee)
    if attendance is None:
        return False

    now = now or datetime.now(timezone.utc)
    occurred_at = _aware(occurred_at)
    if occurred_at > now + CLOCK_SKEW:
        occurred_at = now
    occurred_at = max(occurred_at, _aware(attendance.check_in))

    pair = ("exit", "enter") if event in ("exit", "enter") else ("on", "off")
    last = next(
        (e for e in reversed(attendance.presence_events) if e.event in pair),
        None,
    )
    if last is not None and last.event == event:
        return False
    # The first movement can only be leaving: the check-in was inside.
    if last is None and event == "enter":
        return False

    db.add(
        PresenceEvent(
            attendance_id=attendance.id,
            event=event,
            occurred_at=occurred_at,
            received_at=now,
        )
    )
    db.commit()
    return True


def summarize(attendance: Attendance, now: datetime | None = None) -> dict:
    """
    time_outside_minutes: total of each exit until the next enter (or the
    check-out, or now while still out). presence_tracking: "on" / "off" as
    last reported, None for check-ins without the app's tracking.
    """
    events = attendance.presence_events
    tracking = next(
        (e.event for e in reversed(events) if e.event in ("on", "off")),
        None,
    )
    moves = [e for e in events if e.event in ("exit", "enter")]

    if tracking is None and not moves:
        return {
            "presence_tracking": None,
            "time_outside_minutes": None,
            "presence_events": [],
        }

    end = _aware(attendance.check_out) if attendance.check_out else _aware(now or datetime.now(timezone.utc))
    outside = timedelta()
    left_at = None
    for e in moves:
        at = _aware(e.occurred_at)
        if e.event == "exit" and left_at is None:
            left_at = at
        elif e.event == "enter" and left_at is not None:
            outside += max(at - left_at, timedelta())
            left_at = None
    if left_at is not None:
        outside += max(end - left_at, timedelta())

    return {
        "presence_tracking": tracking or "on",
        "time_outside_minutes": round(outside.total_seconds() / 60),
        "presence_events": [
            {"event": e.event, "at": e.occurred_at} for e in moves
        ],
    }
