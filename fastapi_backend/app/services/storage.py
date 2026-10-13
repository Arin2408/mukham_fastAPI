"""
File storage for employee photos and enrolled face images.

Two stores:
- media_store: employee photos. Local disk under MEDIA_ROOT (served at
  /media), or the S3 bucket under media/ with short-lived signed URLs.
- face_store: enrolled face images (biometric data). Local disk under
  PRIVATE_MEDIA_ROOT, which is never served, or the S3 bucket under faces/.
  Face images have no URL; they are only read server-side.

S3 is used when MEDIA_S3_BUCKET is set. The bucket must be private;
objects are written with server-side encryption.
"""
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


logger = logging.getLogger(__name__)


class LocalStorage:
    def __init__(self, root: Path, url_prefix: str | None = None):
        self.root = root
        self.url_prefix = url_prefix

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def url(self, key: str) -> str | None:
        if self.url_prefix is None:
            return None
        return f"{self.url_prefix}/{key}"


class S3Storage:
    def __init__(self, bucket: str, prefix: str, public_urls: bool):
        self.bucket = bucket
        self.prefix = prefix
        self.public_urls = public_urls
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_default_region,
        )

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    def save(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def read(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=self._key(key),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))

    def url(self, key: str) -> str | None:
        if not self.public_urls:
            return None
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(key)},
            ExpiresIn=settings.media_url_expire_seconds,
        )


def uses_s3() -> bool:
    return bool(settings.media_s3_bucket)


if uses_s3():
    media_store = S3Storage(settings.media_s3_bucket, "media", public_urls=True)
    face_store = S3Storage(settings.media_s3_bucket, "faces", public_urls=False)
else:
    media_store = LocalStorage(settings.media_root, url_prefix="/media")
    face_store = LocalStorage(settings.private_media_root)
