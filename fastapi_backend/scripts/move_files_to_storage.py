"""
Move stored files into the configured storage (app/services/storage.py).

1. Face images still kept as base64 in face_auth_employeefacedata are
   written to face_store, and the base64 column is emptied.
2. When MEDIA_S3_BUCKET is set, files already on local disk are uploaded:
   MEDIA_ROOT -> s3://<bucket>/media/, PRIVATE_MEDIA_ROOT -> .../faces/.
   Local files are left in place; delete them once the upload is checked.

Safe to run more than once. Run from fastapi_backend/:

    python -m scripts.move_files_to_storage --dry-run
    python -m scripts.move_files_to_storage
"""
import argparse
import base64
import mimetypes
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.face import EmployeeFaceData
from app.services.face_service import store_face_image
from app.services.storage import face_store, media_store, uses_s3


def move_database_faces(dry_run: bool) -> int:
    db = SessionLocal()
    moved = 0
    try:
        records = (
            db.query(EmployeeFaceData)
            .filter(
                EmployeeFaceData.face_image_key == "",
                EmployeeFaceData.face_image_base64 != "",
            )
            .all()
        )
        for record in records:
            print(f"face {record.mobile_number}: database -> face store")
            if not dry_run:
                image_bytes = base64.b64decode(record.face_image_base64)
                store_face_image(record, record.mobile_number, image_bytes)
                db.commit()
            moved += 1
    finally:
        db.close()
    return moved


def upload_folder(root: Path, store, label: str, dry_run: bool) -> int:
    if not root.is_dir():
        return 0
    uploaded = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        key = path.relative_to(root).as_posix()
        print(f"{label} {key}: local disk -> S3")
        if not dry_run:
            content_type = mimetypes.guess_type(path.name)[0]
            store.save(key, path.read_bytes(), content_type or "application/octet-stream")
        uploaded += 1
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dry-run", action="store_true", help="list only, change nothing")
    args = parser.parse_args()

    faces = move_database_faces(args.dry_run)
    photos = private = 0
    if uses_s3():
        photos = upload_folder(settings.media_root, media_store, "photo", args.dry_run)
        private = upload_folder(settings.private_media_root, face_store, "face", args.dry_run)

    verb = "Would move" if args.dry_run else "Moved"
    print(
        f"{verb} {faces} face(s) out of the database"
        + (f", {photos} photo(s) and {private} face file(s) to S3" if uses_s3() else "")
        + "."
    )


if __name__ == "__main__":
    main()
