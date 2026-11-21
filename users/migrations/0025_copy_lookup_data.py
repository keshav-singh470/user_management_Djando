from django.db import migrations

DEFAULT_STATUSES = ['Pending', 'In Progress', 'Completed', 'On Hold']
SAMPLE_TYPES = ['Web App', 'Mobile App', 'AI']


def copy_data(apps, schema_editor):
    Lookup = apps.get_model('users', 'LookupValue')
    Project = apps.get_model('users', 'Project')
    Task = apps.get_model('users', 'ProjectTask')

    def get_value(category, name, is_default=False):
        """Value case-insensitive dhundho, na mile to banao."""
        name = ' '.join(str(name).split())
        if not name:
            return None
        obj = Lookup.objects.filter(category=category, name__iexact=name).first()
        if obj is None:
            obj = Lookup.objects.create(category=category, name=name, is_default=is_default)
        return obj

    # 1. system (default) statuses: update/delete nahi honge
    for n in DEFAULT_STATUSES:
        get_value('project_status', n, True)
        get_value('task_status', n, True)
    # 2. sample types (protected nahi), taaki fresh database mein project ban sake
    for n in SAMPLE_TYPES:
        get_value('project_type', n)

    # 3. purani text values ko naye foreign keys mein copy karo
    for p in Project.objects.all():
        Project.objects.filter(pk=p.pk).update(
            type_fk=get_value('project_type', p.type) if p.type else None,
            status_fk=get_value('project_status', p.status or 'Pending'),
        )
    for t in Task.objects.all():
        Task.objects.filter(pk=t.pk).update(
            status_fk=get_value('task_status', t.status or 'Pending'),
        )


class Migration(migrations.Migration):

    dependencies = [('users', '0024_lookupvalue_and_new_fields')]

    operations = [migrations.RunPython(copy_data, migrations.RunPython.noop)]