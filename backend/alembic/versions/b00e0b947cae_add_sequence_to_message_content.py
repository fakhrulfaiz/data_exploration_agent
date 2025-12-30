"""add_sequence_to_message_content

Revision ID: b00e0b947cae
Revises: 
Create Date: 2025-12-30 13:35:15.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b00e0b947cae'
down_revision: Union[str, None] = None  # Update this if there's a previous migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sequence column with default value 0
    op.add_column('message_content', 
        sa.Column('sequence', sa.Integer(), nullable=False, server_default='0')
    )
    
    # Create index for efficient ordering queries
    op.create_index(
        'idx_message_content_message_sequence',
        'message_content',
        ['chat_message_id', 'sequence'],
        unique=False
    )
    
    # Backfill existing records with sequence based on created_at order
    # This ensures existing data has correct ordering
    op.execute("""
        WITH numbered_blocks AS (
            SELECT 
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY chat_message_id 
                    ORDER BY created_at
                ) - 1 as seq_num
            FROM message_content
        )
        UPDATE message_content mc
        SET sequence = nb.seq_num
        FROM numbered_blocks nb
        WHERE mc.id = nb.id
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_message_content_message_sequence', table_name='message_content')
    
    # Drop column
    op.drop_column('message_content', 'sequence')
