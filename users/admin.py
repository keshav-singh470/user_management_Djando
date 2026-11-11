from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Client, Project, Profile, ProjectAttachment, ProjectTask, TaskComment

admin.site.register(User, UserAdmin)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'first_name', 'last_name', 'email_id', 'contact_no',
        'countries', 'is_active', 'created_at', 'updated_at',
    )
    list_filter = ('is_active', 'countries', 'created_at')
    search_fields = ('first_name', 'last_name', 'email_id', 'contact_no')
    readonly_fields = ('created_at', 'updated_at')


class ProjectAttachmentInline(admin.TabularInline):
    model = ProjectAttachment
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'type', 'status', 'client', 'assigned_manager', 'is_active', 'date_of_completion')
    list_filter = ('status', 'type', 'is_active')
    search_fields = ('title', 'client__first_name', 'assigned_manager__username')
    inlines = [ProjectAttachmentInline]


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_default', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_default',)

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_default:
            return False
        return super().has_change_permission(request, obj)

@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'project', 'assigned_to', 'status', 'priority', 'deadline_date', 'is_active')
    list_filter = ('is_active', 'status', 'priority')
    search_fields = ('title', 'project__title', 'assigned_to__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'user', 'hours_spent', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('comment', 'task__title', 'user__email')
    readonly_fields = ('created_at', 'updated_at')