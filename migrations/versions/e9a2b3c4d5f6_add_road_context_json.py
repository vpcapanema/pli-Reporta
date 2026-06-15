"""add road_context_json to reports

Revision ID: e9a2b3c4d5f6
Revises: d8f1a2b3c4e5
Create Date: 2026-06-15 03:00:00.000000

"""
# pylint: disable=invalid-name,no-member
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e9a2b3c4d5f6'
down_revision: Union[str, None] = 'd8f1a2b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('road_context_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_column('road_context_json')
