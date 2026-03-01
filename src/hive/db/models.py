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
    UniqueConstraint,
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
    length: Mapped[int] = mapped_column(Integer)
    topology: Mapped[str] = mapped_column(Text)  # 'circular' | 'linear'
    sequence: Mapped[str] = mapped_column(Text)
    sequence_hash: Mapped[str] = mapped_column(Text, default="")
    molecule: Mapped[str] = mapped_column(Text, default="DNA")  # DNA | RNA | protein
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    file: Mapped[IndexedFile] = relationship(back_populates="sequences")
    part_instances: Mapped[list["PartInstance"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan"
    )

    @property
    def size_bp(self) -> int:
        return self.length

    __table_args__ = (
        Index("idx_seq_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_seq_meta", "meta", postgresql_using="gin"),
        Index("idx_seq_hash", "sequence_hash"),
    )


# ── Part system ──────────────────────────────────────────────────


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    sequence_hash: Mapped[str] = mapped_column(Text, unique=True, index=True)
    sequence: Mapped[str] = mapped_column(Text)
    molecule: Mapped[str] = mapped_column(Text)  # DNA | RNA | AA
    length: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    names: Mapped[list["PartName"]] = relationship(back_populates="part", cascade="all, delete-orphan")
    instances: Mapped[list["PartInstance"]] = relationship(back_populates="part", cascade="all, delete-orphan")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="part", cascade="all, delete-orphan")
    library_members: Mapped[list["LibraryMember"]] = relationship(back_populates="part", cascade="all, delete-orphan")


class PartName(Base):
    __tablename__ = "part_names"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # "file" | "manual" | "external"
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    part: Mapped[Part] = relationship(back_populates="names")

    __table_args__ = (
        UniqueConstraint("part_id", "name", "source", name="uq_part_name_source"),
        Index("idx_partname_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
    )


class PartInstance(Base):
    __tablename__ = "part_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    seq_id: Mapped[int] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"))
    annotation_type: Mapped[str] = mapped_column(Text)  # "CDS", "promoter", "primer_bind", etc.
    start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strand: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    qualifiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    part: Mapped[Part] = relationship(back_populates="instances")
    sequence: Mapped[Sequence] = relationship(back_populates="part_instances")

    __table_args__ = (
        Index("idx_pi_seq_start", "seq_id", "start"),
        Index("idx_pi_part", "part_id"),
    )


# ── Libraries ────────────────────────────────────────────────────


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    source: Mapped[str] = mapped_column(Text)  # "native" | "manual"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list["LibraryMember"]] = relationship(back_populates="library", cascade="all, delete-orphan")


class LibraryMember(Base):
    __tablename__ = "library_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="CASCADE"))
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))

    library: Mapped[Library] = relationship(back_populates="members")
    part: Mapped[Part] = relationship(back_populates="library_members")

    __table_args__ = (
        UniqueConstraint("library_id", "part_id", name="uq_library_part"),
    )


# ── Annotations ──────────────────────────────────────────────────


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # "native" | "manual" | "external"

    part: Mapped[Part] = relationship(back_populates="annotations")

    __table_args__ = (
        Index("idx_annotation_part_key", "part_id", "key"),
    )


# ── Feedback & Tool Approvals ────────────────────────────────────


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
