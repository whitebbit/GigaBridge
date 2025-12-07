"""add_email_to_users

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2025-01-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l3m4n5o6p7q8'
down_revision: Union[str, None] = 'k2l3m4n5o6p7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле email в таблицу users
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаляем поле email
    op.drop_column('users', 'email')

