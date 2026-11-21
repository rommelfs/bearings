"""Bounded preview/explicit atomic import into manual inventory. Never an upstream submission."""

import csv
import hashlib
import io
import ipaddress
import json
import re
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction, DatabaseError
from django.utils import timezone
from .access import can_edit, require, audit
from .models import (
    Asset,
    Installation,
    Product,
    InventorySource,
    InventoryCSVBatch,
    CSVAssetBinding,
    Organization,
    ProductWatch,
)
from .scope import normalize

COLUMNS = ["asset_key", "name", "kind", "ip", "domain", "software", "version", "software_key"]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def authorize(actor, org, source):
    require(
        actor.is_active
        and can_edit(actor, org)
        and source.organization_id == org.pk
        and source.instance_id is None
        and source.mode == "manual"
        and source.can_write
    )


def parse(raw):
    if len(raw) > 1_000_000:
        raise ValidationError("Use a UTF-8 CSV file of at most 1 MB and 500 rows")
    try:
        text = raw.decode("utf-8-sig")
        delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = reader.fieldnames
        if (
            not headers
            or len(set(headers)) != len(headers)
            or not {"asset_key", "name"} <= set(headers)
            or set(headers) - set(COLUMNS)
        ):
            raise ValidationError(
                "Required columns: asset_key, name. Optional: kind, ip, domain, software, version, software_key. No duplicate/unknown columns."
            )
        rows, errors, assets, installs = [], [], {}, set()
        for number, row in enumerate(reader, 2):
            if number > 501:
                raise ValidationError("Use at most 500 data rows")
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValidationError("Row has the wrong number of columns")
                row = {key: (row.get(key) or "").strip() for key in COLUMNS}
                if any(len(v) > 255 or any(ord(c) < 32 for c in v) for v in row.values()):
                    raise ValidationError("Cells must be single-line text of at most 255 characters")
                if (
                    not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", row["asset_key"])
                    or not 1 <= len(row["name"]) <= 180
                ):
                    raise ValidationError(
                        "Use a stable asset_key (letters, digits, . _ : -) and an asset name of 1–180 characters"
                    )
                row["kind"] = row["kind"] or "server"
                if row["kind"] not in {"server", "desktop", "laptop", "appliance", "vm"}:
                    raise ValidationError("Kind must be server, desktop, laptop, appliance or vm")
                if row["ip"]:
                    row["ip"] = str(ipaddress.ip_interface(row["ip"]))
                if row["domain"]:
                    row["domain"] = normalize("domain", row["domain"])
                if (
                    len(row["software"]) > 180
                    or len(row["version"]) > 120
                    or (row["version"] and not row["software"])
                ):
                    raise ValidationError("Software needs a name (max 180); version is optional (max 120)")
                row["software_key"] = row["software_key"] or row["software"]
                meta = {k: row[k] for k in ["name", "kind", "ip", "domain"]}
                if row["asset_key"] in assets and assets[row["asset_key"]] != meta:
                    raise ValidationError("Repeated asset_key has conflicting name/kind/IP/domain")
                assets[row["asset_key"]] = meta
                key = (row["asset_key"], row["software_key"])
                if row["software"] and key in installs:
                    raise ValidationError(
                        "Repeated software_key for this asset; keep one row per installation"
                    )
                if row["software"]:
                    installs.add(key)
                rows.append(row)
            except (ValidationError, ValueError) as error:
                message = (
                    "; ".join(error.messages) if isinstance(error, ValidationError) else "Invalid IP address"
                )
                errors.append(f"Row {number}: {message}")
        if not rows and not errors:
            errors.append("Add at least one asset row")
        return rows, errors
    except (UnicodeError, csv.Error, IndexError):
        raise ValidationError("Use a valid UTF-8 CSV file with a header row") from None


def asset_data(asset):
    return {
        "name": asset.name,
        "kind": asset.kind,
        "lifecycle": asset.lifecycle,
        "upstream_data": asset.upstream_data,
    }


def installation_data(installation):
    return {
        "asset": str(installation.asset_id),
        "product": installation.product_id,
        "version": installation.version,
        "build": installation.build,
        "edition": installation.edition,
        "is_operating_system": installation.is_operating_system,
        "component_type": installation.component_type,
    }


def plan(source, rows):
    keys = {row["asset_key"] for row in rows}
    bindings = {
        b.key: b for b in CSVAssetBinding.objects.filter(source=source, key__in=keys).select_related("asset")
    }
    baseline = {
        "source": str(source.pk),
        "mode": source.mode,
        "instance": str(source.instance_id),
        "bindings": {},
    }
    errors = []
    name_keys = {}
    for row in rows:
        if row["name"] in name_keys and name_keys[row["name"]] != row["asset_key"]:
            errors.append("Different asset keys use the same name; reconcile duplicate asset rows first")
        name_keys[row["name"]] = row["asset_key"]
    names = {row["name"] for row in rows}
    collisions = set(
        Asset.objects.filter(organization=source.organization, name__in=names)
        .exclude(pk__in=[b.asset_id for b in bindings.values()])
        .values_list("name", flat=True)
    )
    if collisions:
        errors.append(
            "An asset name already exists outside these CSV keys. Use individual editors; existing assets are not adopted by name."
        )
    for key, binding in bindings.items():
        asset = binding.asset
        current = asset_data(asset)
        records = {}
        if (
            asset.organization_id != source.organization_id
            or asset.source_id != source.pk
            or digest(current) != binding.managed_digest
        ):
            errors.append(
                f"Asset {key}: source or locally edited inventory differs from the last import; reconcile in the individual editor"
            )
        for software_key, item in binding.installations.items():
            installed = Installation.objects.filter(
                pk=item["id"], asset=asset, product__organization=source.organization
            ).first()
            records[software_key] = installation_data(installed) if installed else None
            if installed and hasattr(installed, "agent_component"):
                errors.append(
                    f"Asset {key}: software is managed by a Linux device; reconcile ownership first"
                )
            if not installed or digest(records[software_key]) != item["digest"]:
                errors.append(f"Asset {key}: software was edited elsewhere; reconcile before importing")
        baseline["bindings"][key] = {"asset": str(asset.pk), "data": current, "installed": records}
    return digest(baseline), errors


def preview(actor, org, raw):
    source = InventorySource.objects.get(organization=org)
    authorize(actor, org, source)
    rows, errors = parse(raw)
    baseline, conflicts = plan(source, rows)
    return InventoryCSVBatch.objects.create(
        organization=org,
        source=source,
        actor=actor,
        rows=rows,
        errors=errors + conflicts,
        baseline=baseline,
        expires_at=timezone.now() + timedelta(hours=24),
    )


@transaction.atomic
def commit(actor, org, batch_id):
    Organization.objects.select_for_update().get(pk=org.pk)
    try:
        source = InventorySource.objects.select_for_update(nowait=True).get(organization=org)
    except DatabaseError as error:
        if getattr(error.__cause__, "sqlstate", None) == "55P03":
            raise ValidationError(
                "Inventory is being updated. Your preview is retained; retry shortly."
            ) from None
        raise
    authorize(actor, org, source)
    batch = InventoryCSVBatch.objects.select_for_update().get(
        pk=batch_id, organization=org, actor=actor, source=source
    )
    if batch.status == "committed":
        return batch
    if batch.expires_at <= timezone.now() or batch.errors or batch.status != "preview":
        raise ValidationError("The preview expired or contains errors. Upload a corrected file.")
    baseline, errors = plan(source, batch.rows)
    if baseline != batch.baseline or errors:
        raise ValidationError(
            "Inventory changed since preview. Upload again and review the current differences."
        )
    created, updated, installed_count = 0, 0, 0
    touched = {}
    for row in batch.rows:
        key = row["asset_key"]
        binding = touched.get(key)
        if not binding:
            binding = CSVAssetBinding.objects.filter(source=source, key=key).select_related("asset").first()
            if not binding:
                asset = Asset(
                    organization=org, source=source, state="recorded", name=row["name"], kind=row["kind"]
                )
                binding = CSVAssetBinding(source=source, key=key, asset=asset)
                created += 1
            else:
                updated += 1
            asset = binding.asset
            asset.name, asset.kind = row["name"], row["kind"]
            data = dict(asset.upstream_data)
            for field in [
                "primary_ip4",
                "primary_ip6",
                "primary_ip4_dns_name",
                "primary_ip6_dns_name",
                "dns_name",
            ]:
                data.pop(field, None)
            if row["ip"]:
                field = "primary_ip" + str(ipaddress.ip_interface(row["ip"]).version)
                data[field], data[field + "_dns_name"] = row["ip"], row["domain"]
            data["dns_name"] = row["domain"]
            asset.upstream_data = data
            asset.full_clean()
            asset.save()
            binding.managed_digest = digest(asset_data(asset))
            binding.save()
            touched[key] = binding
        if row["software"]:
            product, _ = Product.objects.get_or_create(organization=org, name=row["software"], identifier="")
            previous = binding.installations.get(row["software_key"])
            installed = (
                Installation.objects.get(pk=previous["id"], asset=binding.asset)
                if previous
                else Installation(asset=binding.asset)
            )
            installed.product, installed.version = product, row["version"]
            installed.full_clean()
            installed.save()
            binding.installations[row["software_key"]] = {
                "id": installed.pk,
                "digest": digest(installation_data(installed)),
            }
            binding.save(update_fields=["installations"])
            from .product_matching import ensure_watch

            try:
                ensure_watch(product, actor)
            except ValidationError:
                pass
            ProductWatch.objects.filter(product=product).update(requested=True)
            installed_count += 1
    batch.status = "committed"
    batch.result = {"created": created, "updated": updated, "installations": installed_count}
    batch.save(update_fields=["status", "result"])
    audit(actor, org, "inventory.csv_committed", batch.pk, **batch.result)
    return batch
