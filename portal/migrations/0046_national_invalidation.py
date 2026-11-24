"""PostgreSQL statement triggers cover ORM bulk updates and imports, in the writing transaction."""

from django.db import migrations

OWNERS = {
    "asset": "SELECT organization_id FROM changed",
    "finding": "SELECT organization_id FROM changed",
    "installation": "SELECT a.organization_id FROM portal_asset a JOIN changed c ON a.id=c.asset_id",
    "product": "SELECT organization_id FROM changed UNION SELECT a.organization_id FROM portal_installation i JOIN portal_asset a ON a.id=i.asset_id WHERE i.product_id IN (SELECT id FROM changed)",
    "inventorysource": "SELECT organization_id FROM changed UNION SELECT organization_id FROM portal_asset WHERE source_id IN (SELECT id FROM changed)",
    "sourcerecord": "SELECT organization_id FROM changed UNION SELECT organization_id FROM portal_finding WHERE record_id IN (SELECT id FROM changed)",
    "productwatch": "SELECT f.organization_id FROM portal_discoverymatch m JOIN portal_finding f ON f.id=m.finding_id WHERE m.watch_id IN (SELECT id FROM changed)",
    "sourcerecordrevision": "SELECT f.organization_id FROM portal_discoverymatch m JOIN portal_finding f ON f.id=m.finding_id WHERE m.evidence_revision_id IN (SELECT id FROM changed)",
    "discoverymatch": "SELECT f.organization_id FROM portal_finding f JOIN changed c ON f.id=c.finding_id",
    "discoveryrevision": "SELECT f.organization_id FROM portal_discoverymatch m JOIN portal_finding f ON f.id=m.finding_id WHERE m.id IN (SELECT match_id FROM changed)",
    "findinghistory": "SELECT f.organization_id FROM portal_finding f JOIN changed c ON f.id=c.finding_id",
}


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    q = schema_editor.execute
    q("""INSERT INTO portal_nationalstate (organization_id,dirty,operator_counts,shared_counts,inventory_assets,installations,unknown_versions)
         SELECT id,true,'{}'::jsonb,'{}'::jsonb,0,0,0 FROM portal_organization ON CONFLICT DO NOTHING""")
    q("""CREATE FUNCTION bearings_national_new_org() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
         INSERT INTO portal_nationalstate (organization_id,dirty,operator_counts,shared_counts,inventory_assets,installations,unknown_versions)
         SELECT id,true,'{}'::jsonb,'{}'::jsonb,0,0,0 FROM new_rows ON CONFLICT DO NOTHING;
         RETURN NULL; END $$""")
    q(
        "CREATE TRIGGER bearings_national_new_org AFTER INSERT ON portal_organization REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION bearings_national_new_org()"
    )
    for model, owners in OWNERS.items():
        for event in ("INSERT", "UPDATE", "DELETE"):
            suffix = model + "_" + event.lower()
            source = (
                "SELECT * FROM new_rows"
                if event == "INSERT"
                else "SELECT * FROM old_rows"
                if event == "DELETE"
                else "SELECT * FROM new_rows UNION ALL SELECT * FROM old_rows"
            )
            transition = (
                "NEW TABLE AS new_rows"
                if event == "INSERT"
                else "OLD TABLE AS old_rows"
                if event == "DELETE"
                else "OLD TABLE AS old_rows NEW TABLE AS new_rows"
            )
            q(f"""CREATE FUNCTION bearings_dirty_{suffix}() RETURNS trigger LANGUAGE plpgsql AS $$
                 DECLARE owner_id bigint; BEGIN
                 FOR owner_id IN WITH changed AS ({source}) SELECT DISTINCT organization_id FROM ({owners}) owners WHERE organization_id IS NOT NULL ORDER BY organization_id
                 LOOP UPDATE portal_nationalstate SET dirty=true WHERE organization_id=owner_id; END LOOP;
                 RETURN NULL; END $$""")
            q(
                f"CREATE TRIGGER bearings_dirty_{suffix} AFTER {event} ON portal_{model} REFERENCING {transition} FOR EACH STATEMENT EXECUTE FUNCTION bearings_dirty_{suffix}()"
            )


def remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    q = schema_editor.execute
    q("DROP TRIGGER IF EXISTS bearings_national_new_org ON portal_organization")
    q("DROP FUNCTION IF EXISTS bearings_national_new_org()")
    for model in OWNERS:
        for event in ("insert", "update", "delete"):
            q(f"DROP TRIGGER IF EXISTS bearings_dirty_{model}_{event} ON portal_{model}")
            q(f"DROP FUNCTION IF EXISTS bearings_dirty_{model}_{event}()")


class Migration(migrations.Migration):
    dependencies = [("portal", "0045_national_read_models")]
    operations = [migrations.RunPython(install, remove)]
