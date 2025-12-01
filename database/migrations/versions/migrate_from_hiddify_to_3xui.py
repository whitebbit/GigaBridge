"""migrate_from_hiddify_to_3xui

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-11-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Обновление таблицы users: переименование hiddify_id в x3ui_id
    op.alter_column('users', 'hiddify_id', new_column_name='x3ui_id')
    
    # 2. Обновление таблицы servers:
    #    - Удаление proxy_path
    #    - Переименование api_key в api_username
    #    - Добавление api_password
    #    - Добавление inbound_id
    #    - Добавление subscription_url (опционально)
    op.drop_column('servers', 'proxy_path')
    op.alter_column('servers', 'api_key', new_column_name='api_username')
    op.add_column('servers', sa.Column('api_password', sa.String(), nullable=False, server_default=''))
    op.add_column('servers', sa.Column('inbound_id', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('servers', sa.Column('subscription_url', sa.String(), nullable=True))
    
    # 3. Обновление таблицы subscriptions:
    #    - Переименование hiddify_id в x3ui_client_id
    #    - Добавление x3ui_client_email
    op.alter_column('subscriptions', 'hiddify_id', new_column_name='x3ui_client_id')
    op.add_column('subscriptions', sa.Column('x3ui_client_email', sa.String(), nullable=True))


def downgrade() -> None:
    # Откат изменений
    op.alter_column('subscriptions', 'x3ui_client_id', new_column_name='hiddify_id')
    op.drop_column('subscriptions', 'x3ui_client_email')
    
    op.drop_column('servers', 'subscription_url')
    op.drop_column('servers', 'inbound_id')
    op.drop_column('servers', 'api_password')
    op.alter_column('servers', 'api_username', new_column_name='api_key')
    op.add_column('servers', sa.Column('proxy_path', sa.String(), nullable=True))
    
    op.alter_column('users', 'x3ui_id', new_column_name='hiddify_id')

