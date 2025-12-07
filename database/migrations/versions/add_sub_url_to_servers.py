"""add_sub_url_to_servers

Revision ID: add_sub_url_servers_2025
Revises: payment_fields_servers_2025
Create Date: 2025-01-31 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_sub_url_servers_2025'
down_revision: Union[str, None] = 'payment_fields_servers_2025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле sub_url для хранения URL шаблона ссылок подписки
    op.add_column('servers', sa.Column('sub_url', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаляем поле sub_url
    op.drop_column('servers', 'sub_url')

