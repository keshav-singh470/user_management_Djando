from django.db import migrations


def link_clients(apps, schema_editor):
    Project = apps.get_model('users', 'Project')
    User = apps.get_model('users', 'User')
    unmatched = []
    for p in Project.objects.exclude(old_client=None).select_related('old_client'):
        email = (p.old_client.email_id or '').strip()
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user:
            Project.objects.filter(pk=p.pk).update(client=user)
        else:
            unmatched.append((p.pk, p.title, email))
    if unmatched:
        print(f"\n  WARNING: {len(unmatched)} project(s) have a client with no matching user: {unmatched}")


class Migration(migrations.Migration):

    dependencies = [('users', '0027_project_old_client_and_new_client')]

    operations = [migrations.RunPython(link_clients, migrations.RunPython.noop)]