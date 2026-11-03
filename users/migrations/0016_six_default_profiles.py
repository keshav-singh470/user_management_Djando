from django.db import migrations

DEFAULT_PROFILES = ['Super Admin', 'Admin', 'Manager', 'Team Leader', 'Developer', 'Human Resource']

def set_default_profiles(apps, schema_editor):
    Profile = apps.get_model('users', 'Profile')
    for name in DEFAULT_PROFILES:
        profile = Profile.objects.filter(name__iexact=name).first()
        if profile:
            profile.name = name
            profile.is_default = True
            profile.save()
        else:
            Profile.objects.create(name=name, is_default=True)
    # Jo list mein nahi hai (jaise Standard) wo ab normal/deletable profile ban jayega
    Profile.objects.exclude(name__in=DEFAULT_PROFILES).update(is_default=False)

class Migration(migrations.Migration):
    dependencies = [('users', '0015_alter_client_restored_by')]
    operations = [migrations.RunPython(set_default_profiles, migrations.RunPython.noop)]