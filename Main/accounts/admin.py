from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, APIConfiguration


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'tier', 'parent', 'is_active')
    list_filter = ('tier',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Platform', {'fields': ('tier', 'parent')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Platform', {'fields': ('tier', 'parent')}),
    )


@admin.register(APIConfiguration)
class APIConfigurationAdmin(admin.ModelAdmin):
    list_display = ('owner', 'label', 'provider', 'model_name', 'is_default', 'is_active')
    list_filter = ('provider', 'is_active')