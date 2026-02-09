from pydantic import BaseModel, Field
from typing import Any, Optional

class UploadResponse(BaseModel):
    table_id: str
    name: str
    columns: list[dict]
    row_count: int

class TableSummary(BaseModel):
    table_id: str
    name: str
    original_filename: str
    created_at: str
    row_count: int
    col_count: int

class SliceResponse(BaseModel):
    table_id: str
    columns: list[str]
    rows: list[dict]

class QueryRequest(BaseModel):
    table_id: str
    query: str = Field(min_length=1)
    top_k: int = 5

class Citation(BaseModel):
    table_id: str
    range: dict
    evidence: list[dict]
    confidence: float = 0.0

class QueryResponse(BaseModel):
    query: str
    table_id: str
    tool_text: str
    citations: list[Citation]
    highlight_id: str
    highlight_url: str
    debug: Optional[dict] = None

class HighlightResponse(BaseModel):
    highlight_id: str
    table_id: str
    payload: dict
