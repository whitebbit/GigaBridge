"""add_sub_id_to_subscriptions

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2025-01-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, None] = 'i0j1k2l3m4n5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле sub_id в таблицу subscriptions
    op.add_column('subscriptions', sa.Column('sub_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_subscriptions_sub_id'), 'subscriptions', ['sub_id'], unique=False)


def downgrade() -> None:
    # Удаляем индекс и поле sub_id
    op.drop_index(op.f('ix_subscriptions_sub_id'), table_name='subscriptions')
    op.drop_column('subscriptions', 'sub_id')

