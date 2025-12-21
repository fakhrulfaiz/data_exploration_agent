"""remove_message_type_and_status_from_chat_messages

Revision ID: dd8fb2da2ffb
Revises: e503f4ae17c0
Create Date: 2025-12-20 17:41:38.404938

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'dd8fb2da2ffb'
down_revision = 'e503f4ae17c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop indexes that reference these columns
    op.drop_index('idx_chat_messages_thread_type', table_name='chat_messages')
    op.drop_index('idx_chat_messages_thread_status', table_name='chat_messages')
    
    # Drop the columns
    op.drop_column('chat_messages', 'message_type')
    op.drop_column('chat_messages', 'message_status')
    
    # Drop only message_type_enum (message_status_enum is still used by MessageContent)
    op.execute('DROP TYPE IF EXISTS message_type_enum')


def downgrade() -> None:
    # Recreate message_type_enum
    op.execute("CREATE TYPE message_type_enum AS ENUM ('MESSAGE', 'EXPLORER', 'VISUALIZATION', 'STRUCTURED')")
    
    # Add columns back
    op.add_column('chat_messages', 
        sa.Column('message_status', postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'ERROR', 'TIMEOUT', 
                  name='message_status_enum', create_type=False), nullable=True)
    )
    op.add_column('chat_messages',
        sa.Column('message_type', postgresql.ENUM('MESSAGE', 'EXPLORER', 'VISUALIZATION', 'STRUCTURED', 
                  name='message_type_enum', create_type=False), nullable=False, 
                  server_default='STRUCTURED')
    )
    
    # Recreate indexes
    op.create_index('idx_chat_messages_thread_status', 'chat_messages', ['thread_id', 'message_status'])
    op.create_index('idx_chat_messages_thread_type', 'chat_messages', ['thread_id', 'message_type'])


