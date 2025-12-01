"""add_proxy_path_to_servers

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2025-11-27 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавление поля proxy_path в таблицу servers
    op.add_column('servers', sa.Column('proxy_path', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаление поля proxy_path из таблицы servers
    op.drop_column('servers', 'proxy_path')

