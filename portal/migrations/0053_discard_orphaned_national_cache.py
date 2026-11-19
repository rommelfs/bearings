"""Derived rows must disappear on raw organization deletion/truncation as with ORM cascades."""

from django.db import migrations

CACHE_TABLES = [
    "nationalactivity",
    "nationalproblem",
    "nationalproductversion",
    "nationalversion",
    "nationalstate",
]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    selected = " ".join(
        f"DELETE FROM portal_{table} WHERE organization_id IN (SELECT id FROM old_rows);"
        for table in CACHE_TABLES
    )
    all_rows = " ".join(f"DELETE FROM portal_{table};" for table in CACHE_TABLES)
    schema_editor.execute(
        f"CREATE FUNCTION bearings_national_deleted_org() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {selected} RETURN NULL; END $$"
    )
    schema_editor.execute(
        "CREATE TRIGGER bearings_national_deleted_org AFTER DELETE ON portal_organization REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT EXECUTE FUNCTION bearings_national_deleted_org()"
    )
    schema_editor.execute(
        f"CREATE OR REPLACE FUNCTION bearings_national_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_TABLE_NAME='portal_organization' THEN {all_rows} ELSE UPDATE portal_nationalstate SET dirty=true; END IF; RETURN NULL; END $$"
    )


def remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS bearings_national_deleted_org ON portal_organization")
    schema_editor.execute("DROP FUNCTION IF EXISTS bearings_national_deleted_org()")
    schema_editor.execute(
        "CREATE OR REPLACE FUNCTION bearings_national_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE portal_nationalstate SET dirty=true; RETURN NULL; END $$"
    )


class Migration(migrations.Migration):
    dependencies = [("portal", "0052_national_cache_reset_recovery")]
    operations = [migrations.RunPython(install, remove)]
