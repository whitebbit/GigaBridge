"""add_promo_codes_tables

Revision ID: a1b2c3d4e5f6
Revises: 7102cbf958bc
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7102cbf958bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы promo_codes
    op.create_table('promo_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('discount_percent', sa.Float(), nullable=False),
    sa.Column('max_uses', sa.Integer(), nullable=True),  # None = безлимитный промокод
    sa.Column('current_uses', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_promo_codes_id'), 'promo_codes', ['id'], unique=False)
    op.create_index(op.f('ix_promo_codes_code'), 'promo_codes', ['code'], unique=True)
    
    # Создание таблицы promo_code_usages
    op.create_table('promo_code_usages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('promo_code_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=True),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['promo_code_id'], ['promo_codes.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_promo_code_usages_id'), 'promo_code_usages', ['id'], unique=False)


def downgrade() -> None:
    # Удаление таблицы promo_code_usages
    op.drop_index(op.f('ix_promo_code_usages_id'), table_name='promo_code_usages')
    op.drop_table('promo_code_usages')
    
    # Удаление таблицы promo_codes
    op.drop_index(op.f('ix_promo_codes_code'), table_name='promo_codes')
    op.drop_index(op.f('ix_promo_codes_id'), table_name='promo_codes')
    op.drop_table('promo_codes')

