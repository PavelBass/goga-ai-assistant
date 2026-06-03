"""chat history: chats, messages, message_media

Revision ID: b7e2c9a4f1d3
Revises: 34a0a7c31535
Create Date: 2026-06-03 22:30:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7e2c9a4f1d3'
down_revision: str | None = '34a0a7c31535'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Применить миграцию"""
    op.create_table(
        'chats',
        sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('tg_message_id', sa.BigInteger(), nullable=False),
        sa.Column('sender_user_id', sa.BigInteger(), nullable=True),
        sa.Column('sender_username', sa.String(length=255), nullable=True),
        sa.Column('sender_name', sa.Text(), nullable=True),
        sa.Column('direction', sa.Enum('incoming', 'outgoing', name='message_direction'), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('edit_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reply_to_tg_message_id', sa.BigInteger(), nullable=True),
        sa.Column('forward_origin', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('forward_sender_name', sa.Text(), nullable=True),
        sa.Column('media_group_id', sa.String(length=64), nullable=True),
        sa.Column('content_type', sa.String(length=32), nullable=False),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id', 'tg_message_id', name='uq_messages_chat_tg_id'),
    )
    op.create_index('ix_messages_media_group', 'messages', ['media_group_id'], unique=False)
    op.create_table(
        'message_media',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column(
            'media_type',
            sa.Enum(
                'photo',
                'video',
                'animation',
                'document',
                'audio',
                'voice',
                'video_note',
                'sticker',
                name='media_type',
            ),
            nullable=False,
        ),
        sa.Column('file_id', sa.Text(), nullable=False),
        sa.Column('file_unique_id', sa.String(length=64), nullable=False),
        sa.Column('file_name', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(length=255), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=True),
        sa.Column('downloaded', sa.Boolean(), nullable=False),
        sa.Column('download_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id'),
    )
    op.create_index('ix_message_media_file_unique_id', 'message_media', ['file_unique_id'], unique=False)


def downgrade() -> None:
    """Откатить миграцию"""
    op.drop_index('ix_message_media_file_unique_id', table_name='message_media')
    op.drop_table('message_media')
    op.drop_index('ix_messages_media_group', table_name='messages')
    op.drop_table('messages')
    op.drop_table('chats')
    # Типы enum не удаляются автоматически вместе с таблицами в PostgreSQL
    sa.Enum(name='media_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='message_direction').drop(op.get_bind(), checkfirst=True)
