"""add_sub_id_to_users

Revision ID: g8h9i0j1k2l3
Revises: f7g8h9i0j1k2
Create Date: 2025-01-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g8h9i0j1k2l3'
down_revision: Union[str, None] = 'f7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле sub_id в таблицу users
    op.add_column('users', sa.Column('sub_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_users_sub_id'), 'users', ['sub_id'], unique=False)


def downgrade() -> None:
    # Удаляем индекс и поле sub_id
    op.drop_index(op.f('ix_users_sub_id'), table_name='users')
    op.drop_column('users', 'sub_id')

