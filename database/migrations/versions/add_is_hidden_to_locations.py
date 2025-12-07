"""add_is_hidden_to_locations

Revision ID: add_is_hidden_to_locations
Revises: remove_private_location_fields
Create Date: 2025-01-31 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_is_hidden_to_locations'
down_revision: Union[str, None] = 'remove_private_location_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле is_hidden в таблицу locations
    op.add_column('locations', sa.Column('is_hidden', sa.Boolean(), nullable=True, server_default='false'))
    # Создаем индекс для поля is_hidden
    op.create_index(op.f('ix_locations_is_hidden'), 'locations', ['is_hidden'], unique=False)
    # Обновляем существующие записи
    op.execute("UPDATE locations SET is_hidden = false WHERE is_hidden IS NULL")


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index(op.f('ix_locations_is_hidden'), table_name='locations')
    # Удаляем поле is_hidden
    op.drop_column('locations', 'is_hidden')

