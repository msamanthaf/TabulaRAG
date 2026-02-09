import re
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .embedding import embed_texts
from .rrf import rrf_fuse
from .settings import settings

QDRANT_COLLECTION_PREFIX = "table_rows_"

def qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL)

def ensure_collection(table_id: str, vector_size: int) -> str:
    client = qdrant_client()
    name = QDRANT_COLLECTION_PREFIX + table_id.replace("-", "")
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )
    return name

def upsert_embeddings(table_id: str, row_ids: list[str], row_indices: list[int], row_texts: list[str]) -> None:
    vectors = embed_texts(row_texts)
    vector_size = len(vectors[0]) if vectors else 384
    cname = ensure_collection(table_id, vector_size)

    client = qdrant_client()
    points = []
    for rid, rix, v, txt in zip(row_ids, row_indices, vectors, row_texts):
        points.append(
            qm.PointStruct(
                id=rid,
                vector=v,
                payload={
                    "table_id": table_id,
                    "row_index": rix,
                    "text": txt[:2000],
                },
            )
        )
    client.upsert(collection_name=cname, points=points)

def _extract_code_tokens(q: str) -> list[str]:
    # tokens that look like IDs/codes; tweak later
    # keep long alnum strings + strings containing digits + letters
    toks = re.findall(r"[A-Za-z0-9#_-]{4,}", q)
    out = []
    for t in toks:
        has_alpha = any(ch.isalpha() for ch in t)
        has_digit = any(ch.isdigit() for ch in t)
        if has_alpha and (has_digit or "#" in t or "_" in t or "-" in t):
            out.append(t)
    return out[:5]

def lexical_search(db: Session, table_id: str, query: str, limit: int = 20) -> list[tuple[str, float]]:
    """
    Uses Postgres full-text for general keywords + ILIKE boosts for code tokens.
    Returns list of (row_id, score)
    """
    code_tokens = _extract_code_tokens(query)

    # We use a simple rank; you can upgrade to websearch_to_tsquery, trigram, etc.
    sql = """
    WITH base AS (
      SELECT
        id,
        row_text,
        ts_rank_cd(to_tsvector('simple', row_text), plainto_tsquery('simple', :q)) AS ts_rank
      FROM table_rows
      WHERE table_id = :table_id
      ORDER BY ts_rank DESC
      LIMIT :lim
    )
    SELECT
      id,
      (ts_rank
        + :code_boost * (
            CASE
              WHEN :has_codes = 1 AND ({code_ilike_clause}) THEN 1
              ELSE 0
            END
          )
      ) AS score
    FROM base
    ORDER BY score DESC
    LIMIT :lim;
    """

    if code_tokens:
        ilikes = " OR ".join([f"row_text ILIKE :c{i}" for i in range(len(code_tokens))])
        has_codes = 1
    else:
        ilikes = "FALSE"
        has_codes = 0

    sql = sql.format(code_ilike_clause=ilikes)
    params: dict[str, Any] = {
        "q": query,
        "table_id": table_id,
        "lim": limit,
        "code_boost": 0.7,
        "has_codes": has_codes,
    }
    for i, t in enumerate(code_tokens):
        params[f"c{i}"] = f"%{t}%"

    rows = db.execute(text(sql), params).fetchall()
    return [(r[0], float(r[1] or 0.0)) for r in rows if (r[1] or 0) > 0]

def vector_search(table_id: str, query: str, limit: int = 20) -> list[tuple[str, float]]:
    client = qdrant_client()
    qvec = embed_texts([query])[0]

    cname = QDRANT_COLLECTION_PREFIX + table_id.replace("-", "")
    # if collection doesn't exist, return empty
    existing = [c.name for c in client.get_collections().collections]
    if cname not in existing:
        return []

    res = client.search(
        collection_name=cname,
        query_vector=qvec,
        limit=limit,
        with_payload=False,
    )
    return [(str(p.id), float(p.score)) for p in res]

def pick_columns_for_highlight(query: str, columns: list[str], row: dict) -> list[str]:
    """
    MVP heuristic locator:
    - if query mentions a column name, include it
    - otherwise pick columns whose cell values overlap most with query tokens
    """
    q = query.lower()
    q_tokens = set(re.findall(r"[a-z0-9]+", q))

    explicit = []
    for c in columns:
        if c.lower() in q:
            explicit.append(c)

    if explicit:
        return explicit[:6]

    scored = []
    for c in columns:
        v = str(row.get(c, "")).lower()
        v_tokens = set(re.findall(r"[a-z0-9]+", v))
        score = len(q_tokens & v_tokens)
        scored.append((c, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    best = [c for c, s in scored if s > 0][:6]
    return best if best else columns[: min(6, len(columns))]

def hybrid_query(db: Session, table_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    v = vector_search(table_id, query, limit=max(20, top_k * 10))
    l = lexical_search(db, table_id, query, limit=max(20, top_k * 10))

    v_ids = [rid for rid, _ in v]
    l_ids = [rid for rid, _ in l]

    fused = rrf_fuse([v_ids, l_ids], k=60)
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[: max(10, top_k)]

    best_ids = [rid for rid, _ in ranked]
    if not best_ids:
        return {"rows": [], "debug": {"vector": v[:5], "lexical": l[:5]}}

    # fetch rows
    sql = text("""
      SELECT id, row_index, row_json, row_text
      FROM table_rows
      WHERE table_id = :table_id AND id = ANY(:ids)
    """)
    fetched = db.execute(sql, {"table_id": table_id, "ids": best_ids}).fetchall()
    by_id = {r[0]: {"row_id": r[0], "row_index": r[1], "row_json": r[2], "row_text": r[3]} for r in fetched}

    ordered = [by_id[rid] for rid in best_ids if rid in by_id]

    return {
        "rows": ordered,
        "debug": {
            "vector_top": v[:5],
            "lexical_top": l[:5],
            "rrf_top": ranked[:5],
        },
    }
