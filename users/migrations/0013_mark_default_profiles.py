from django.db import migrations

DEFAULT_PROFILES = ['Admin', 'Human Resource', 'Manager', 'Developer', 'Standard']

def create_default_profiles(apps, schema_editor):
    Profile = apps.get_model('users', 'Profile')
    for name in DEFAULT_PROFILES:
        Profile.objects.update_or_create(name=name, defaults={'is_default': True})

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_remove_profile_description_profile_is_default'),
    ]

    operations = [
        migrations.RunPython(create_default_profiles, migrations.RunPython.noop),
    ]