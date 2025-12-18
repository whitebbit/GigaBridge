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
    # Используем условный SQL для проверки и добавления колонки
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'servers' 
                AND column_name = 'subscription_url'
                AND table_schema = 'public'
            ) THEN
                ALTER TABLE servers ADD COLUMN subscription_url VARCHAR;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Удаляем колонку subscription_url, если она существует
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'servers' 
                AND column_name = 'subscription_url'
                AND table_schema = 'public'
            ) THEN
                ALTER TABLE servers DROP COLUMN subscription_url;
            END IF;
        END $$;
    """)

