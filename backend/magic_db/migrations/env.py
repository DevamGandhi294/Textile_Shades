"""Alembic environment: reads DATABASE_URL from magic_db.config and the tables from magic_db.models."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from magic_db import config as app_config
from magic_db.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata


def run_offline():
    context.configure(url=app_config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online():
    engine = create_engine(app_config.DATABASE_URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
