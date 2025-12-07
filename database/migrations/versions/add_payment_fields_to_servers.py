"""add_payment_fields_to_servers

Revision ID: payment_fields_servers_2025
Revises: add_is_hidden_to_locations
Create Date: 2025-01-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'payment_fields_servers_2025'
down_revision: Union[str, None] = 'add_is_hidden_to_locations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля для отслеживания оплаты сервера
    op.add_column('servers', sa.Column('payment_expire_date', sa.DateTime(), nullable=True))
    op.add_column('servers', sa.Column('payment_days', sa.Integer(), nullable=True))
    # Создаем индекс для быстрого поиска серверов с истекающей оплатой
    op.create_index(op.f('ix_servers_payment_expire_date'), 'servers', ['payment_expire_date'])


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index(op.f('ix_servers_payment_expire_date'), table_name='servers')
    # Удаляем поля
    op.drop_column('servers', 'payment_days')
    op.drop_column('servers', 'payment_expire_date')

