"""add_location_unique_name_to_subscriptions

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2025-01-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k2l3m4n5o6p7'
down_revision: Union[str, None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле location_unique_name в таблицу subscriptions
    op.add_column('subscriptions', sa.Column('location_unique_name', sa.String(), nullable=True))
    op.create_index(op.f('ix_subscriptions_location_unique_name'), 'subscriptions', ['location_unique_name'], unique=False)


def downgrade() -> None:
    # Удаляем индекс и поле location_unique_name
    op.drop_index(op.f('ix_subscriptions_location_unique_name'), table_name='subscriptions')
    op.drop_column('subscriptions', 'location_unique_name')

