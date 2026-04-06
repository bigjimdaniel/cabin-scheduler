from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scheduler", "0002_seed_default_cabin"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="guest_name",
            field=models.CharField(
                blank=True,
                help_text="Optional name of the person staying, if different from the requester.",
                max_length=120,
            ),
        ),
    ]
