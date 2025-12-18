"""add_admin_documentation_tables

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2025-01-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'add_sub_url_servers_2025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы admin_documentation
    op.create_table('admin_documentation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admin_documentation_id'), 'admin_documentation', ['id'], unique=False)
    
    # Создание таблицы admin_documentation_files
    op.create_table('admin_documentation_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('documentation_id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=True),
    sa.Column('file_type', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('order', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['documentation_id'], ['admin_documentation.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admin_documentation_files_id'), 'admin_documentation_files', ['id'], unique=False)
    op.create_index(op.f('ix_admin_documentation_files_documentation_id'), 'admin_documentation_files', ['documentation_id'], unique=False)


def downgrade() -> None:
    # Удаление таблиц в обратном порядке (из-за внешних ключей)
    op.drop_index(op.f('ix_admin_documentation_files_documentation_id'), table_name='admin_documentation_files')
    op.drop_index(op.f('ix_admin_documentation_files_id'), table_name='admin_documentation_files')
    op.drop_table('admin_documentation_files')
    op.drop_index(op.f('ix_admin_documentation_id'), table_name='admin_documentation')
    op.drop_table('admin_documentation')

