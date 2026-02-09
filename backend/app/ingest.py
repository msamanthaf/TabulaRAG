import csv
import os
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session
from psycopg.types.json import Json

from .models import Table, Row, Job
from .db import engine, SessionLocal
from .vector_store import upsert_rows, count_vectors

CHUNK_ROWS = int(os.getenv("INGEST_CHUNK_ROWS", "10000"))
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "128"))
EMBED_SCAN_BATCH = int(os.getenv("EMBED_SCAN_BATCH", "1000"))
EMBED_ON_UPLOAD = os.getenv("EMBED_ON_UPLOAD", "true").lower() in ("1", "true", "yes")

def _normalize_cell(x: Optional[str]) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s if s != "" else None

def _row_to_text(row_dict: Dict[str, Optional[str]], max_chars: int = 2000) -> str:
    parts = []
    total = 0
    for k, v in row_dict.items():
        if v is None:
            continue
        part = f"{k}: {v}"
        total += len(part)
        parts.append(part)
        if total > max_chars:
            break
    return " | ".join(parts) if parts else ""

def _embed_table_rows(db: Session, job: Job, t: Table):
    total_rows = t.row_count or 0
    if total_rows <= 0:
        job.status = "error"
        job.progress = 100
        job.message = "No rows to embed."
        db.commit()
        return

    # If already fully indexed, mark done
    existing = count_vectors(str(t.id))
    if existing >= total_rows:
        job.status = "done"
        job.progress = 100
        job.message = f"Done. Already indexed {existing} rows."
        db.commit()
        return

    job.status = "indexing"
    job.progress = max(job.progress, 60)
    job.message = "Embedding rows..."
    db.commit()

    embedded = 0
    start = 0
    while start < total_rows:
        end = min(total_rows, start + EMBED_SCAN_BATCH)
        rows = db.execute(
            select(Row.row_index, Row.row_text)
            .where(Row.table_id == t.id, Row.row_index >= start, Row.row_index < end)
            .order_by(Row.row_index)
        ).all()
        start = end

        items: List[Tuple[int, str]] = [(r.row_index, r.row_text) for r in rows if r.row_text]
        for i in range(0, len(items), EMBED_BATCH):
            batch = items[i : i + EMBED_BATCH]
            if not batch:
                continue
            upsert_rows(str(t.id), batch)
            embedded += len(batch)
            if total_rows > 0:
                p = 60 + int(39 * (embedded / total_rows))
                job.progress = min(99, p)
                job.message = f"Embedding rows... ({embedded}/{total_rows})"
                db.commit()

    job.status = "done"
    job.progress = 100
    job.message = f"Done. Ingested {total_rows} rows."
    db.commit()

def resume_embedding_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        if not job.table_id:
            job.status = "error"
            job.progress = 100
            job.message = "No table_id to resume."
            db.commit()
            return
        t = db.get(Table, job.table_id)
        if not t:
            job.status = "error"
            job.progress = 100
            job.message = "Table not found for resume."
            db.commit()
            return
        _embed_table_rows(db, job, t)
    except Exception as e:
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = "error"
                job.progress = 100
                job.message = f"Failed: {e}"
                db.commit()
        finally:
            raise
    finally:
        db.close()

def ingest_csv_job(db: Session, job_id: str, filepath: str, original_filename: str, table_name: str):
    job = db.get(Job, job_id)
    if not job:
        return
    try:
        job.status = "running"
        job.progress = 1
        job.message = "Parsing CSV..."
        db.commit()

        file_size = None
        try:
            file_size = os.path.getsize(filepath)
        except OSError:
            file_size = None

        with open(filepath, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                job.status = "error"
                job.message = "Empty CSV"
                job.progress = 100
                db.commit()
                return

            columns = [h.strip() if h else f"col_{i}" for i, h in enumerate(header)]
            t = Table(name=table_name, original_filename=original_filename, columns=columns, col_count=len(columns))
            db.add(t)
            db.commit()
            db.refresh(t)

            job.table_id = t.id
            db.commit()

            row_index = 0

            def bump_progress(p: int, msg: str):
                job.progress = min(99, p)
                job.message = msg
                db.commit()

            bump_progress(5, "Copying rows...")

            # Fast path: COPY into Postgres
            raw_conn = engine.raw_connection()
            try:
                with raw_conn.cursor() as cur:
                    with cur.copy(
                        "COPY rows (table_id, row_index, data, row_text) FROM STDIN"
                    ) as copy:
                        for raw in reader:
                            # pad/truncate to header length
                            if len(raw) < len(columns):
                                raw = raw + [None] * (len(columns) - len(raw))
                            elif len(raw) > len(columns):
                                raw = raw[: len(columns)]

                            row_dict = {columns[i]: _normalize_cell(raw[i]) for i in range(len(columns))}
                            row_text = _row_to_text(row_dict)
                            copy.write_row([t.id, row_index, Json(row_dict), row_text])
                            row_index += 1

                            if row_index % 2000 == 0:
                                bump_progress(min(55, 5 + (row_index // 2000)), f"Copying rows... ({row_index})")
                raw_conn.commit()
            except Exception:
                raw_conn.rollback()
                raise
            finally:
                raw_conn.close()

            # update table stats
            t.row_count = row_index
            db.commit()

            if not EMBED_ON_UPLOAD:
                job.status = "done"
                job.progress = 100
                job.message = f"Done. Ingested {row_index} rows. (Embedding skipped)"
                db.commit()
                return

            _embed_table_rows(db, job, t)
    except Exception as e:
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            job.status = "error"
            job.progress = 100
            job.message = f"Failed: {e}"
            db.commit()
        raise
