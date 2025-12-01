"""add_locations_table

Revision ID: 4b5c6d7e8f9a
Revises: 3a1b2c3d4e5f
Create Date: 2024-11-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4b5c6d7e8f9a'
down_revision = '3a1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создание таблицы locations
    op.create_table('locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_locations_id'), 'locations', ['id'], unique=False)
    
    # Добавляем location_id в таблицу servers
    op.add_column('servers', sa.Column('location_id', sa.Integer(), nullable=True))
    
    # Создаем временную таблицу для миграции данных
    # Если у серверов была строка location, создаем локации и привязываем серверы
    op.execute("""
        INSERT INTO locations (name, price, is_active, created_at, updated_at)
        SELECT DISTINCT 
            COALESCE(location, 'Без локации') as name,
            MIN(price) as price,
            TRUE as is_active,
            NOW() as created_at,
            NOW() as updated_at
        FROM servers
        WHERE location IS NOT NULL
        GROUP BY location
    """)
    
    # Обновляем location_id для серверов
    op.execute("""
        UPDATE servers
        SET location_id = (
            SELECT id FROM locations 
            WHERE locations.name = COALESCE(servers.location, 'Без локации')
            LIMIT 1
        )
    """)
    
    # Если есть серверы без локации, создаем дефолтную
    op.execute("""
        INSERT INTO locations (name, price, is_active, created_at, updated_at)
        SELECT 'Без локации', 0.0, TRUE, NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM locations WHERE name = 'Без локации'
        )
    """)
    
    # Обновляем серверы без location_id
    op.execute("""
        UPDATE servers
        SET location_id = (SELECT id FROM locations WHERE name = 'Без локации' LIMIT 1)
        WHERE location_id IS NULL
    """)
    
    # Делаем location_id обязательным
    op.alter_column('servers', 'location_id', nullable=False)
    
    # Создаем внешний ключ
    op.create_foreign_key('fk_servers_location_id', 'servers', 'locations', ['location_id'], ['id'])
    
    # Удаляем старую колонку location
    op.drop_column('servers', 'location')


def downgrade() -> None:
    # Добавляем обратно колонку location
    op.add_column('servers', sa.Column('location', sa.String(), nullable=True))
    
    # Заполняем location из связанной локации
    op.execute("""
        UPDATE servers
        SET location = (SELECT name FROM locations WHERE locations.id = servers.location_id)
    """)
    
    # Удаляем внешний ключ
    op.drop_constraint('fk_servers_location_id', 'servers', type_='foreignkey')
    
    # Удаляем location_id
    op.drop_column('servers', 'location_id')
    
    # Удаляем таблицу locations
    op.drop_index(op.f('ix_locations_id'), table_name='locations')
    op.drop_table('locations')

