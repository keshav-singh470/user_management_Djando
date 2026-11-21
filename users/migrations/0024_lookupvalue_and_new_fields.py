import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0023_remove_client_updated_at_remove_client_updated_by_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LookupValue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('project_type', 'Project Type'), ('project_status', 'Project Status'), ('task_status', 'Task Status')], max_length=30)),
                ('name', models.CharField(max_length=100)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True, blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lookupvalue_created', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lookupvalue_modified', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['category', 'name']},
        ),
        migrations.AddConstraint(
            model_name='lookupvalue',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('name'), models.F('category'), name='unique_lookup_name_per_category'),
        ),
        # temporary fields: migration 0026 mein inka naam "type" / "status" ho jayega
        migrations.AddField(
            model_name='project',
            name='type_fk',
            field=models.ForeignKey(blank=True, null=True, limit_choices_to={'category': 'project_type'}, on_delete=django.db.models.deletion.PROTECT, related_name='projects_by_type', to='users.lookupvalue'),
        ),
        migrations.AddField(
            model_name='project',
            name='status_fk',
            field=models.ForeignKey(blank=True, null=True, limit_choices_to={'category': 'project_status'}, on_delete=django.db.models.deletion.PROTECT, related_name='projects_by_status', to='users.lookupvalue'),
        ),
        migrations.AddField(
            model_name='projecttask',
            name='status_fk',
            field=models.ForeignKey(blank=True, null=True, limit_choices_to={'category': 'task_status'}, on_delete=django.db.models.deletion.PROTECT, related_name='tasks_by_status', to='users.lookupvalue'),
        ),
    ]