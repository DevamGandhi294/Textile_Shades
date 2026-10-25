"""free trial: 100 credits instead of 10

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 15:30:00
"""
from alembic import op


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # new shops only; accounts that already started their trial keep what they were given
    op.execute("UPDATE plans SET one_time_credits = 100, "
               "features[1] = '100 credits, one time' WHERE id = 'free'")


def downgrade():
    op.execute("UPDATE plans SET one_time_credits = 10, "
               "features[1] = '10 credits, one time' WHERE id = 'free'")
