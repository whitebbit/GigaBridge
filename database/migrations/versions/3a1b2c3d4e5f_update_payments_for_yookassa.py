"""Update payments for YooKassa

Revision ID: 3a1b2c3d4e5f
Revises: 2e8fff6060d9
Create Date: 2024-11-25 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3a1b2c3d4e5f'
down_revision = '2e8fff6060d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Изменяем валюту по умолчанию с USD на RUB
    op.alter_column('payments', 'currency',
                    existing_type=sa.String(),
                    server_default='RUB',
                    nullable=True)
    
    # Добавляем server_id для связи с сервером
    op.add_column('payments', sa.Column('server_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_payments_server_id', 'payments', 'servers', ['server_id'], ['id'])
    
    # Добавляем yookassa_payment_id для хранения ID платежа в YooKassa
    op.add_column('payments', sa.Column('yookassa_payment_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_payments_yookassa_payment_id'), 'payments', ['yookassa_payment_id'], unique=True)
    
    # Добавляем paid_at для хранения даты оплаты
    op.add_column('payments', sa.Column('paid_at', sa.DateTime(), nullable=True))
    
    # Обновляем существующие записи: меняем USD на RUB
    op.execute("UPDATE payments SET currency = 'RUB' WHERE currency = 'USD' OR currency IS NULL")


def downgrade() -> None:
    # Удаляем индекс и колонку yookassa_payment_id
    op.drop_index(op.f('ix_payments_yookassa_payment_id'), table_name='payments')
    op.drop_column('payments', 'yookassa_payment_id')
    
    # Удаляем колонку paid_at
    op.drop_column('payments', 'paid_at')
    
    # Удаляем server_id
    op.drop_constraint('fk_payments_server_id', 'payments', type_='foreignkey')
    op.drop_column('payments', 'server_id')
    
    # Возвращаем валюту по умолчанию на USD
    op.alter_column('payments', 'currency',
                    existing_type=sa.String(),
                    server_default='USD',
                    nullable=True)
    op.execute("UPDATE payments SET currency = 'USD' WHERE currency = 'RUB'")

