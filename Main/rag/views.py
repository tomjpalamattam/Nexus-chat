from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.http import JsonResponse

from accounts.models import User
from .models import ProviderDocument, ProviderEmbeddingConfig
from .tasks import ingest_async
from .ingest import delete_document_vectors

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.doc', '.md', '.markdown'}
MAX_UPLOAD_MB = 50

EMBED_MODEL_CHOICES = [
    ('Qwen/Qwen3-Embedding-8B',              'Qwen3-Embedding-8B (recommended)'),
    ('sentence-transformers/all-MiniLM-L6-v2', 'all-MiniLM-L6-v2 (lightweight)'),
    ('BAAI/bge-large-en-v1.5',               'BGE-Large-EN (high quality)'),
    ('intfloat/multilingual-e5-large',       'Multilingual-E5-Large'),
]


class BtierRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.tier not in [User.Tier.A, User.Tier.B]:
            return redirect('chat_home')
        return super().dispatch(request, *args, **kwargs)


class DocumentListView(BtierRequiredMixin, View):
    def get(self, request):
        docs = ProviderDocument.objects.filter(provider=request.user)
        try:
            embed_cfg = request.user.embedding_config
        except ProviderEmbeddingConfig.DoesNotExist:
            embed_cfg = None
        return render(request, 'rag/documents.html', {
            'documents':       docs,
            'embed_cfg':       embed_cfg,
            'model_choices':   EMBED_MODEL_CHOICES,
        })


class EmbeddingConfigSaveView(BtierRequiredMixin, View):
    """Save or update HuggingFace token + embedding model."""
    def post(self, request):
        hf_token    = request.POST.get('hf_token', '').strip()
        embed_model = request.POST.get('embed_model', '').strip()

        if not hf_token:
            messages.error(request, 'HuggingFace token is required.')
            return redirect('rag_documents')
        if not hf_token.startswith('hf_'):
            messages.error(request, 'Token should start with "hf_".')
            return redirect('rag_documents')
        if not embed_model:
            messages.error(request, 'Please select an embedding model.')
            return redirect('rag_documents')

        ProviderEmbeddingConfig.objects.update_or_create(
            provider=request.user,
            defaults={'hf_token': hf_token, 'embed_model': embed_model},
        )
        messages.success(request, 'Embedding configuration saved.')
        return redirect('rag_documents')


class DocumentUploadView(BtierRequiredMixin, View):
    def post(self, request):
        import os

        # Must have embedding config before ingesting
        try:
            request.user.embedding_config
        except ProviderEmbeddingConfig.DoesNotExist:
            messages.error(request, 'Please configure your HuggingFace token first.')
            return redirect('rag_documents')

        uploaded = request.FILES.get('file')
        if not uploaded:
            messages.error(request, 'No file selected.')
            return redirect('rag_documents')

        ext = os.path.splitext(uploaded.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            messages.error(request, f'Unsupported file type "{ext}". Allowed: PDF, TXT, DOCX, MD.')
            return redirect('rag_documents')

        if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
            messages.error(request, f'File too large. Maximum is {MAX_UPLOAD_MB} MB.')
            return redirect('rag_documents')

        doc = ProviderDocument.objects.create(
            provider=request.user,
            file=uploaded,
            original_name=uploaded.name,
        )
        ingest_async(doc.pk)
        messages.success(request, f'"{uploaded.name}" uploaded — indexing started.')
        return redirect('rag_documents')


class DocumentDeleteView(BtierRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(ProviderDocument, pk=pk, provider=request.user)
        try:
            delete_document_vectors(doc)
        except Exception as exc:
            messages.warning(request, f'Could not remove vectors: {exc}')
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, 'Document deleted.')
        return redirect('rag_documents')


class DocumentStatusView(BtierRequiredMixin, View):
    """AJAX endpoint — returns current ingestion status."""
    def get(self, request, pk):
        doc = get_object_or_404(ProviderDocument, pk=pk, provider=request.user)
        return JsonResponse({
            'status':      doc.status,
            'chunk_count': doc.chunk_count,
            'error':       doc.error_message,
        })