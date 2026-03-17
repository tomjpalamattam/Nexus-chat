"""
Synchronous ingestion task — called from a Django view via a thread
so it doesn't block the request/response cycle.

In production, swap the threading call for a Celery task.
"""
import logging
import threading

logger = logging.getLogger(__name__)


def _run_ingest(document_pk: int):
    from rag.models import ProviderDocument
    from rag.ingest import ingest_document

    doc = ProviderDocument.objects.get(pk=document_pk)
    doc.status = ProviderDocument.Status.INGESTING
    doc.save(update_fields=['status'])
    try:
        count = ingest_document(doc)
        doc.chunk_count = count
        doc.status = ProviderDocument.Status.READY
        doc.save(update_fields=['chunk_count', 'status'])
        logger.info('Ingested %d chunks for document %d', count, document_pk)
    except Exception as exc:
        logger.exception('Ingestion failed for document %d', document_pk)
        doc.status = ProviderDocument.Status.ERROR
        doc.error_message = str(exc)
        doc.save(update_fields=['status', 'error_message'])


def ingest_async(document_pk: int):
    """Kick off ingestion in a background thread."""
    t = threading.Thread(target=_run_ingest, args=(document_pk,), daemon=True)
    t.start()
