"""Image storage: MinIO / Contabo / any S3 (STORAGE_BACKEND=s3) or a local folder (STORAGE_BACKEND=local).

Only this file talks to storage. Moving from MinIO to Contabo = change S3_* in .env, nothing else.

The browser never gets a storage address. It gets a link to our own backend,
/api/files/<key>?e=<expiry>&s=<signature>, which works for FILE_LINK_MINUTES and needs no login,
so it can sit in an <img> tag. Store keys in the database, never links (links expire).
"""
import base64
import binascii
import hashlib
import hmac
import io
import re
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple
from urllib.parse import quote

from . import config

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config
        _s3 = boto3.client(
            "s3", endpoint_url=config.S3_ENDPOINT_URL, region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY, aws_secret_access_key=config.S3_SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
    return _s3


def _local_path(key: str) -> Path:
    p = (config.LOCAL_STORAGE_DIR / key).resolve()
    if config.LOCAL_STORAGE_DIR.resolve() not in p.parents:
        raise ValueError("bad key")
    return p


# ------------------------------------------------------------------ basic operations

def ensure_bucket():
    """Create the bucket if it is missing (safe to run again)."""
    if config.STORAGE_BACKEND == "local":
        config.LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return
    s3 = _client()
    try:
        s3.head_bucket(Bucket=config.S3_BUCKET)
    except Exception:
        s3.create_bucket(Bucket=config.S3_BUCKET)


def put(key: str, data: bytes, content_type: str):
    if config.STORAGE_BACKEND == "local":
        p = _local_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return
    _client().put_object(Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=content_type)


def get(key: str) -> Tuple[Iterator[bytes], str, int]:
    """(chunks, content_type, size). Raises FileNotFoundError when missing."""
    if config.STORAGE_BACKEND == "local":
        p = _local_path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        data = p.read_bytes()
        return iter([data]), _guess_type(key), len(data)
    s3 = _client()
    try:
        obj = s3.get_object(Bucket=config.S3_BUCKET, Key=key)
    except s3.exceptions.NoSuchKey:
        raise FileNotFoundError(key)
    body = obj["Body"]
    return body.iter_chunks(64 * 1024), obj.get("ContentType") or _guess_type(key), obj.get("ContentLength", 0)


def read(key: str) -> bytes:
    chunks, _, _ = get(key)
    return b"".join(chunks)


def copy(src_key: str, dst_key: str):
    if config.STORAGE_BACKEND == "local":
        dst = _local_path(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_local_path(src_key).read_bytes())
        return
    _client().copy_object(Bucket=config.S3_BUCKET, Key=dst_key,
                          CopySource={"Bucket": config.S3_BUCKET, "Key": src_key})


def delete(*keys: Optional[str]):
    """Delete files; missing ones are ignored."""
    keys = [k for k in keys if k]
    if not keys:
        return
    if config.STORAGE_BACKEND == "local":
        for k in keys:
            try:
                _local_path(k).unlink()
            except FileNotFoundError:
                pass
        return
    s3 = _client()
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=config.S3_BUCKET,
                          Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


def _guess_type(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
            "svg": "image/svg+xml", "pdf": "application/pdf"}.get(ext, "application/octet-stream")


# ------------------------------------------------------------------ signed links

def _sign(key: str, exp: int) -> str:
    msg = f"{key}\n{exp}".encode()
    return hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]


def url_for(key: Optional[str]) -> Optional[str]:
    """A link the browser can load for FILE_LINK_MINUTES (rounded so links stay cacheable)."""
    if not key:
        return None
    step = 300
    exp = (int(time.time()) // step + 1) * step + config.FILE_LINK_MINUTES * 60
    return f"{config.FILES_URL_PREFIX}/{quote(key)}?e={exp}&s={_sign(key, exp)}"


def check_link(key: str, exp: int, sig: str) -> bool:
    return exp >= time.time() and hmac.compare_digest(_sign(key, exp), sig)


def key_from_url(url: str) -> Optional[str]:
    """If url is one of our own valid links, return its key (used when the frontend sends a link back)."""
    from urllib.parse import parse_qs, unquote, urlparse
    u = urlparse(url)
    prefix = urlparse(config.FILES_URL_PREFIX).path + "/"
    if not u.path.startswith(prefix):
        return None
    key = unquote(u.path[len(prefix):])
    q = parse_qs(u.query)
    try:
        exp, sig = int(q["e"][0]), q["s"][0]
    except (KeyError, ValueError, IndexError):
        return None
    return key if hmac.compare_digest(_sign(key, exp), sig) else None


# ------------------------------------------------------------------ images from the frontend

_DATA_URL = re.compile(r"^data:([\w/+.-]+)(;[\w=-]+)*;base64,(.*)$", re.S)
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}


class BadImage(ValueError):
    pass


def decode_data_url(url: str) -> Tuple[bytes, str, str]:
    """data:image/png;base64,... -> (bytes, content_type, ext)."""
    m = _DATA_URL.match(url)
    if not m:
        raise BadImage("The image must be a data URL (data:image/...;base64,...) or a saved image link.")
    ctype = m.group(1).lower()
    if ctype not in _EXT:
        raise BadImage("Please upload a photo (JPG, PNG, WEBP) or an SVG.")
    try:
        data = base64.b64decode(m.group(3), validate=False)
    except (binascii.Error, ValueError):
        raise BadImage("The image data is damaged.")
    if len(data) > config.MAX_IMAGE_MB * 1024 * 1024:
        raise BadImage(f"The photo is too big (more than {config.MAX_IMAGE_MB} MB).")
    return data, ctype, _EXT[ctype]


def image_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height
    except Exception:
        return None, None


def make_thumb(data: bytes, max_side: int = 400) -> Optional[bytes]:
    """A small JPEG preview for lists and party pages. None for SVG or unreadable files."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im.thumbnail((max_side, max_side))
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, "JPEG", quality=82)
            return out.getvalue()
    except Exception:
        return None
