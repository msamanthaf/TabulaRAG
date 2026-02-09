import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Table(Base):
    __tablename__ = "tables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    col_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    columns: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

class Row(Base):
    __tablename__ = "rows"

    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tables.id"), primary_key=True)
    row_index: Mapped[int] = mapped_column(Integer, primary_key=True)

    data: Mapped[dict] = mapped_column(JSONB, nullable=False)      # {col: value}
    row_text: Mapped[str] = mapped_column(Text, nullable=False)    # for lexical search / debugging

class Highlight(Base):
    __tablename__ = "highlights"

    id: Mapped[str] = mapped_column(String, primary_key=True)      # "hl_xxx"
    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    rows: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    cols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)  # queued|running|indexing|done|error
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)     # 0..100
    message: Mapped[str] = mapped_column(String, default="", nullable=False)

    table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
