"""add_failed_subscription_attempts_table

Revision ID: 9dd0e1f2a3b4
Revises: add_photo_to_support_tickets
Create Date: 2025-01-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9dd0e1f2a3b4'
down_revision: Union[str, tuple[str, ...], None] = ('n5o6p7q8r9s0', 'f7g8h9i0j1k2')  # Merge двух веток: add_allow_reuse_to_promo_codes и add_photo_to_support_tickets
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы failed_subscription_attempts
    op.create_table('failed_subscription_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('server_id', sa.Integer(), nullable=False),
    sa.Column('subscription_id', sa.Integer(), nullable=True),
    sa.Column('is_renewal', sa.Boolean(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('error_type', sa.String(), nullable=True),
    sa.Column('attempt_count', sa.Integer(), nullable=True),
    sa.Column('max_attempts', sa.Integer(), nullable=True),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('refund_attempted', sa.Boolean(), nullable=True),
    sa.Column('refund_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ),
    sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_failed_subscription_attempts_id'), 'failed_subscription_attempts', ['id'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_payment_id'), 'failed_subscription_attempts', ['payment_id'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_user_id'), 'failed_subscription_attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_server_id'), 'failed_subscription_attempts', ['server_id'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_subscription_id'), 'failed_subscription_attempts', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_is_renewal'), 'failed_subscription_attempts', ['is_renewal'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_next_attempt_at'), 'failed_subscription_attempts', ['next_attempt_at'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_status'), 'failed_subscription_attempts', ['status'], unique=False)
    op.create_index(op.f('ix_failed_subscription_attempts_created_at'), 'failed_subscription_attempts', ['created_at'], unique=False)
    op.create_index('idx_failed_attempt_status_next', 'failed_subscription_attempts', ['status', 'next_attempt_at'], unique=False)
    op.create_index('idx_failed_attempt_payment', 'failed_subscription_attempts', ['payment_id', 'status'], unique=False)


def downgrade() -> None:
    # Удаление таблицы failed_subscription_attempts
    op.drop_index('idx_failed_attempt_payment', table_name='failed_subscription_attempts')
    op.drop_index('idx_failed_attempt_status_next', table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_created_at'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_status'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_next_attempt_at'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_is_renewal'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_subscription_id'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_server_id'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_user_id'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_payment_id'), table_name='failed_subscription_attempts')
    op.drop_index(op.f('ix_failed_subscription_attempts_id'), table_name='failed_subscription_attempts')
    op.drop_table('failed_subscription_attempts')

