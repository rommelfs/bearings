"""Provision Bearings for the explicitly isolated development stack."""

import json
import os
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from portal.access import ANALYST_GROUP, audit
from portal.connectors.http import ConnectorError
from portal.models import (
    Asset,
    Installation,
    InventorySource,
    Membership,
    NetBoxInstance,
    Organization,
    Product,
)
from portal.services import query_inventory


class Command(BaseCommand):
    help = "Initialize an isolated bundled/external development lab; never prints credentials"

    def add_arguments(self, parser):
        parser.add_argument("--config", required=True)
        parser.add_argument("--password-file", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or os.getenv("BEARINGS_DEV_STACK") != "1":
            raise CommandError("This initializer is restricted to the explicit local development stack")
        password = Path(options["password_file"]).read_text().strip()
        if len(password) < 12:
            raise CommandError("Invalid development password file")
        config = json.loads(Path(options["config"]).read_text())
        if config.get("mode") not in {"bundled", "external"}:
            raise CommandError("Invalid development connection mode")
        users, created_users = {}, {}
        for name in ["platform-admin", "company-admin", "circl-analyst"]:
            admin = name == "platform-admin"
            user, created = get_user_model().objects.get_or_create(
                username=name,
                defaults={"email": name + "@example.invalid", "is_superuser": admin, "is_staff": admin},
            )
            if created:
                user.set_password(password)
                user.save()
            users[name], created_users[name] = user, created
        group, _ = Group.objects.get_or_create(name=ANALYST_GROUP)
        if created_users["circl-analyst"]:
            users["circl-analyst"].groups.add(group)
        example_existed = Organization.objects.filter(slug="example-labs").exists()
        call_command("seed_demo", no_users=True)
        example = Organization.objects.get(slug="example-labs")
        if not example_existed or created_users["company-admin"]:
            Membership.objects.get_or_create(
                user=users["company-admin"], organization=example, defaults={"role": "admin"}
            )
        for item in config["connections"]:
            org, org_created = Organization.objects.get_or_create(
                slug=item["organization_slug"],
                defaults={
                    "name": item["organization_name"],
                    "operator_visibility": config["mode"] == "bundled",
                },
            )
            if org_created or created_users["company-admin"]:
                Membership.objects.get_or_create(
                    user=users["company-admin"], organization=org, defaults={"role": "admin"}
                )
            fields = {
                key: item[key]
                for key in ["base_url", "token_env_var", "auth_scheme", "access_mode", "allow_private"]
            }
            fields.update({key: item.get(key) for key in ["site_id", "role_id", "device_type_id"]})
            fields["browser_url"] = item.get("browser_url", "")
            fields["organization"] = org if item.get("dedicated") else None
            instance, created = NetBoxInstance.objects.get_or_create(name=item["name"], defaults=fields)
            if instance.base_url != item["base_url"] or instance.token_env_var != item["token_env_var"]:
                raise CommandError("Existing development connection identity differs; refusing to repoint it")
            if config["mode"] == "bundled" and not instance.browser_url and item.get("browser_url"):
                instance.browser_url = item["browser_url"]
                instance.full_clean()
                instance.save(update_fields=["browser_url"])
            instance.full_clean()
            if created:
                audit(
                    None, org, "development.instance_created", instance.pk, access_mode=instance.access_mode
                )
            source, source_created = InventorySource.objects.get_or_create(
                organization=org,
                defaults={
                    "mode": "central" if config["mode"] == "bundled" else "external",
                    "instance": instance,
                    "tenant_id": item.get("tenant_id"),
                },
            )
            if source.instance_id != instance.pk or source.tenant_id != item.get("tenant_id"):
                raise CommandError("Existing development source differs; refusing to overwrite inventory")
            source.full_clean()
            if not instance.enabled:
                self.stdout.write("Disabled development connection preserved.")
                continue
            try:
                result = query_inventory(
                    source, ["devices", "virtual-machines"] if config["mode"] == "bundled" else ["devices"]
                )
            except ConnectorError:
                if config["mode"] == "bundled" and source_created:
                    raise CommandError(
                        "Bundled NetBox validation failed; inspect the verified connection health/configuration"
                    ) from None
                self.stderr.write(
                    "NetBox query failed; last-known data retained, inspect workspace read health."
                )
                continue
            for seed in item.get("assets", []):
                kind = "devices" if seed["object_type"] == "dcim.device" else "virtual-machines"
                row = next((v for v in result[kind] if v["external_id"] == seed["external_id"]), None)
                if not row or row["record"].get("custom_fields", {}).get("bearings_id") != seed["id"]:
                    raise CommandError("Synthetic seed identity not confirmed by the live bundled API")
                asset, _ = Asset.objects.get_or_create(
                    source=source,
                    object_type=seed["object_type"],
                    external_id=seed["external_id"],
                    defaults={
                        "id": seed["id"],
                        "organization": org,
                        "name": row["record"]["name"],
                        "kind": seed["kind"],
                        "state": "synced",
                    },
                )
                asset.full_clean()
                product, _ = Product.objects.get_or_create(
                    organization=org,
                    name="Apache Log4j",
                    identifier="pkg:maven/org.apache.logging.log4j/log4j-core",
                )
                Installation.objects.get_or_create(
                    asset=asset, product=product, defaults={"version": "2.14.1"}
                )
        from portal.intelligence import default_catalog

        default_catalog()
        self.stdout.write(
            "Development accounts/connections prepared. Bundled inventory is synthetic; external mode performs GETs only."
        )
