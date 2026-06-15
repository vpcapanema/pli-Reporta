"""add veracity_weights_json and highway_factors_json to moderation_policy

Revision ID: c4a1d8f23e51
Revises: b7e3f92a1c84
Create Date: 2026-06-15 00:00:00.000000

"""
# flake8: noqa  (arquivo auto-gerado pelo Alembic)
# pylint: disable=invalid-name,no-member  # arquivo/membros gerados pelo Alembic
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a1d8f23e51'
down_revision: Union[str, None] = 'b7e3f92a1c84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('moderation_policy', schema=None) as batch_op:
        batch_op.add_column(sa.Column('veracity_weights_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('highway_factors_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('moderation_policy', schema=None) as batch_op:
        batch_op.drop_column('highway_factors_json')
        batch_op.drop_column('veracity_weights_json')
