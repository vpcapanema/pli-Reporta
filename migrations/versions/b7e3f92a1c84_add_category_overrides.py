"""add category_overrides_json to moderation_policy

Revision ID: b7e3f92a1c84
Revises: 48ae7286ef69
Create Date: 2026-06-14 22:00:00.000000

"""
# flake8: noqa  (arquivo auto-gerado pelo Alembic)
# pylint: disable=invalid-name,no-member  # arquivo/membros gerados pelo Alembic
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e3f92a1c84'
down_revision: Union[str, None] = '48ae7286ef69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('moderation_policy', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_overrides_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('moderation_policy', schema=None) as batch_op:
        batch_op.drop_column('category_overrides_json')
