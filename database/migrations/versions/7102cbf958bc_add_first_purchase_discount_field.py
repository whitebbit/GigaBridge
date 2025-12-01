"""add_first_purchase_discount_field

Revision ID: 7102cbf958bc
Revises: c9cf92bee278
Create Date: 2025-11-26 11:03:00.122062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7102cbf958bc'
down_revision: Union[str, None] = 'c9cf92bee278'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле для отслеживания использования скидки на первую покупку
    op.add_column('users', sa.Column('used_first_purchase_discount', sa.Boolean(), nullable=True, server_default='false'))
    # Обновляем существующие записи
    op.execute("UPDATE users SET used_first_purchase_discount = false WHERE used_first_purchase_discount IS NULL")


def downgrade() -> None:
    # Удаляем поле
    op.drop_column('users', 'used_first_purchase_discount')

