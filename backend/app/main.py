import os
import re
import threading
import uuid
from urllib.parse import quote
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlalchemy.orm import Session
from sqlalchemy import select, desc, asc, func, cast, Float, or_, delete

from .db import Base, engine, get_db, SessionLocal
from .models import Table, Row, Highlight, Job
from .ingest import ingest_csv_job, resume_embedding_job
from .vector_store import vector_search
from .mcp_server import mcp

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
VIEWER_BASE = os.getenv("VIEWER_BASE", "http://localhost:5173")
GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED", "true").lower() in ("1", "true", "yes")
GUARDRAILS_MIN_TOKEN_MATCH = int(os.getenv("GUARDRAILS_MIN_TOKEN_MATCH", "1"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    _resume_pending_jobs()
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Table RAG MVP", lifespan=lifespan)

# Allow local frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/mcp-status")
def mcp_status():
    return {"status": "online"}

def _resume_pending_jobs():
    db = SessionLocal()
    try:
        pending = db.execute(
            select(Job).where(Job.status.in_(["running", "indexing"]))
        ).scalars().all()
        for job in pending:
            if not job.table_id:
                job.status = "error"
                job.progress = 100
                job.message = "Interrupted before table creation."
                db.commit()
                continue
            # Resume embedding in a background thread
            threading.Thread(target=resume_embedding_job, args=(job.id,), daemon=True).start()
    finally:
        db.close()

app.mount("/mcp", mcp.streamable_http_app())

class UploadResponse(BaseModel):
    job_id: str
    message: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    table_id: Optional[str] = None

class TableInfo(BaseModel):
    table_id: str
    name: str
    original_filename: str
    created_at: str
    row_count: int
    col_count: int

class QueryRequest(BaseModel):
    query: str
    table_id: Optional[str] = None
    top_k: int = 1

class RenameTableRequest(BaseModel):
    name: str

class EvidenceCell(BaseModel):
    row: int
    col: str
    value: Any

class Citation(BaseModel):
    table_id: str
    range: Dict[str, Any]
    evidence: List[EvidenceCell]
    confidence: float = 0.5

class QueryResponse(BaseModel):
    query: str
    table_id: str
    tool_text: str
    citations: List[Citation]
    highlight_id: str
    highlight_url: str

def _latest_table(db: Session) -> Table:
    t = db.execute(select(Table).order_by(desc(Table.created_at)).limit(1)).scalar_one_or_none()
    if not t:
        raise HTTPException(400, "No tables uploaded yet.")
    return t

def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())

def _intent_from_query(query: str, table: Table):
    tokens = _tokens(query)
    want_shortest = "shortest" in tokens
    want_positive = "positive" in tokens
    want_negative = "negative" in tokens
    has_review = "review" in (table.columns or [])
    has_sentiment = "sentiment" in (table.columns or [])
    return {
        "tokens": tokens,
        "want_shortest": want_shortest,
        "want_positive": want_positive,
        "want_negative": want_negative,
        "has_review": has_review,
        "has_sentiment": has_sentiment,
    }

def _row_matches_tokens(tokens: List[str], row_text: str) -> bool:
    if not tokens:
        return True
    hits = 0
    lt = row_text.lower() if row_text else ""
    for tok in tokens:
        if len(tok) < 3:
            continue
        if tok in lt:
            hits += 1
    return hits >= GUARDRAILS_MIN_TOKEN_MATCH

@app.get("/tables", response_model=List[TableInfo])
def list_tables(db: Session = Depends(get_db)):
    rows = db.execute(select(Table).order_by(desc(Table.created_at))).scalars().all()
    out = []
    for t in rows:
        out.append(
            TableInfo(
                table_id=str(t.id),
                name=t.name,
                original_filename=t.original_filename,
                created_at=t.created_at.isoformat(),
                row_count=t.row_count,
                col_count=t.col_count,
            )
        )
    return out

@app.delete("/tables/{table_id}")
def delete_table(table_id: str, db: Session = Depends(get_db)):
    t = db.get(Table, table_id)
    if not t:
        raise HTTPException(404, "Table not found")

    db.execute(delete(Row).where(Row.table_id == t.id))
    db.execute(delete(Highlight).where(Highlight.table_id == t.id))
    db.execute(delete(Job).where(Job.table_id == t.id))
    db.delete(t)
    db.commit()

    return {"ok": True, "table_id": table_id}

@app.patch("/tables/{table_id}", response_model=TableInfo)
def rename_table(table_id: str, req: RenameTableRequest, db: Session = Depends(get_db)):
    t = db.get(Table, table_id)
    if not t:
        raise HTTPException(404, "Table not found")
    if not req.name.strip():
        raise HTTPException(400, "Name cannot be empty")
    t.name = req.name.strip()
    db.commit()
    db.refresh(t)
    return TableInfo(
        table_id=str(t.id),
        name=t.name,
        original_filename=t.original_filename,
        created_at=t.created_at.isoformat(),
        row_count=t.row_count,
        col_count=t.col_count,
    )

@app.post("/upload", response_model=UploadResponse)
async def upload_csv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    table_name: str | None = Query(None, alias="name"), 
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv supported in this MVP")

    job = Job()
    db.add(job)
    db.commit()
    db.refresh(job)

    job_id = str(job.id)
    table_name = table_name or os.path.splitext(file.filename)[0]

    filepath = os.path.join(UPLOAD_DIR, f"{job_id}.csv")
    with open(filepath, "wb") as f:
        f.write(await file.read())

    # run ingestion in background (still single-process, but non-blocking)
    def run_job():
        local_db = SessionLocal()
        try:
            ingest_csv_job(local_db, job_id, filepath, file.filename, table_name)
        finally:
            local_db.close()

    background.add_task(run_job)

    return UploadResponse(job_id=job_id, message="Upload accepted. Indexing started.")

@app.post("/tables/{table_id}/reindex", response_model=UploadResponse)
def reindex_table(table_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    t = db.get(Table, table_id)
    if not t:
        raise HTTPException(404, "Table not found")

    job = Job(status="indexing", progress=60, message="Reindexing...")
    job.table_id = t.id
    db.add(job)
    db.commit()
    db.refresh(job)

    background.add_task(resume_embedding_job, job.id)
    return UploadResponse(job_id=str(job.id), message="Reindex started.")

@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        message=job.message,
        table_id=str(job.table_id) if job.table_id else None,
    )

@app.get("/tables/{table_id}/slice")
def get_table_slice(
    table_id: str,
    offset: int = 0,
    limit: int = 200,
    cols: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # Efficient paging for 50k: only fetch the rows you need
    t = db.get(Table, table_id)
    if not t:
        raise HTTPException(404, "Table not found")

    wanted_cols = None
    if cols:
        wanted_cols = [c.strip() for c in cols.split(",") if c.strip()]

    q = (
        select(Row)
        .where(Row.table_id == t.id)
        .order_by(Row.row_index.asc())
        .offset(offset)
        .limit(limit)
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
        "offset": offset,
        "limit": limit,
        "rows": [project(r) for r in rows],
        "row_count": t.row_count,
    }

@app.post("/query", response_model=QueryResponse)
def query_table_rag(req: QueryRequest, db: Session = Depends(get_db)):
    # Default table: latest
    if req.table_id:
        t = db.get(Table, req.table_id)
        if not t:
            raise HTTPException(404, "Table not found")
    else:
        t = _latest_table(db)

    intent = _intent_from_query(req.query, t)

    def structured_shortest_query():
        if not intent["want_shortest"] or not intent["has_review"]:
            return []
        q = select(Row.row_index).where(Row.table_id == t.id)
        if intent["want_positive"] and intent["has_sentiment"]:
            q = q.where(func.lower(Row.data["sentiment"].astext) == "positive")
        elif intent["want_negative"] and intent["has_sentiment"]:
            q = q.where(func.lower(Row.data["sentiment"].astext) == "negative")
        q = q.order_by(func.length(Row.data["review"].astext).asc(), Row.row_index.asc()).limit(req.top_k)
        return [r[0] for r in db.execute(q).all()]

    # Guardrail: if the query is clearly a "shortest" request, use deterministic SQL first
    row_indices = structured_shortest_query()

    if not row_indices:
        # Vector search -> row indices
        row_indices = vector_search(str(t.id), req.query, top_k=max(req.top_k * 3, 10))
        row_indices = list(dict.fromkeys(row_indices))  # stable unique

    # Fallback: if vector search yields nothing (e.g., embeddings not ready), do a lightweight DB search
    if not row_indices:
        tokens = intent["tokens"]
        # Basic keyword search over row_text
        keywords = [t for t in tokens if len(t) >= 3]
        if keywords:
            conds = [Row.row_text.ilike(f"%{tok}%") for tok in keywords]
            q = select(Row.row_index).where(Row.table_id == t.id).where(or_(*conds))
            if intent["want_positive"] and intent["has_sentiment"]:
                q = q.where(func.lower(Row.data["sentiment"].astext) == "positive")
            elif intent["want_negative"] and intent["has_sentiment"]:
                q = q.where(func.lower(Row.data["sentiment"].astext) == "negative")
            q = q.order_by(Row.row_index.asc()).limit(max(req.top_k * 3, 10))
            row_indices = [r[0] for r in db.execute(q).all()]

    # Fetch rows
    q = select(Row).where(Row.table_id == t.id, Row.row_index.in_(row_indices))
    found = {r.row_index: r for r in db.execute(q).scalars().all()}

    # Build citations (filter null-only rows)
    citations: List[Citation] = []
    for idx in row_indices:
        r = found.get(idx)
        if not r:
            continue

        if intent["has_sentiment"]:
            s = str(r.data.get("sentiment", "")).lower()
            if intent["want_positive"] and s != "positive":
                continue
            if intent["want_negative"] and s != "negative":
                continue

        # Guardrail: require some token overlap for non-empty queries
        if GUARDRAILS_ENABLED and not _row_matches_tokens(intent["tokens"], r.row_text):
            continue

        # Prefer key columns first
        ev: List[EvidenceCell] = []
        for col in ["review", "sentiment"]:
            if col in r.data and r.data.get(col) is not None:
                ev.append(EvidenceCell(row=idx, col=col, value=r.data.get(col)))
        # Fill the rest
        for col, val in r.data.items():
            if val is None:
                continue
            if any(e.col == col for e in ev):
                continue
            ev.append(EvidenceCell(row=idx, col=col, value=val))
            if len(ev) >= 6:
                break

        if not ev:
            continue

        cols = [e.col for e in ev]
        citations.append(
            Citation(
                table_id=str(t.id),
                range={"rows": [idx], "cols": cols},
                evidence=ev,
                confidence=0.5,
            )
        )
        if len(citations) >= req.top_k:
            break

    # Guardrail: if sentiment requested but not satisfied, fallback to deterministic query
    if GUARDRAILS_ENABLED and citations and intent["has_sentiment"]:
        def _has_sentiment(c: Citation, target: str) -> bool:
            for e in c.evidence:
                if e.col == "sentiment" and str(e.value).lower() == target:
                    return True
            return False

        if intent["want_positive"] and not any(_has_sentiment(c, "positive") for c in citations):
            row_indices = structured_shortest_query() or row_indices
        elif intent["want_negative"] and not any(_has_sentiment(c, "negative") for c in citations):
            row_indices = structured_shortest_query() or row_indices

        # Rebuild citations after fallback
        if row_indices and (intent["want_positive"] or intent["want_negative"]):
            q = select(Row).where(Row.table_id == t.id, Row.row_index.in_(row_indices))
            found = {r.row_index: r for r in db.execute(q).scalars().all()}
            citations = []
            for idx in row_indices:
                r = found.get(idx)
                if not r:
                    continue
                ev: List[EvidenceCell] = []
                for col in ["review", "sentiment"]:
                    if col in r.data and r.data.get(col) is not None:
                        ev.append(EvidenceCell(row=idx, col=col, value=r.data.get(col)))
                for col, val in r.data.items():
                    if val is None or any(e.col == col for e in ev):
                        continue
                    ev.append(EvidenceCell(row=idx, col=col, value=val))
                    if len(ev) >= 6:
                        break
                if not ev:
                    continue
                cols = [e.col for e in ev]
                citations.append(
                    Citation(
                        table_id=str(t.id),
                        range={"rows": [idx], "cols": cols},
                        evidence=ev,
                        confidence=0.5,
                    )
                )
                if len(citations) >= req.top_k:
                    break

    # Create highlight
    highlight_id = f"hl_{uuid.uuid4().hex[:16]}"
    hl_rows = [c.range["rows"][0] for c in citations] if citations else []
    hl_cols = list({cname for c in citations for cname in c.range["cols"]}) if citations else []

    hl = Highlight(
        id=highlight_id,
        table_id=t.id,
        rows=hl_rows or [],
        cols=hl_cols or [],
        evidence=[c.model_dump() for c in citations],
    )
    db.add(hl)
    db.commit()

    # Tool text
    if citations:
        lines = [f"Top matches from table '{t.name}' (table_id={t.id}):", ""]
        for c in citations:
            ridx = c.range["rows"][0]
            lines.append(f"- row(s) [{ridx}] cols {c.range['cols']}")
            for e in c.evidence:
                lines.append(f"  • {e.col}: {e.value}")
        lines.append("")
    else:
        lines = [f"No matches found in table '{t.name}' for query: {req.query}", ""]

    highlight_url = f"{VIEWER_BASE}/highlight/{highlight_id}?q={quote(req.query)}"
    lines.append(f"Open highlight: {highlight_url}")

    return QueryResponse(
        query=req.query,
        table_id=str(t.id),
        tool_text="\n".join(lines),
        citations=citations,
        highlight_id=highlight_id,
        highlight_url=highlight_url,
    )

@app.get("/highlights/{highlight_id}")
def get_highlight(highlight_id: str, db: Session = Depends(get_db)):
    hl = db.get(Highlight, highlight_id)
    if not hl:
        raise HTTPException(404, "Highlight not found")
    return {
        "highlight_id": hl.id,
        "table_id": str(hl.table_id),
        "rows": hl.rows,
        "cols": hl.cols,
        "evidence": hl.evidence,
        "created_at": hl.created_at.isoformat(),
    }

class RankRequest(BaseModel):
    table_id: str | None = None
    primary_col: str
    primary_dir: str = "desc"          # "asc" or "desc"
    tie_col: str | None = None
    tie_dir: str = "asc"              # "asc" or "desc"
    limit: int = 1

@app.post("/rank")
def rank_rows(req: RankRequest, db: Session = Depends(get_db)):
    # default to latest table if not provided
    if req.table_id:
        t = db.get(Table, req.table_id)
        if not t:
            raise HTTPException(404, "Table not found")
    else:
        t = _latest_table(db)

    def num_expr(col: str):
        # (data->>'col')::float with empty-string protection
        return cast(func.nullif(Row.data[col].astext, ""), Float)

    p = num_expr(req.primary_col)
    q = select(Row).where(Row.table_id == t.id, p.isnot(None))

    order = desc(p) if req.primary_dir.lower() == "desc" else asc(p)

    if req.tie_col:
        tie = num_expr(req.tie_col)
        q = q.where(tie.isnot(None))
        tie_order = desc(tie) if req.tie_dir.lower() == "desc" else asc(tie)
        q = q.order_by(order, tie_order)
    else:
        q = q.order_by(order)

    q = q.limit(req.limit)
    rows = db.execute(q).scalars().all()
    if not rows:
        return {"message": "No rows matched ranking criteria."}

    r = rows[0]
    # build a tiny citation + highlight (reuse your existing Highlight logic)
    # cite only the relevant cells:
    ev = []
    ev.append({"row": r.row_index, "col": req.primary_col, "value": r.data.get(req.primary_col)})
    if req.tie_col:
        ev.append({"row": r.row_index, "col": req.tie_col, "value": r.data.get(req.tie_col)})

    highlight_id = f"hl_{uuid.uuid4().hex[:16]}"
    hl = Highlight(
        id=highlight_id,
        table_id=t.id,
        rows=[r.row_index],
        cols=[req.primary_col] + ([req.tie_col] if req.tie_col else []),
        evidence=[{"table_id": str(t.id), "range": {"rows":[r.row_index], "cols":[e["col"] for e in ev]}, "evidence": ev, "confidence": 0.7}],
    )
    db.add(hl)
    db.commit()

    highlight_url = f"{VIEWER_BASE}/highlight/{highlight_id}"
    return {
        "table_id": str(t.id),
        "row_index": r.row_index,
        "values": {req.primary_col: r.data.get(req.primary_col), **({req.tie_col: r.data.get(req.tie_col)} if req.tie_col else {})},
        "highlight_url": highlight_url,
        "citations": hl.evidence,
    }
