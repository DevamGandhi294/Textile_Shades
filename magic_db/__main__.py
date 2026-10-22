"""Commands. Run from the backend folder (the one that holds magic_db/):

    python -m magic_db migrate                    create / update all tables
    python -m magic_db make-migration "add x"     after changing models.py
    python -m magic_db create-bucket              make the image bucket in MinIO / Contabo
    python -m magic_db check                      test the database and storage connections
    python -m magic_db seed-demo                  a demo shop with parties, designs and a chat
    python -m magic_db set-plan PHONE PLAN [--yearly]   e.g. set-plan 9825012345 pro (after a manual payment)
    python -m magic_db grant PHONE CREDITS [--note TEXT]  add (or with a minus, remove) credits
    python -m magic_db renew-due                  monthly credits + carry-over (run once a day)
    python -m magic_db release-stale              give back credits of AI calls that never finished
    python -m magic_db cleanup [--yes]            delete designs older than the plan keeps files
"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _alembic():
    from alembic.config import Config
    cfg = Config(str(HERE / "alembic.ini"))
    cfg.set_main_option("script_location", str(HERE / "migrations"))
    return cfg


def cmd_migrate(a):
    from alembic import command
    command.upgrade(_alembic(), "head")
    print("Database is up to date.")


def cmd_make_migration(a):
    from alembic import command
    command.revision(_alembic(), message=a.message, autogenerate=True)
    print("New migration written in magic_db/migrations/versions/. Read it, then run: python -m magic_db migrate")


def cmd_create_bucket(a):
    from . import config, storage
    storage.ensure_bucket()
    print(f"Bucket ready: {config.S3_BUCKET if config.STORAGE_BACKEND == 's3' else config.LOCAL_STORAGE_DIR}")


def cmd_check(a):
    from sqlalchemy import text

    from . import config, storage
    from .db import engine
    with engine.connect() as c:
        version = c.execute(text("select version()")).scalar()
        tables = c.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar()
    print(f"PostgreSQL OK: {version.split(',')[0]}, {tables} tables")
    storage.put("healthcheck.txt", b"ok", "text/plain")
    assert storage.read("healthcheck.txt") == b"ok"
    storage.delete("healthcheck.txt")
    print(f"Storage OK: {config.STORAGE_BACKEND} {config.S3_ENDPOINT_URL if config.STORAGE_BACKEND == 's3' else ''}")


def _member(db, phone):
    from fastapi import HTTPException

    from . import auth
    try:
        p = auth.normalise_phone(phone)
    except HTTPException as e:
        sys.exit(e.detail)
    from sqlalchemy import select

    from .models import User
    user = db.scalar(select(User).where(User.phone == p))
    member = auth.membership(db, user) if user else None
    if member is None:
        sys.exit(f"No shop found for {p}. They must log in once first.")
    return member


def cmd_set_plan(a):
    from . import credits
    from .db import session_scope
    with session_scope() as db:
        m = _member(db, a.phone)
        sub = credits.set_plan(db, m.account_id, a.plan, "yearly" if a.yearly else "monthly")
        db.flush()
        print(f"{a.phone} is now on {a.plan} until {sub.current_end:%d %b %Y}. "
              f"Balance: {credits.balance(db, m.account_id)} credits.")


def cmd_grant(a):
    from . import credits
    from .db import session_scope
    with session_scope() as db:
        m = _member(db, a.phone)
        reason = "top_up" if a.credits > 0 and a.top_up else "manual_adjust"
        credits.add(db, m.account_id, a.credits, reason, a.note or "Added by support")
        db.flush()
        print(f"Balance now {credits.balance(db, m.account_id)} credits.")


def cmd_renew_due(a):
    from . import credits
    from .db import session_scope
    with session_scope() as db:
        print(credits.renew_due(db))


def cmd_release_stale(a):
    from . import credits
    from .db import session_scope
    with session_scope() as db:
        print(f"Gave back {credits.release_stale(db)} unfinished holds.")


def cmd_cleanup(a):
    """Designs not touched for longer than the shop's plan keeps files."""
    from sqlalchemy import select

    from . import credits, storage
    from .db import session_scope
    from .models import Account, Design, DesignVersion
    with session_scope() as db:
        total = 0
        for account in db.scalars(select(Account)):
            plan = credits.plan_of(db, account.id)
            cutoff = credits.now() - timedelta(days=plan.retention_days)
            old = db.scalars(select(Design).where(Design.account_id == account.id, Design.updated_at < cutoff)).all()
            for d in old:
                keys = [k for v in db.scalars(select(DesignVersion).where(DesignVersion.design_id == d.id))
                        for k in (v.storage_key, v.thumb_key)]
                print(f"{'DELETE' if a.yes else 'would delete'}: {account.business_name} / {d.name} "
                      f"(last change {d.updated_at:%d %b %Y}, {len(keys)} files)")
                if a.yes:
                    d.current_version_id = None
                    db.flush()
                    db.delete(d)
                    db.flush()
                    storage.delete(*keys)
                total += 1
        print(f"{total} designs {'deleted' if a.yes else 'to delete. Run again with --yes to delete them'}.")


def cmd_seed_demo(a):
    from .seed import seed_demo
    seed_demo(a.phone)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m magic_db", description="Magic Outline database commands")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    s = sub.add_parser("make-migration")
    s.add_argument("message")
    s.set_defaults(fn=cmd_make_migration)
    sub.add_parser("create-bucket").set_defaults(fn=cmd_create_bucket)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    s = sub.add_parser("seed-demo")
    s.add_argument("--phone", default="9999999999")
    s.set_defaults(fn=cmd_seed_demo)
    s = sub.add_parser("set-plan")
    s.add_argument("phone")
    s.add_argument("plan", choices=["starter", "pro", "studio"])
    s.add_argument("--yearly", action="store_true")
    s.set_defaults(fn=cmd_set_plan)
    s = sub.add_parser("grant")
    s.add_argument("phone")
    s.add_argument("credits", type=int)
    s.add_argument("--note")
    s.add_argument("--top-up", action="store_true", help="count it as a paid top-up")
    s.set_defaults(fn=cmd_grant)
    sub.add_parser("renew-due").set_defaults(fn=cmd_renew_due)
    sub.add_parser("release-stale").set_defaults(fn=cmd_release_stale)
    s = sub.add_parser("cleanup")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_cleanup)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
