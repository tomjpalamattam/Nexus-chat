"""
Ingestion pipeline using the current langchain_qdrant API:
  - QdrantVectorStore  (not the old Qdrant class)
  - Local path-based storage: BASE_DIR/qdrant_store/{provider_slug}/
  - HuggingFace token fetched from ProviderEmbeddingConfig in DB
  - Supports PDF, TXT, DOCX, MD
"""
import os
import tempfile
import logging
from pathlib import Path

from django.conf import settings

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredMarkdownLoader,
)
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

CHUNK_SIZE    = int(os.getenv('CHUNK_SIZE',    '800'))
CHUNK_OVERLAP = int(os.getenv('CHUNK_OVERLAP', '100'))


# ── helpers ───────────────────────────────────────────────────────────────────

def _qdrant_path(provider) -> str:
    """Absolute local path for this provider's Qdrant store."""
    base = Path(settings.BASE_DIR) / 'qdrant_store' / provider.slug
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def _collection_name(provider) -> str:
    return f'provider_{provider.slug}'


def _get_embedding_cfg(provider):
    """
    Fetch the ProviderEmbeddingConfig for a provider.
    Pure DB access — must be called from a sync context (use
    database_sync_to_async when calling from async code).
    """
    from rag.models import ProviderEmbeddingConfig
    try:
        return ProviderEmbeddingConfig.objects.get(provider=provider)
    except ProviderEmbeddingConfig.DoesNotExist:
        raise ValueError(
            f'Provider "{provider.username}" has no embedding config. '
            'Please add a HuggingFace token in Dashboard → Knowledge Base.'
        )


def _build_embeddings(cfg) -> HuggingFaceEndpointEmbeddings:
    """Build embeddings object from a ProviderEmbeddingConfig instance."""
    return HuggingFaceEndpointEmbeddings(
        model=cfg.embed_model,
        task='feature-extraction',
        huggingfacehub_api_token=cfg.hf_token,
    )


def _loader_for(filepath: str, ext: str):
    ext = ext.lower()
    if ext == '.pdf':
        return PyMuPDFLoader(filepath)
    elif ext == '.txt':
        return TextLoader(filepath, encoding='utf-8')
    elif ext in ('.docx', '.doc'):
        return UnstructuredWordDocumentLoader(filepath)
    elif ext in ('.md', '.markdown'):
        return UnstructuredMarkdownLoader(filepath)
    else:
        raise ValueError(f'Unsupported file extension: {ext}')


# ── main entry points ─────────────────────────────────────────────────────────

def ingest_document(provider_document) -> int:
    """
    Load → split → embed → upsert into local QdrantVectorStore.
    Runs in a background thread (sync context). Returns chunk count.
    """
    from rag.models import ProviderCollection

    provider   = provider_document.provider
    ext        = os.path.splitext(provider_document.original_name)[1]
    col_name   = _collection_name(provider)
    path       = _qdrant_path(provider)
    cfg        = _get_embedding_cfg(provider)
    embeddings = _build_embeddings(cfg)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in provider_document.file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        loader   = _loader_for(tmp_path, ext)
        raw_docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(raw_docs)

        for chunk in chunks:
            chunk.metadata['provider_slug'] = provider.slug
            chunk.metadata['provider_id']   = provider.pk
            chunk.metadata['document_id']   = provider_document.pk
            chunk.metadata['original_name'] = provider_document.original_name

        QdrantVectorStore.from_documents(
            chunks,
            embedding=embeddings,
            path=path,
            collection_name=col_name,
        )

        ProviderCollection.objects.update_or_create(
            provider=provider,
            defaults={'collection_name': col_name, 'local_path': path},
        )

        return len(chunks)
    finally:
        os.unlink(tmp_path)


def delete_document_vectors(provider_document):
    """Remove all vectors for a specific document from the local store."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    provider = provider_document.provider
    col_name = _collection_name(provider)
    path     = _qdrant_path(provider)

    client   = QdrantClient(path=path)
    existing = [c.name for c in client.get_collections().collections]
    if col_name not in existing:
        client.close()
        return

    client.delete(
        collection_name=col_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key='metadata.document_id',
                    match=MatchValue(value=provider_document.pk),
                )
            ]
        ),
    )
    client.close()


def get_vectorstore(cfg, provider) -> QdrantVectorStore:
    """
    Return a QdrantVectorStore for a provider's local collection.
    Accepts an already-fetched ProviderEmbeddingConfig so the caller
    can do the DB lookup in a sync context before entering async code.
    """
    col_name   = _collection_name(provider)
    path       = _qdrant_path(provider)
    embeddings = _build_embeddings(cfg)

    return QdrantVectorStore.from_existing_collection(
        collection_name=col_name,
        embedding=embeddings,
        path=path,
    )