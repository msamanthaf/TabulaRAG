from typing import Any
from sqlalchemy import select
from mcp.server.fastmcp import FastMCP

from .db import SessionLocal
from .models import Table, Row

mcp = FastMCP("TabulaRAG")


@mcp.tool()
def ping() -> dict:
    return {"status": "ok"}


@mcp.tool()
def list_tables() -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.execute(select(Table).order_by(Table.created_at.desc())).scalars().all()
        return [
            {
                "table_id": str(t.id),
                "name": t.name,
                "original_filename": t.original_filename,
                "created_at": t.created_at.isoformat(),
                "row_count": t.row_count,
                "col_count": t.col_count,
            }
            for t in rows
        ]
    finally:
        db.close()


@mcp.tool()
def get_table_slice(
    table_id: str,
    offset: int = 0,
    limit: int = 50,
    cols: list[str] | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        t = db.get(Table, table_id)
        if not t:
            raise ValueError("Table not found")

        wanted_cols = cols or None

        q = (
            select(Row)
            .where(Row.table_id == t.id)
            .order_by(Row.row_index.asc())
            .offset(max(0, offset))
            .limit(max(1, limit))
        )
        rows = db.execute(q).scalars().all()

        def project(r: Row):
            d = r.data
            if wanted_cols:
                d = {k: d.get(k) for k in wanted_cols}
            return {"row_index": r.row_index, "data": d}

        return {
            "table_id": table_id,
            "columns": wanted_cols or t.columns,
            "offset": max(0, offset),
            "limit": max(1, limit),
            "rows": [project(r) for r in rows],
            "row_count": t.row_count,
        }
    finally:
        db.close()
