"""
Embedder service — single entry point for getting embeddings using whatever
provider is configured. Used by semantic ground truth matching, retrieval
helpers, and anywhere else in the backend that needs to encode text.

Lookup order:
    1. The EmbedderConfigRecord row passed in directly
    2. The first row in embedder_configs where is_default = TRUE and is_active = TRUE
    3. Hardcoded fallback: sentence-transformers/all-MiniLM-L6-v2 (local, free)

The fallback means the rest of the system keeps working out of the box even
if the user never visits the Embedder Config page.
"""

import logging
import threading
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.db.models import EmbedderConfigRecord

logger = logging.getLogger("obtrac")

# Caches keyed by (provider, model_id) so we don't reload heavy models
_local_model_cache: dict = {}
_cache_lock = threading.Lock()


def _resolve_embedder(db: Optional[Session], embedder: Optional[EmbedderConfigRecord]) -> Optional[EmbedderConfigRecord]:
    if embedder is not None:
        return embedder
    if db is None:
        return None
    return (
        db.query(EmbedderConfigRecord)
        .filter(EmbedderConfigRecord.is_default == True, EmbedderConfigRecord.is_active == True)
        .first()
    )


def get_embedding(
    text: str,
    *,
    db: Optional[Session] = None,
    embedder: Optional[EmbedderConfigRecord] = None,
) -> list[float]:
    """Encode a single text into a vector. Always succeeds — falls back to
    a local sentence-transformers model if no config is found and no errors."""
    return get_embeddings([text], db=db, embedder=embedder)[0]


def get_embeddings(
    texts: Sequence[str],
    *,
    db: Optional[Session] = None,
    embedder: Optional[EmbedderConfigRecord] = None,
) -> list[list[float]]:
    """Encode many texts. Single point of dispatch by provider."""
    cfg = _resolve_embedder(db, embedder)

    if cfg is None:
        # Fallback: local sentence-transformers
        return _embed_sentence_transformers("all-MiniLM-L6-v2", texts)

    provider = (cfg.provider or "sentence_transformers").lower()
    if provider == "sentence_transformers":
        return _embed_sentence_transformers(cfg.model_id, texts)
    if provider == "openai":
        return _embed_openai(cfg, texts)
    if provider == "azure_openai":
        return _embed_azure_openai(cfg, texts)
    if provider == "cohere":
        return _embed_cohere(cfg, texts)
    if provider == "vertex":
        return _embed_vertex(cfg, texts)
    if provider == "huggingface":
        return _embed_huggingface(cfg, texts)
    if provider == "ollama":
        return _embed_ollama(cfg, texts)

    # Unknown provider — fall back rather than blowing up
    logger.warning(f"Unknown embedder provider '{provider}', falling back to local MiniLM")
    return _embed_sentence_transformers("all-MiniLM-L6-v2", texts)


# ----------------------------- Providers ----------------------------------

def _embed_sentence_transformers(model_id: str, texts: Sequence[str]) -> list[list[float]]:
    """Local CPU embedding via sentence-transformers. No API key required.

    device="cpu" is explicit and load-bearing, not cosmetic: without it,
    sentence-transformers auto-detects and picks Apple's MPS (GPU) backend
    on Apple Silicon, which has intermittently hard-crashed this backend's
    entire process (not a catchable Python exception — the process just
    disappears, taking every in-flight request down with it). A single
    short string doesn't need GPU acceleration; CPU is both fast enough and
    far more stable for a long-running background service."""
    cache_key = ("sentence_transformers", model_id)
    with _cache_lock:
        model = _local_model_cache.get(cache_key)
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_id, device="cpu")
            _local_model_cache[cache_key] = model
    vectors = model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)
    return vectors.tolist()


def _embed_openai(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is not installed. Run: pip install openai"
        )
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.api_base or None)
    resp = client.embeddings.create(input=list(texts), model=cfg.model_id)
    return [d.embedding for d in resp.data]


def _embed_azure_openai(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is not installed. Run: pip install openai"
        )
    client = AzureOpenAI(
        api_key=cfg.api_key,
        api_version=cfg.api_version or "2024-02-01",
        azure_endpoint=cfg.api_base,
    )
    deployment = cfg.azure_deployment or cfg.model_id
    resp = client.embeddings.create(input=list(texts), model=deployment)
    return [d.embedding for d in resp.data]


def _embed_cohere(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    try:
        import cohere
    except ImportError:
        raise RuntimeError(
            "The 'cohere' package is not installed. Run: pip install cohere"
        )
    client = cohere.Client(api_key=cfg.api_key)
    resp = client.embed(texts=list(texts), model=cfg.model_id, input_type="search_document")
    return list(resp.embeddings)


def _embed_vertex(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    try:
        from vertexai.language_models import TextEmbeddingModel
    except ImportError:
        raise RuntimeError(
            "The 'google-cloud-aiplatform' package is not installed. "
            "Run: pip install google-cloud-aiplatform"
        )
    model = TextEmbeddingModel.from_pretrained(cfg.model_id)
    embeddings = model.get_embeddings(list(texts))
    return [e.values for e in embeddings]


def _embed_huggingface(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    import requests
    url = cfg.api_base or f"https://api-inference.huggingface.co/pipeline/feature-extraction/{cfg.model_id}"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    resp = requests.post(url, headers=headers, json={"inputs": list(texts)}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # HF returns either [[float]] for single input or [[[float]]] for batch
    if isinstance(data[0], list) and isinstance(data[0][0], list):
        return data
    return [data] if not isinstance(data[0], list) else data


def _embed_ollama(cfg: EmbedderConfigRecord, texts: Sequence[str]) -> list[list[float]]:
    import requests
    base = (cfg.api_base or "http://localhost:11434").rstrip("/")
    out: list[list[float]] = []
    for t in texts:
        r = requests.post(f"{base}/api/embeddings", json={"model": cfg.model_id, "prompt": t}, timeout=30)
        r.raise_for_status()
        out.append(r.json()["embedding"])
    return out
