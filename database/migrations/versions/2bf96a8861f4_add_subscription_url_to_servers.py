"""add_subscription_url_to_servers

Revision ID: 2bf96a8861f4
Revises: d4e5f6a7b8c9
Create Date: 2025-11-28 15:09:06.122311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bf96a8861f4'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем колонку subscription_url, если её ещё нет
    try:
        op.add_column('servers', sa.Column('subscription_url', sa.String(), nullable=True))
    except Exception:
        # Колонка уже существует, пропускаем
        pass


def downgrade() -> None:
    # Удаляем колонку subscription_url, если она существует
    try:
        op.drop_column('servers', 'subscription_url')
    except Exception:
        # Колонка не существует, пропускаем
        pass

