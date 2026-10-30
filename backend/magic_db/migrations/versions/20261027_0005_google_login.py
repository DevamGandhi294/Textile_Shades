"""google login: users.google_sub

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    # Google's id for the person ("sub"): stays the same even if they change their Gmail address
    op.add_column('users', sa.Column('google_sub', sa.Text(), nullable=True))
    op.create_unique_constraint(op.f('uq_users_google_sub'), 'users', ['google_sub'])


def downgrade():
    op.drop_constraint(op.f('uq_users_google_sub'), 'users', type_='unique')
    op.drop_column('users', 'google_sub')
