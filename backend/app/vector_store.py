import os
import uuid
from typing import Iterable, List, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from fastembed import TextEmbedding

QDRANT_URL = os.getenv("QDRANT_URL", "http://vectordb:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "table_rows")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

_client = QdrantClient(url=QDRANT_URL)
_embedder = TextEmbedding(model_name=EMBED_MODEL)
_vector_dim: int | None = None
_collection_ready = False

def ensure_collection(vector_dim: int):
    global _collection_ready
    if _collection_ready:
        return
    existing = [c.name for c in _client.get_collections().collections]
    if QDRANT_COLLECTION in existing:
        _collection_ready = True
        return

    _client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=qm.VectorParams(size=vector_dim, distance=qm.Distance.COSINE),
    )
    # Useful payload index for filtering
    _client.create_payload_index(
        collection_name=QDRANT_COLLECTION,
        field_name="table_id",
        field_schema=qm.PayloadSchemaType.KEYWORD,
    )
    _collection_ready = True

def embed_texts(texts: List[str]) -> List[List[float]]:
    # fastembed returns numpy arrays; convert to python lists
    vectors = []
    for vec in _embedder.embed(texts):
        vectors.append(vec.tolist())
    return vectors

def _get_vector_dim() -> int:
    global _vector_dim
    if _vector_dim is None:
        _vector_dim = len(embed_texts(["hello"])[0])
    return _vector_dim

def upsert_rows(
    table_id: str,
    items: List[Tuple[int, str]],
):
    # items: [(row_index, row_text)]
    if not items:
        return

    ensure_collection(_get_vector_dim())

    texts = [t for _, t in items]
    vectors = embed_texts(texts)

    points = []
    for (row_index, row_text), vec in zip(items, vectors):
        # stable deterministic id so re-upserts overwrite
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{table_id}:{row_index}"))
        points.append(
            qm.PointStruct(
                id=point_id,
                vector=vec,
                payload={"table_id": table_id, "row_index": row_index, "row_text": row_text},
            )
        )

    _client.upsert(collection_name=QDRANT_COLLECTION, points=points)

def count_vectors(table_id: str) -> int:
    try:
        ensure_collection(_get_vector_dim())
        res = _client.count(
            collection_name=QDRANT_COLLECTION,
            count_filter=qm.Filter(
                must=[qm.FieldCondition(key="table_id", match=qm.MatchValue(value=table_id))]
            ),
            exact=True,
        )
        return int(res.count or 0)
    except Exception:
        return 0

def vector_search(table_id: str, query: str, top_k: int = 10) -> List[int]:
    qvec = embed_texts([query])[0]
    res = _client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=qvec,
        limit=top_k,
        query_filter=qm.Filter(
            must=[qm.FieldCondition(key="table_id", match=qm.MatchValue(value=table_id))]
        ),
    )
    return [int(r.payload["row_index"]) for r in res]
