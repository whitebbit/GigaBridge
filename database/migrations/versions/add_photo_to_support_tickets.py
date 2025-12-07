"""add_photo_to_support_tickets

Revision ID: f7g8h9i0j1k2
Revises: e5f6a7b8c9d0
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7g8h9i0j1k2'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Изменяем тип поля message с String на Text для поддержки больших сообщений
    op.alter_column('support_tickets', 'message',
                    existing_type=sa.String(),
                    type_=sa.Text(),
                    existing_nullable=False)
    
    # Добавляем поле photo_file_id для хранения file_id изображения
    op.add_column('support_tickets', sa.Column('photo_file_id', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаляем поле photo_file_id
    op.drop_column('support_tickets', 'photo_file_id')
    
    # Возвращаем тип поля message обратно на String
    op.alter_column('support_tickets', 'message',
                    existing_type=sa.Text(),
                    type_=sa.String(),
                    existing_nullable=False)

