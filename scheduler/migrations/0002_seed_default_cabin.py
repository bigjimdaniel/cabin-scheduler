from django.db import migrations


def seed_default_cabin(apps, schema_editor):
    Cabin = apps.get_model("scheduler", "Cabin")
    Cabin.objects.get_or_create(
        slug="main-cabin",
        defaults={
            "name": "Cabin Scheduler Cabin",
            "description": "A shared cabin schedule for invited guests and administrators.",
            "location": "Set location in admin",
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("scheduler", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_cabin, migrations.RunPython.noop),
    ]
