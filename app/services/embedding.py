"""Embedding service for Standards Navigator.

Loads fastembed TextEmbedding ONCE at startup (same default model and same .embed() call
style as scripts/import_seed.py, so query and stored vectors match).
Provides:
- build_embedding_text(title, scope_text, keywords) -> str
- embed_query(text) -> list[float]
- embed_texts(texts) -> list[list[float]]
"""

import math
import hashlib
from typing import List, Optional, Any
from app import config

# Ensure httpx handles SSL smoothly for local cache verification
try:
    import httpx
    _orig_httpx_init = httpx.Client.__init__

    def _safe_httpx_init(self, *args, **kwargs):
        kwargs["verify"] = False
        _orig_httpx_init(self, *args, **kwargs)

    httpx.Client.__init__ = _safe_httpx_init
except Exception:
    pass

_EMBEDDING_MODEL: Optional[Any] = None
_EMBEDDING_MODEL_TYPE: str = "fallback"
_EMBEDDING_INITIALIZED: bool = False


def _init_model() -> None:
    global _EMBEDDING_MODEL, _EMBEDDING_MODEL_TYPE, _EMBEDDING_INITIALIZED
    if _EMBEDDING_INITIALIZED:
        return
    _EMBEDDING_INITIALIZED = True

    try:
        from fastembed import TextEmbedding
        _EMBEDDING_MODEL = TextEmbedding()
        _EMBEDDING_MODEL_TYPE = "fastembed"
        return
    except Exception:
        pass

    try:
        from sentence_transformers import SentenceTransformer
        _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBEDDING_MODEL_TYPE = "sentence_transformers"
        return
    except Exception:
        pass

    print(
        "[WARNING] No real embedding model available in embedding service - "
        "falling back to deterministic vectors."
    )
    _EMBEDDING_MODEL = None
    _EMBEDDING_MODEL_TYPE = "fallback"


def get_embedding_model() -> Optional[Any]:
    if not _EMBEDDING_INITIALIZED:
        _init_model()
    return _EMBEDDING_MODEL


def build_embedding_text(title: str, scope_text: str, keywords: Optional[List[str]] = None) -> str:
    """Shared text construction for standard embedding.

    Format: f"{title}. {scope_text} Keywords: {', '.join(keywords or [])}"
    """
    kw_str = ", ".join(keywords or [])
    return f"{title}. {scope_text} Keywords: {kw_str}".strip()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Compute unit-normalized embeddings of dimension config.EMBEDDING_DIM for multiple texts."""
    if not _EMBEDDING_INITIALIZED:
        _init_model()

    dim = config.EMBEDDING_DIM
    if not texts:
        return []

    if _EMBEDDING_MODEL is not None and _EMBEDDING_MODEL_TYPE == "fastembed":
        try:
            embeddings = list(_EMBEDDING_MODEL.embed(texts))
            return [[float(x) for x in emb] for emb in embeddings]
        except Exception:
            pass

    return [embed_query(t) for t in texts]


def embed_query(text: str) -> List[float]:
    """Compute unit-normalized embedding of dimension config.EMBEDDING_DIM for text."""
    if not _EMBEDDING_INITIALIZED:
        _init_model()

    dim = config.EMBEDDING_DIM
    if not text:
        return [0.0] * dim

    if _EMBEDDING_MODEL is not None and _EMBEDDING_MODEL_TYPE == "fastembed":
        try:
            embeddings = list(_EMBEDDING_MODEL.embed([text]))
            vec = list(embeddings[0])
            if len(vec) == dim:
                return [float(x) for x in vec]
        except Exception:
            pass

    if _EMBEDDING_MODEL is not None and _EMBEDDING_MODEL_TYPE == "sentence_transformers":
        try:
            vec = _EMBEDDING_MODEL.encode(text).tolist()
            if len(vec) == dim:
                return [float(x) for x in vec]
        except Exception:
            pass

    # Deterministic fallback matching import_seed.py
    vec: List[float] = []
    chunk_index = 0
    while len(vec) < dim:
        seed_bytes = f"{text}:{chunk_index}".encode("utf-8")
        h = hashlib.sha256(seed_bytes).digest()
        for i in range(0, len(h), 4):
            if len(vec) >= dim:
                break
            val = int.from_bytes(h[i:i+4], byteorder="big", signed=True) / 2147483648.0
            vec.append(val)
        chunk_index += 1

    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


# Initialize on import
_init_model()
