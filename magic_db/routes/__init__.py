"""All database routes, mounted under /api."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import check_api_token
from ..db import engine
from . import account, billing, chats, designs, files, parties

router = APIRouter(prefix="/api", dependencies=[Depends(check_api_token)])
for module in (account, parties, designs, chats, billing, files):
    router.include_router(module.router)


@router.get("/db/health")
def db_health():
    """Is PostgreSQL reachable?"""
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"ok": True}
