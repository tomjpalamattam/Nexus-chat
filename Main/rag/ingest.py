"""
Ingestion pipeline: load → split → embed → upsert into Qdrant.
Each provider gets its own Qdrant collection: provider_{slug}
"""
import os
import tempfile
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredMarkdownLoader,
)
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_qdrant import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────────────────
QDRANT_URL      = os.getenv('QDRANT_URL', 'http://localhost:6333')
HF_API_KEY      = os.getenv('HF_API_KEY', '')
EMBED_MODEL     = os.getenv('EMBED_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
EMBED_DIM       = int(os.getenv('EMBED_DIM', '384'))
CHUNK_SIZE      = int(os.getenv('CHUNK_SIZE', '800'))
CHUNK_OVERLAP   = int(os.getenv('CHUNK_OVERLAP', '100'))

# ── helpers ───────────────────────────────────────────────────────────────────

def get_embeddings():
    return HuggingFaceEndpointEmbeddings(
        model=EMBED_MODEL,
        huggingfacehub_api_token=HF_API_KEY,
    )


def get_qdrant_client():
    return QdrantClient(url=QDRANT_URL)


def collection_name_for(provider) -> str:
    return f'provider_{provider.slug}'


def ensure_collection(client: QdrantClient, name: str):
    """Create the Qdrant collection if it doesn't exist yet."""
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info('Created Qdrant collection: %s', name)


def loader_for(filepath: str, ext: str):
    ext = ext.lower()
    if ext == '.pdf':
        return PyMuPDFLoader(filepath)
    elif ext in ('.txt',):
        return TextLoader(filepath, encoding='utf-8')
    elif ext in ('.docx', '.doc'):
        return UnstructuredWordDocumentLoader(filepath)
    elif ext in ('.md', '.markdown'):
        return UnstructuredMarkdownLoader(filepath)
    else:
        raise ValueError(f'Unsupported file extension: {ext}')


# ── main entry point ──────────────────────────────────────────────────────────

def ingest_document(provider_document) -> int:
    """
    Load, split, embed and upsert a ProviderDocument.
    Returns the number of chunks inserted.
    Raises on failure (caller should set status=error).
    """
    from rag.models import ProviderCollection

    doc_file  = provider_document.file
    ext       = os.path.splitext(provider_document.original_name)[1]
    provider  = provider_document.provider
    col_name  = collection_name_for(provider)

    # Write the Django FieldFile to a temp file so loaders can read it
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in doc_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        loader   = loader_for(tmp_path, ext)
        raw_docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(raw_docs)

        # Tag every chunk with provider info for future filtering
        for chunk in chunks:
            chunk.metadata['provider_slug']    = provider.slug
            chunk.metadata['provider_id']      = provider.pk
            chunk.metadata['document_id']      = provider_document.pk
            chunk.metadata['original_name']    = provider_document.original_name

        embeddings = get_embeddings()
        client     = get_qdrant_client()
        ensure_collection(client, col_name)

        Qdrant(
            client=client,
            collection_name=col_name,
            embeddings=embeddings,
        ).add_documents(chunks)

        # Record the collection mapping (idempotent)
        ProviderCollection.objects.get_or_create(
            provider=provider,
            defaults={'collection_name': col_name},
        )

        return len(chunks)
    finally:
        os.unlink(tmp_path)


def delete_document_vectors(provider_document):
    """Remove all vectors that belong to a specific document from Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    provider = provider_document.provider
    col_name = collection_name_for(provider)
    client   = get_qdrant_client()

    existing = [c.name for c in client.get_collections().collections]
    if col_name not in existing:
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


def get_retriever(provider, k: int = 4):
    """Return a LangChain VectorStoreRetriever for a provider's collection."""
    col_name   = collection_name_for(provider)
    embeddings = get_embeddings()
    client     = get_qdrant_client()

    store = Qdrant(
        client=client,
        collection_name=col_name,
        embeddings=embeddings,
    )
    return store.as_retriever(search_kwargs={'k': k})


def get_vectorstore(provider):
    """Return the raw Qdrant vectorstore for a provider."""
    col_name   = collection_name_for(provider)
    embeddings = get_embeddings()
    client     = get_qdrant_client()

    return Qdrant(
        client=client,
        collection_name=col_name,
        embeddings=embeddings,
    )
