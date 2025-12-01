"""make_promo_code_max_uses_nullable

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Изменяем поле max_uses на nullable для поддержки безлимитных промокодов
    # Сначала устанавливаем значение по умолчанию для существующих записей (если они есть)
    # Затем изменяем поле на nullable
    op.execute("UPDATE promo_codes SET max_uses = NULL WHERE max_uses = 0")
    op.alter_column('promo_codes', 'max_uses',
                    existing_type=sa.Integer(),
                    nullable=True,
                    existing_nullable=False)


def downgrade() -> None:
    # Возвращаем поле max_uses к not nullable
    # Устанавливаем значение по умолчанию для существующих NULL записей
    op.execute("UPDATE promo_codes SET max_uses = 0 WHERE max_uses IS NULL")
    op.alter_column('promo_codes', 'max_uses',
                    existing_type=sa.Integer(),
                    nullable=False,
                    existing_nullable=True)

