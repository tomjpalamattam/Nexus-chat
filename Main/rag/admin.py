from django.contrib import admin
from .models import ProviderDocument, ProviderCollection


@admin.register(ProviderDocument)
class ProviderDocumentAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'provider', 'status', 'chunk_count', 'uploaded_at')
    list_filter  = ('status',)
    readonly_fields = ('chunk_count', 'status', 'error_message', 'uploaded_at')


@admin.register(ProviderCollection)
class ProviderCollectionAdmin(admin.ModelAdmin):
    list_display = ('provider', 'collection_name', 'created_at')
