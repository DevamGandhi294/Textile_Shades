"""Magic Outline database part: login, parties, designs, images, chats, credits and billing.

Add it to the existing backend (backend/api.py) with two lines:

    import magic_db
    magic_db.setup(app)

Or run it on its own:  uvicorn magic_db.standalone:app --port 8001
"""
import logging

__all__ = ["setup", "router"]

log = logging.getLogger("magic_db")


def setup(app):
    """Mount every database route under /api on an existing FastAPI app."""
    from . import config
    from .routes import router

    app.include_router(router)
    if config.SECRET_KEY == "dev-only-secret-change-me":
        log.warning("SECRET_KEY is not set: image links and OTPs use a development key. Set it outside local dev.")
    if config.DEV_LOGIN_PHONE:
        log.warning("DEV_LOGIN_PHONE is set: requests without login act as %s. Never set it on a real server.",
                    config.DEV_LOGIN_PHONE)


def __getattr__(name):
    if name == "router":
        from .routes import router
        return router
    raise AttributeError(name)
