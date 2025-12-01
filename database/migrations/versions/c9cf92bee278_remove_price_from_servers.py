"""remove_price_from_servers

Revision ID: c9cf92bee278
Revises: 4b5c6d7e8f9a
Create Date: 2025-11-26 10:22:32.904334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9cf92bee278'
down_revision: Union[str, None] = '4b5c6d7e8f9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем колонку price из таблицы servers
    # Цена теперь хранится в таблице locations
    op.drop_column('servers', 'price')


def downgrade() -> None:
    # Восстанавливаем колонку price (делаем её nullable, так как данные могут быть потеряны)
    op.add_column('servers', sa.Column('price', sa.Float(), nullable=True))

