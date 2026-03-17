from django.db import models
from accounts.models import User


def upload_path(instance, filename):
    return f'rag/{instance.provider.slug}/{filename}'


class ProviderEmbeddingConfig(models.Model):
    """
    Stores the HuggingFace token and embedding model for a B-tier provider.
    Required before any documents can be ingested.
    """
    provider    = models.OneToOneField(User, on_delete=models.CASCADE,
                                       related_name='embedding_config')
    hf_token    = models.CharField(max_length=500,
                                   help_text='HuggingFace API token (hf_...)')
    embed_model = models.CharField(
        max_length=200,
        default='Qwen/Qwen3-Embedding-8B',
        help_text='HuggingFace model ID used for embeddings',
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.provider.username} — {self.embed_model}'


class ProviderDocument(models.Model):
    """A document uploaded by a B-tier provider for RAG."""

    class Status(models.TextChoices):
        PENDING   = 'pending',   'Pending'
        INGESTING = 'ingesting', 'Ingesting'
        READY     = 'ready',     'Ready'
        ERROR     = 'error',     'Error'

    provider      = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='documents')
    file          = models.FileField(upload_to=upload_path)
    original_name = models.CharField(max_length=255)
    status        = models.CharField(max_length=10, choices=Status.choices,
                                     default=Status.PENDING)
    error_message = models.TextField(blank=True)
    chunk_count   = models.PositiveIntegerField(default=0)
    uploaded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.provider.username} — {self.original_name}'


class ProviderCollection(models.Model):
    """Tracks the local Qdrant path + collection name for a provider."""
    provider        = models.OneToOneField(User, on_delete=models.CASCADE,
                                           related_name='qdrant_collection')
    collection_name = models.CharField(max_length=120)   # provider_{slug}
    local_path      = models.CharField(max_length=500)   # qdrant_store/{slug}/
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.provider.username} → {self.collection_name}'