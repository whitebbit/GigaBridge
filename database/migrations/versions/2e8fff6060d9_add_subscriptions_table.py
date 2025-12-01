"""add_subscriptions_table

Revision ID: 2e8fff6060d9
Revises: 80eb616c732e
Create Date: 2025-11-25 10:55:28.862541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e8fff6060d9'
down_revision: Union[str, None] = '80eb616c732e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы subscriptions
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('server_id', sa.Integer(), nullable=False),
    sa.Column('tariff_id', sa.Integer(), nullable=False),
    sa.Column('hiddify_id', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('expire_date', sa.DateTime(), nullable=True),
    sa.Column('traffic_used', sa.Float(), nullable=True),
    sa.Column('traffic_limit', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ),
    sa.ForeignKeyConstraint(['tariff_id'], ['tariffs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)
    op.create_index('ix_subscriptions_user_server', 'subscriptions', ['user_id', 'server_id'], unique=False)


def downgrade() -> None:
    # Удаление таблицы subscriptions
    op.drop_index('ix_subscriptions_user_server', table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_id'), table_name='subscriptions')
    op.drop_table('subscriptions')

