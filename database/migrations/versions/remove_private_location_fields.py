"""remove_private_location_fields

Revision ID: remove_private_location_fields
Revises: 9dd0e1f2a3b4
Create Date: 2025-01-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'remove_private_location_fields'
down_revision: Union[str, None] = '9dd0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем индекс и поля для приватных локаций из таблицы locations
    op.drop_index(op.f('ix_locations_is_private'), table_name='locations')
    op.drop_column('locations', 'password')
    op.drop_column('locations', 'is_private')


def downgrade() -> None:
    # Восстанавливаем поля для приватных локаций в таблицу locations
    op.add_column('locations', sa.Column('is_private', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('locations', sa.Column('password', sa.String(), nullable=True))
    op.create_index(op.f('ix_locations_is_private'), 'locations', ['is_private'], unique=False)

