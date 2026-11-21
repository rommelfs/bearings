"""Do not rebuild unchanged inventory because a poll timestamp or health receipt changed."""

from importlib import import_module
from django.db import migrations

OWNERS = import_module("portal.migrations.0046_national_invalidation").OWNERS
TRACKED = {
    "asset": ("organization_id", "source_id", "lifecycle"),
    "finding": ("organization_id", "installation_id", "record_id", "status", "analyst_applicability"),
    "installation": ("asset_id", "product_id", "version"),
    "product": ("organization_id", "name", "identifier"),
    "inventorysource": ("organization_id",),
    "sourcerecord": ("organization_id", "external_id", "source_severity", "shareable"),
    "productwatch": ("product_id",),
    "sourcerecordrevision": ("record_id",),
    "discoverymatch": ("watch_id", "finding_id", "evidence_revision_id"),
    "discoveryrevision": ("match_id", "created_at"),
    "findinghistory": ("finding_id", "previous_status", "status", "created_at"),
}


def replace(schema_editor, precise):
    if schema_editor.connection.vendor != "postgresql":
        return
    for model, owners in OWNERS.items():
        if precise:
            fields = ("id", *TRACKED[model])
            new = ",".join("n." + field for field in fields)
            old = ",".join("o." + field for field in fields)
            source = f"""WITH delta AS (SELECT n.id AS new_id,o.id AS old_id FROM new_rows n FULL JOIN old_rows o ON n.id=o.id WHERE ROW({new}) IS DISTINCT FROM ROW({old}))
                       SELECT * FROM new_rows WHERE id IN (SELECT new_id FROM delta)
                       UNION ALL SELECT * FROM old_rows WHERE id IN (SELECT old_id FROM delta)"""
        else:
            source = "SELECT * FROM new_rows UNION ALL SELECT * FROM old_rows"
        schema_editor.execute(f"""CREATE OR REPLACE FUNCTION bearings_dirty_{model}_update() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE owner_id bigint; BEGIN
            FOR owner_id IN WITH changed AS ({source}) SELECT DISTINCT organization_id FROM ({owners}) owners WHERE organization_id IS NOT NULL ORDER BY organization_id
            LOOP UPDATE portal_nationalstate SET dirty=true WHERE organization_id=owner_id; END LOOP;
            RETURN NULL; END $$""")


def install(apps, schema_editor):
    replace(schema_editor, True)


def remove(apps, schema_editor):
    replace(schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [("portal", "0050_nonblocking_derived_references")]
    operations = [migrations.RunPython(install, remove)]
