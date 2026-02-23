"""SQLAlchemy models — hybrid schema with JSON/JSONB meta.

Uses generic JSON type for cross-DB compatibility (SQLite in tests).
The Alembic migration uses PostgreSQL JSONB explicitly for production.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IndexedFile(Base):
    __tablename__ = "indexed_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True)
    file_hash: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)  # 'dna' | 'gb' | 'fasta' | 'zrt'
    status: Mapped[str] = mapped_column(Text, default="active")  # 'active' | 'deleted' | 'error'
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    file_mtime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sequences: Mapped[list["Sequence"]] = relationship(back_populates="file", cascade="all")


class Sequence(Base):
    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("indexed_files.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    size_bp: Mapped[int] = mapped_column(Integer)
    topology: Mapped[str] = mapped_column(Text)  # 'circular' | 'linear'
    sequence: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    file: Mapped[IndexedFile] = relationship(back_populates="sequences")
    features: Mapped[list["Feature"]] = relationship(back_populates="sequence", cascade="all")
    primers: Mapped[list["Primer"]] = relationship(back_populates="sequence_ref", cascade="all")

    __table_args__ = (
        Index("idx_seq_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_seq_meta", "meta", postgresql_using="gin"),
    )


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    seq_id: Mapped[int] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)  # SO term: CDS, promoter, terminator...
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    strand: Mapped[int] = mapped_column(SmallInteger)  # +1 or -1
    qualifiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    sequence: Mapped[Sequence] = relationship(back_populates="features")

    __table_args__ = (
        Index("idx_feat_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_feat_type", "type"),
    )


class Primer(Base):
    __tablename__ = "primers"

    id: Mapped[int] = mapped_column(primary_key=True)
    seq_id: Mapped[int] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    sequence: Mapped[str] = mapped_column(Text)
    tm: Mapped[float | None] = mapped_column(nullable=True)
    start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strand: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    sequence_ref: Mapped[Sequence] = relationship(back_populates="primers")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chat_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[str] = mapped_column(Text, nullable=False)  # 'good' | 'bad'
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship()

    __table_args__ = (
        Index("idx_feedback_user", "user_id"),
    )


class ToolApproval(Base):
    __tablename__ = "tool_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="quarantined")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
