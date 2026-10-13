from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('face_auth', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeefacedata',
            name='face_image_key',
            field=models.CharField(blank=True, default='', max_length=255, db_default=''),
        ),
        migrations.AlterField(
            model_name='employeefacedata',
            name='face_image_base64',
            field=models.TextField(blank=True, default='', db_default=''),
        ),
    ]
