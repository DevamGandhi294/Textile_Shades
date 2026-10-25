"""Serves stored images to the browser: GET /files/<key>?e=&s= (signed links made by storage.url_for)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import storage

router = APIRouter()


@router.get("/files/{key:path}")
def get_file(key: str, e: int = 0, s: str = ""):
    if not storage.check_link(key, e, s):
        raise HTTPException(403, "This image link has expired. Please reload the page.")
    try:
        chunks, ctype, size = storage.get(key)
    except FileNotFoundError:
        raise HTTPException(404, "Image not found.")
    headers = {"Cache-Control": "private, max-age=3600"}
    if size:
        headers["Content-Length"] = str(size)
    return StreamingResponse(chunks, media_type=ctype, headers=headers)
