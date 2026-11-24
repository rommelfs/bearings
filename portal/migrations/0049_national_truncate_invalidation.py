"""Administrative truncation must not leave apparently current derived inventory."""

from django.db import migrations

TABLES = [
    "organization",
    "asset",
    "installation",
    "product",
    "inventorysource",
    "sourcerecord",
    "finding",
    "productwatch",
    "sourcerecordrevision",
    "discoverymatch",
    "discoveryrevision",
    "findinghistory",
]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE FUNCTION bearings_national_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE portal_nationalstate SET dirty=true; RETURN NULL; END $$"
    )
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER bearings_truncate_{table} AFTER TRUNCATE ON portal_{table} FOR EACH STATEMENT EXECUTE FUNCTION bearings_national_truncate()"
        )


def remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS bearings_truncate_{table} ON portal_{table}")
    schema_editor.execute("DROP FUNCTION IF EXISTS bearings_national_truncate()")


class Migration(migrations.Migration):
    dependencies = [("portal", "0048_research_version_projection")]
    operations = [migrations.RunPython(install, remove)]
