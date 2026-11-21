from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [('users', '0025_copy_lookup_data')]

    operations = [
        migrations.RemoveField(model_name='project', name='type'),
        migrations.RemoveField(model_name='project', name='status'),
        migrations.RemoveField(model_name='projecttask', name='status'),
        migrations.RenameField(model_name='project', old_name='type_fk', new_name='type'),
        migrations.RenameField(model_name='project', old_name='status_fk', new_name='status'),
        migrations.RenameField(model_name='projecttask', old_name='status_fk', new_name='status'),
    ]