"""Clearing a derived child table must schedule a source-based rebuild."""

from django.db import migrations

TABLES = ["nationalversion", "nationalproductversion", "nationalproblem", "nationalactivity"]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER bearings_truncate_{table} AFTER TRUNCATE ON portal_{table} FOR EACH STATEMENT EXECUTE FUNCTION bearings_national_truncate()"
        )


def remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS bearings_truncate_{table} ON portal_{table}")


class Migration(migrations.Migration):
    dependencies = [("portal", "0051_precise_national_invalidation")]
    operations = [migrations.RunPython(install, remove)]
