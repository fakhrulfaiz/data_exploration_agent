"""merge_heads

Revision ID: ef83184b2739
Revises: b00e0b947cae, dd8fb2da2ffb
Create Date: 2025-12-30 05:41:31.983413

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ef83184b2739'
down_revision = ('b00e0b947cae', 'dd8fb2da2ffb')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
