"""All database routes, mounted under /api."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import check_api_token
from ..db import engine
from . import account, billing, chats, designs, files, parties

router = APIRouter(prefix="/api", dependencies=[Depends(check_api_token)])
TAGS = {account: "Account and team", parties: "Parties", designs: "Designs", chats: "Chats",
        billing: "Credits and billing", files: "Files"}               # groups in /docs
for module, tag in TAGS.items():
    router.include_router(module.router, tags=[tag])


@router.get("/db/health", tags=["Health"])
def db_health():
    """Is PostgreSQL reachable?"""
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"ok": True}
