from django.urls import path
from . import views

urlpatterns = [
    path('documents/',                  views.DocumentListView.as_view(),       name='rag_documents'),
    path('documents/upload/',           views.DocumentUploadView.as_view(),     name='rag_upload'),
    path('documents/<int:pk>/delete/',  views.DocumentDeleteView.as_view(),     name='rag_delete'),
    path('documents/<int:pk>/status/',  views.DocumentStatusView.as_view(),     name='rag_status'),
    path('embedding-config/',           views.EmbeddingConfigSaveView.as_view(), name='rag_embedding_config'),
]