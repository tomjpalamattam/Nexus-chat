from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.http import JsonResponse

from accounts.models import User
from .models import ProviderDocument
from .tasks import ingest_async
from .ingest import delete_document_vectors

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.doc', '.md', '.markdown'}
MAX_UPLOAD_MB = 50


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
        return render(request, 'rag/documents.html', {'documents': docs})


class DocumentUploadView(BtierRequiredMixin, View):
    def post(self, request):
        import os
        uploaded = request.FILES.get('file')
        if not uploaded:
            messages.error(request, 'No file selected.')
            return redirect('rag_documents')

        ext = os.path.splitext(uploaded.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            messages.error(request, f'Unsupported file type: {ext}. Allowed: PDF, TXT, DOCX, MD.')
            return redirect('rag_documents')

        if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
            messages.error(request, f'File too large. Maximum size is {MAX_UPLOAD_MB} MB.')
            return redirect('rag_documents')

        doc = ProviderDocument.objects.create(
            provider=request.user,
            file=uploaded,
            original_name=uploaded.name,
        )
        ingest_async(doc.pk)
        messages.success(request, f'"{uploaded.name}" uploaded — ingestion started.')
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
    """AJAX endpoint — returns current status of a document."""
    def get(self, request, pk):
        doc = get_object_or_404(ProviderDocument, pk=pk, provider=request.user)
        return JsonResponse({
            'status':      doc.status,
            'chunk_count': doc.chunk_count,
            'error':       doc.error_message,
        })
