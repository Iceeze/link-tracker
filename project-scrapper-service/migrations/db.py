from datetime import datetime
from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    String,
    Text,
    ForeignKey,
    Table,
    DateTime,
    func,
    PrimaryKeyConstraint,
    Column,
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


link_chat = Table(
    "link_chat",
    Base.metadata,
    Column(
        "chat_id",
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
    Column(
        "link_id",
        BigInteger,
        ForeignKey("links.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    PrimaryKeyConstraint("chat_id", "link_id", name="pk_link_chat"),
)

link_tag = Table(
    "link_tag",
    Base.metadata,
    Column("chat_id", BigInteger, primary_key=True),
    Column("link_id", BigInteger, primary_key=True),
    Column("tag_name", String(255), primary_key=True, nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    ForeignKeyConstraint(
        ["chat_id", "link_id"],
        ["link_chat.chat_id", "link_chat.link_id"],
        ondelete="CASCADE",
    ),
    PrimaryKeyConstraint("chat_id", "link_id", "tag_name", name="pk_link_tag"),
)


class Chat(Base):
    """Модель чата Telegram."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    links: Mapped[list["Link"]] = relationship(
        "Link", secondary=link_chat, back_populates="chats"
    )


class Link(Base):
    """Модель отслеживаемой ссылки."""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chats: Mapped[list["Chat"]] = relationship(
        "Chat", secondary=link_chat, back_populates="links"
    )
