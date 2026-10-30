from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Client, Project, Profile 

admin.site.register(User, UserAdmin)

 

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

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'type', 'status', 'client', 'assigned_manager', 'is_active', 'date_of_completion')
    list_filter = ('status', 'type', 'is_active')
    search_fields = ('title', 'client__first_name', 'assigned_manager__username')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'created_at')
    search_fields = ('name',)