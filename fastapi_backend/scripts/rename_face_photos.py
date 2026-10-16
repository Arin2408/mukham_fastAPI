"""
Give face photos saved under the old fixed name (employee_photos/face_<mobile>.jpg)
a new random name, as new photos get (face_service.sync_employee_photo).

The fixed name was reused when someone with the same mobile number registered
again, so phones and browsers kept showing the old picture from their cache.
After this, each photo has its own address and the apps load the right one.

Safe to run more than once. Run from fastapi_backend/:

    python -m scripts.rename_face_photos --dry-run
    python -m scripts.rename_face_photos
"""
import argparse
import re
import secrets

from app.db.session import SessionLocal
from app.models.employee import Employee
from app.services.storage import media_store


OLD_NAME = re.compile(r"^employee_photos/face_(\d+)\.jpg$")


def rename(dry_run: bool) -> int:
    db = SessionLocal()
    renamed = 0
    try:
        for employee in db.query(Employee).filter(Employee.photo.isnot(None)).all():
            match = OLD_NAME.match(employee.photo)
            if not match:
                continue

            old = employee.photo
            new = f"employee_photos/face_{match.group(1)}_{secrets.token_hex(8)}.jpg"
            print(f"employee {employee.user_id}: {old} -> {new}")
            if dry_run:
                renamed += 1
                continue

            data = media_store.read(old)
            if data is None:
                print("  file missing; left as it is")
                continue
            media_store.save(new, data, "image/jpeg")
            employee.photo = new
            db.commit()
            media_store.delete(old)
            renamed += 1
    finally:
        db.close()
    return renamed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="only list what would change")
    args = parser.parse_args()
    count = rename(args.dry_run)
    print(f"{'Would rename' if args.dry_run else 'Renamed'} {count} photo(s).")


if __name__ == "__main__":
    main()
