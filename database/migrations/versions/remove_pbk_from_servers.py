"""remove_pbk_from_servers

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2025-01-28 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i0j1k2l3m4n5'
down_revision: Union[str, None] = 'h9i0j1k2l3m4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем поле pbk из таблицы servers
    op.drop_column('servers', 'pbk')


def downgrade() -> None:
    # Возвращаем поле pbk обратно
    op.add_column('servers', sa.Column('pbk', sa.String(), nullable=True))

