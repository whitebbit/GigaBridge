"""add_allow_reuse_to_promo_codes

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2025-01-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n5o6p7q8r9s0'
down_revision: Union[str, None] = 'm4n5o6p7q8r9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле allow_reuse_by_same_user в таблицу promo_codes
    op.add_column('promo_codes', sa.Column('allow_reuse_by_same_user', sa.Boolean(), nullable=True, server_default='false'))
    # Обновляем существующие записи - по умолчанию False
    op.execute("UPDATE promo_codes SET allow_reuse_by_same_user = false WHERE allow_reuse_by_same_user IS NULL")


def downgrade() -> None:
    # Удаляем поле allow_reuse_by_same_user
    op.drop_column('promo_codes', 'allow_reuse_by_same_user')

