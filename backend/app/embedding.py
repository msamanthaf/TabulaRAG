from sentence_transformers import SentenceTransformer
import numpy as np
from .settings import settings

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBED_MODEL)
    return _model

def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vecs = model.encode(texts, batch_size=settings.EMBED_BATCH_SIZE, normalize_embeddings=True)
    if isinstance(vecs, np.ndarray):
        return vecs.astype("float32").tolist()
    return [v.astype("float32").tolist() for v in vecs]
