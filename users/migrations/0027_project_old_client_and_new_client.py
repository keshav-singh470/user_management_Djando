import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('users', '0026_swap_lookup_fields')]

    operations = [
        # 1. Purane client FK ka index hatao, taaki uska naam naye FK se na takraye
        migrations.AlterField(
            model_name='project',
            name='client',
            field=models.ForeignKey(db_index=False, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='projects', to='users.client'),
        ),
        # 2. Purane column ka naam badlo
        migrations.RenameField(model_name='project', old_name='client', new_name='old_client'),
        # 3. Naya client (User) jodo
        migrations.AddField(
            model_name='project',
            name='client',
            field=models.ForeignKey(blank=True, null=True, limit_choices_to={'profiles__name': 'Client'},
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='client_projects', to=settings.AUTH_USER_MODEL),
        ),
    ]