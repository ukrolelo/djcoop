from django.db import migrations

def create_initial_servers(apps, schema_editor):
    DatabaseServer = apps.get_model('core', 'DatabaseServer')
    
    servers = [
        {
            'name': 'dbserver1',
            'host': '192.168.6.99',
            'port': 9991,
            'username': 'your_user1',
            'password': 'your_password1'
        },
        {
            'name': 'dbserver2',
            'host': '192.168.6.99',
            'port': 9992,
            'username': 'your_user2',
            'password': 'your_password2'
        }
    ]
    
    for server_data in servers:
        DatabaseServer.objects.create(**server_data)

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_servers),
    ]