"""add road_scope and road_label to reports

Revision ID: d8f1a2b3c4e5
Revises: c4a1d8f23e51
Create Date: 2026-06-15 02:00:00.000000

"""
# pylint: disable=invalid-name,no-member  # arquivo/membros gerados pelo Alembic
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd8f1a2b3c4e5'
down_revision: Union[str, None] = 'c4a1d8f23e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('road_scope', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('road_label', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_reports_road_scope'), ['road_scope'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reports_road_scope'))
        batch_op.drop_column('road_label')
        batch_op.drop_column('road_scope')
