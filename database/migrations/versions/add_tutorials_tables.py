"""add_tutorials_tables

Revision ID: e5f6a7b8c9d0
Revises: add_deletion_notification_fields
Create Date: 2025-01-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'add_deletion_notification_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы platforms
    op.create_table('platforms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('display_name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('order', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_platforms_id'), 'platforms', ['id'], unique=False)
    op.create_index(op.f('ix_platforms_is_active'), 'platforms', ['is_active'], unique=False)
    
    # Создание таблицы tutorials
    op.create_table('tutorials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('platform_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('video_file_id', sa.String(), nullable=True),
    sa.Column('video_note_id', sa.String(), nullable=True),
    sa.Column('is_basic', sa.Boolean(), nullable=True),
    sa.Column('order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['platform_id'], ['platforms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tutorials_id'), 'tutorials', ['id'], unique=False)
    op.create_index(op.f('ix_tutorials_platform_id'), 'tutorials', ['platform_id'], unique=False)
    op.create_index(op.f('ix_tutorials_is_basic'), 'tutorials', ['is_basic'], unique=False)
    op.create_index(op.f('ix_tutorials_is_active'), 'tutorials', ['is_active'], unique=False)
    op.create_index('idx_tutorial_platform_active', 'tutorials', ['platform_id', 'is_active'], unique=False)
    op.create_index('idx_tutorial_platform_basic', 'tutorials', ['platform_id', 'is_basic'], unique=False)
    
    # Создание таблицы tutorial_files
    op.create_table('tutorial_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tutorial_id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=True),
    sa.Column('file_type', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('order', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tutorial_id'], ['tutorials.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tutorial_files_id'), 'tutorial_files', ['id'], unique=False)
    op.create_index(op.f('ix_tutorial_files_tutorial_id'), 'tutorial_files', ['tutorial_id'], unique=False)


def downgrade() -> None:
    # Удаление таблиц в обратном порядке (из-за внешних ключей)
    op.drop_index(op.f('ix_tutorial_files_tutorial_id'), table_name='tutorial_files')
    op.drop_index(op.f('ix_tutorial_files_id'), table_name='tutorial_files')
    op.drop_table('tutorial_files')
    
    op.drop_index('idx_tutorial_platform_basic', table_name='tutorials')
    op.drop_index('idx_tutorial_platform_active', table_name='tutorials')
    op.drop_index(op.f('ix_tutorials_is_active'), table_name='tutorials')
    op.drop_index(op.f('ix_tutorials_is_basic'), table_name='tutorials')
    op.drop_index(op.f('ix_tutorials_platform_id'), table_name='tutorials')
    op.drop_index(op.f('ix_tutorials_id'), table_name='tutorials')
    op.drop_table('tutorials')
    
    op.drop_index(op.f('ix_platforms_is_active'), table_name='platforms')
    op.drop_index(op.f('ix_platforms_id'), table_name='platforms')
    op.drop_table('platforms')

