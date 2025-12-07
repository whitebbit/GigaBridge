"""merge_email_and_private_locations

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8, add_private_locations
Create Date: 2025-01-29 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm4n5o6p7q8r9'
down_revision: Union[str, tuple[str, ...], None] = ('l3m4n5o6p7q8', 'add_private_locations')  # Merge двух веток
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge миграция - не требует изменений, так как обе миграции уже применены
    pass


def downgrade() -> None:
    # Merge миграция - не требует изменений
    pass

