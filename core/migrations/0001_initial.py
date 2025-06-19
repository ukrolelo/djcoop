from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='DatabaseServer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('host', models.CharField(max_length=255)),
                ('port', models.IntegerField()),
                ('username', models.CharField(max_length=100)),
                ('password', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ReplicationLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('databases', models.JSONField(help_text='List of databases to replicate')),
                ('status', models.CharField(default='pending', max_length=50)),
                ('lag_seconds', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_replications', to='core.databaseserver')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='target_replications', to='core.databaseserver')),
            ],
            options={
                'ordering': ['source__name', 'target__name'],
                'unique_together': {('source', 'target')},
            },
        ),
    ]