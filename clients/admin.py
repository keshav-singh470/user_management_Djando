from django.contrib import admin
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'first_name',
        'last_name',
        'email_id',
        'contact_no',
        'countries',
        'is_active',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_active', 'countries', 'created_at')
    search_fields = ('first_name', 'last_name', 'email_id', 'contact_no')
    readonly_fields = ('created_at', 'updated_at')
