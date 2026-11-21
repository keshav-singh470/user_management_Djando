from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [('users', '0028_link_project_clients')]

    operations = [migrations.RemoveField(model_name='project', name='old_client')]