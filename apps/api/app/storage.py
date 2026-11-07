"""Storage dei file originali su S3 compatibile.

Lo storage non è mai esposto: i file passano dall'API, che controlla i permessi a ogni
richiesta. Le chiavi non contengono il nome del file (nessuna informazione in chiaro).
"""

import hashlib
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_settings

CHUNK = 1024 * 1024


@lru_cache
def client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    bucket = get_settings().s3_bucket
    try:
        client().head_bucket(Bucket=bucket)
    except ClientError:
        client().create_bucket(Bucket=bucket)


def object_key(workspace_id: uuid.UUID, source_id: uuid.UUID, asset_id: uuid.UUID) -> str:
    return f"ws/{workspace_id}/sources/{source_id}/{asset_id}"


@dataclass
class StoredObject:
    size: int
    sha256: str


class _HashingReader:
    """Calcola hash e dimensione mentre il file viene inviato allo storage."""

    def __init__(self, fileobj: BinaryIO, max_bytes: int) -> None:
        self._f = fileobj
        self._max = max_bytes
        self.size = 0
        self._hash = hashlib.sha256()

    def read(self, n: int = -1) -> bytes:
        data = self._f.read(n)
        self.size += len(data)
        if self.size > self._max:
            raise FileTooLarge()
        self._hash.update(data)
        return data

    @property
    def sha256(self) -> str:
        return self._hash.hexdigest()


class FileTooLarge(Exception):
    pass


def put(key: str, fileobj: BinaryIO, content_type: str, max_bytes: int) -> StoredObject:
    reader = _HashingReader(fileobj, max_bytes)
    client().upload_fileobj(
        reader,
        get_settings().s3_bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return StoredObject(size=reader.size, sha256=reader.sha256)


def head(key: str) -> dict:
    return client().head_object(Bucket=get_settings().s3_bucket, Key=key)


def get(key: str, byte_range: str | None = None) -> dict:
    kwargs = {"Bucket": get_settings().s3_bucket, "Key": key}
    if byte_range:
        kwargs["Range"] = byte_range
    return client().get_object(**kwargs)


def delete(key: str) -> None:
    client().delete_object(Bucket=get_settings().s3_bucket, Key=key)


def delete_prefix(prefix: str) -> int:
    bucket = get_settings().s3_bucket
    deleted = 0
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objects:
            client().delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted += len(objects)
    return deleted
