"""One-time local geography extension for provenance-owned showcase companies only."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction, OperationalError
from .access import audit, require
from .demo_data import KEY
from .geography import address_digest
from .models import Asset, DemoDataset, DemoObject, InventorySource, Organization, OrganizationLocation

PLACES = [
    ("1111", "Luxembourg"),
    ("4001", "Esch-sur-Alzette"),
    ("4501", "Differdange"),
    ("3401", "Dudelange"),
    ("9201", "Diekirch"),
    ("9001", "Ettelbruck"),
    ("9501", "Wiltz"),
    ("9701", "Clervaux"),
    ("6401", "Echternach"),
    ("5501", "Remich"),
]


@transaction.atomic
def fill_showcase_addresses(actor):
    require(actor.is_active and actor.is_superuser)
    if not settings.DEBUG:
        raise ValidationError("Synthetic address extension requires DEBUG")
    dataset = DemoDataset.objects.select_for_update().filter(key=KEY, state="active").first()
    if not dataset:
        return 0
    groups = {}
    for label, pk in DemoObject.objects.filter(dataset=dataset).values_list("model_label", "object_pk"):
        groups.setdefault(label, set()).add(pk)
    progress = dataset.configuration.get("map_addresses_v1", {"processed": [], "applied": {}})
    done = set(progress["processed"])
    filled = 0
    orgs = (
        Organization.objects.select_for_update()
        .filter(pk__in=groups.get("portal.organization", []))
        .order_by("pk")
    )
    for i, org in enumerate(orgs):
        key = str(org.pk)
        if key in done:
            continue
        # A source writer may need an Org FK lock. Never wait for its source
        # while holding the organization row; retry this company on a later run.
        try:
            with transaction.atomic():
                source = (
                    InventorySource.objects.select_for_update(nowait=True).filter(organization=org).first()
                )
        except OperationalError:
            continue
        safe = (
            source
            and str(source.pk) in groups.get("portal.inventorysource", set())
            and source.mode == "development"
            and not source.instance_id
            and not source.import_enabled
        )
        if safe:
            safe = (
                not Asset.objects.filter(organization=org)
                .exclude(pk__in=groups.get("portal.asset", []))
                .exists()
            )
        if safe:
            safe = (
                not Asset.objects.filter(organization=org)
                .exclude(source=source, upstream_data__fixture=True)
                .exists()
            )
            safe = safe and not OrganizationLocation.objects.filter(organization=org).exists()
        if safe and not org.postal_address.strip():
            postal, town = PLACES[i % len(PLACES)]
            org.postal_address = f"SYNTHETIC ADDRESS · {i + 1}, rue des Exemples (fictional street)\nL-{postal} {town}\nLuxembourg"
            org.save(update_fields=["postal_address"])
            progress["applied"][key] = address_digest(org.postal_address)
            filled += 1
        done.add(key)
    progress["processed"] = sorted(done)
    dataset.configuration = {**dataset.configuration, "map_addresses_v1": progress}
    dataset.save(update_fields=["configuration"])
    if filled:
        audit(actor, None, "demo.addresses_added", dataset.key, count=filled)
    return filled
