"""add_ssl_certificate_to_servers

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2025-01-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h9i0j1k2l3m4'
down_revision: Union[str, None] = 'g8h9i0j1k2l3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле ssl_certificate в таблицу servers
    op.add_column('servers', sa.Column('ssl_certificate', sa.Text(), nullable=True))


def downgrade() -> None:
    # Удаляем поле ssl_certificate
    op.drop_column('servers', 'ssl_certificate')

