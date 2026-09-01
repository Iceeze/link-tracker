"""Initial database schema for chats, links, and tags

Revision ID: 001
Revises:
Create Date: 2026-03-22

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chats"),
        sa.UniqueConstraint("chat_id", name="uq_chats_chat_id"),
    )
    op.create_index("idx_chats_chat_id", "chats", ["chat_id"], unique=False)

    op.create_table(
        "links",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_links"),
        sa.UniqueConstraint("url", name="uq_links_url"),
    )
    op.create_index("idx_links_url", "links", ["url"], unique=False)

    op.create_table(
        "link_chat",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "link_id", name="pk_link_chat"),
    )
    op.create_index("idx_link_chat_chat_id", "link_chat", ["chat_id"], unique=False)
    op.create_index("idx_link_chat_link_id", "link_chat", ["link_id"], unique=False)

    op.create_table(
        "link_tag",
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id", "tag_name", name="pk_link_tag"),
    )
    op.create_index("idx_link_tag_link_id", "link_tag", ["link_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_link_tag_link_id", table_name="link_tag")
    op.drop_table("link_tag")
    op.drop_index("idx_link_chat_link_id", table_name="link_chat")
    op.drop_index("idx_link_chat_chat_id", table_name="link_chat")
    op.drop_table("link_chat")
    op.drop_index("idx_links_url", table_name="links")
    op.drop_table("links")
    op.drop_index("idx_chats_chat_id", table_name="chats")
    op.drop_table("chats")
