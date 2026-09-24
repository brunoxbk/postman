from django.db import migrations, models


def clear_synclog(apps, schema_editor):
    SyncLog = apps.get_model("core", "SyncLog")
    SyncLog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(clear_synclog, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="synclog",
            name="day",
        ),
        migrations.AlterModelOptions(
            name="synclog",
            options={"ordering": ["-month"]},
        ),
        migrations.AddField(
            model_name="synclog",
            name="month",
            field=models.DateField(unique=True),
        ),
    ]