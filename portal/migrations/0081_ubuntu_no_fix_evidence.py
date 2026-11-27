from django.db import migrations, models

import portal.distro_projection


class Migration(migrations.Migration):
    dependencies = [("portal", "0080_agent_inventory_checks")]

    operations = [
        migrations.RemoveField(model_name="distromatch", name="queue_proof"),
        migrations.AddField(
            model_name="distromatch",
            name="queue_proof",
            field=models.GeneratedField(
                db_persist=True,
                expression=portal.distro_projection.DistroQueueProofV2("snapshot"),
                output_field=models.JSONField(),
            ),
        ),
    ]
