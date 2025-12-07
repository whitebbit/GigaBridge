"""add_private_locations_and_subscriptions

Revision ID: add_private_locations
Revises: k2l3m4n5o6p7
Create Date: 2025-01-28 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_private_locations'
down_revision: Union[str, None] = 'k2l3m4n5o6p7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля для приватных локаций в таблицу locations
    op.add_column('locations', sa.Column('is_private', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('locations', sa.Column('password', sa.String(), nullable=True))
    op.create_index(op.f('ix_locations_is_private'), 'locations', ['is_private'], unique=False)
    
    # Добавляем поле is_private в таблицу subscriptions
    op.add_column('subscriptions', sa.Column('is_private', sa.Boolean(), nullable=True, server_default='false'))
    op.create_index(op.f('ix_subscriptions_is_private'), 'subscriptions', ['is_private'], unique=False)


def downgrade() -> None:
    # Удаляем индексы и поля
    op.drop_index(op.f('ix_subscriptions_is_private'), table_name='subscriptions')
    op.drop_column('subscriptions', 'is_private')
    
    op.drop_index(op.f('ix_locations_is_private'), table_name='locations')
    op.drop_column('locations', 'password')
    op.drop_column('locations', 'is_private')

