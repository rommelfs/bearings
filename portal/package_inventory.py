"""Deterministic Debian/RPM inventory identities; never guesses upstream CVE applicability."""

import re
import json
from urllib.parse import quote, urlencode
from .agent_freshness import recent_component
from .models import AgentComponent, AgentReport, Installation, Product
from .access import audit

MAX_AUTO_PACKAGES = 5000


def identity(component, os):
    manager = component.manager
    if manager == "win-reg" and os.get("id") == "windows":
        # Registration identity is stable across version changes, scoped to its
        # exact location/view. No vendor CPE or executable architecture inferred.
        return {
            "product": "pkg:generic/windows-registration/" + component.key.split(":")[1],
            "name": component.name,
            "manager": manager,
            "distribution": "windows",
            "release": os.get("version", ""),
            "namespace_basis": "machine registry declaration; CVE applicability unknown",
        }
    if manager == "manifest":
        from .manifest_inventory import product_identifier

        return {
            "product": product_identifier(component),
            "name": component.name,
            "manager": "manifest",
            "basis": "locally configured version observation; runtime deployment is not attested",
        }
    distro = os.get("id", "").lower()
    release = os.get("version", "")
    if (
        manager not in {"dpkg", "rpm"}
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", distro)
        or distro == "unknown"
    ):
        return {}
    family = "deb" if manager == "dpkg" else "rpm"
    namespace = {
        "rhel": "redhat",
        "opensuse-leap": "opensuse",
        "opensuse-tumbleweed": "opensuse",
        "sles": "suse",
        "sled": "suse",
    }.get(distro, distro)
    name = component.name.lower() if manager == "dpkg" else component.name
    base = f"pkg:{family}/{quote(namespace, safe='')}/{quote(name, safe='')}"
    # Product identity stays stable across installed versions and host release upgrades.
    product = base + "?" + urlencode({"arch": component.architecture}, quote_via=quote)
    if len(product) > 255:
        return {}
    qualifiers = {"arch": component.architecture}
    if release and release != "unknown":
        qualifiers["distro"] = distro + "-" + release
    version = component.version
    if manager == "rpm" and ":" in version:
        epoch, rest = version.split(":", 1)
        if not epoch.isdigit():
            return {}
        qualifiers["epoch"] = epoch
        version = rest
    return {
        "product": product,
        "name": name,
        "purl": base
        + "@"
        + quote(version, safe=":")
        + "?"
        + urlencode(sorted(qualifiers.items()), quote_via=quote),
        "distribution": distro,
        "release": release,
        "manager": manager,
        "namespace_basis": "reported host OS; package repository/vendor not attested",
    }


def project(device):
    """Caller holds device/source locks. Create separate records, never claim a manual record."""
    if not device.auto_software:
        device.software_sync_pending = False
        return 0
    candidates = (
        device.components.filter(
            recent_component(),
            installation__isnull=True,
            inventory_excluded=False,
            manager__in=["dpkg", "rpm", "win-reg"],
            missing_since__isnull=True,
        )
        .exclude(package_identity__has_key="unsupported")
        .order_by("pk")
    )
    components = list(candidates[:MAX_AUTO_PACKAGES])
    legacy = {
        r.pk: json.loads(bytes(r.body))["os"]
        for r in AgentReport.objects.filter(
            pk__in={c.last_report_id for c in components if not c.package_identity}
        )
    }
    selected = []
    unsupported = []
    for c in components:
        # Only metadata from that component's report, not a later unrelated OS observation.
        if not c.package_identity:
            c.package_identity = identity(c, legacy[c.last_report_id])
        if c.package_identity:
            selected.append(c)
        else:
            c.package_identity = {"unsupported": True}
            unsupported.append(c)
    AgentComponent.objects.bulk_update(unsupported, ["package_identity"], batch_size=250)
    identities = {(c.package_identity["name"], c.package_identity["product"]) for c in selected}
    if not identities:
        device.software_sync_pending = candidates.exists()
        return 0
    identifiers = {identifier for _, identifier in identities}
    existing = {
        (p.name, p.identifier): p
        for p in Product.objects.filter(organization_id=device.organization_id, identifier__in=identifiers)
    }
    Product.objects.bulk_create(
        [
            Product(organization_id=device.organization_id, name=name, identifier=identifier)
            for name, identifier in sorted(identities)
            if (name, identifier) not in existing
        ],
        ignore_conflicts=True,
        batch_size=250,
    )
    products = {
        (p.name, p.identifier): p
        for p in Product.objects.filter(organization_id=device.organization_id, identifier__in=identifiers)
    }
    installations = Installation.objects.bulk_create(
        [
            Installation(
                asset_id=device.asset_id,
                product=products[(c.package_identity["name"], c.package_identity["product"])],
                version=c.version,
                is_operating_system=c.windows.get("kind") == "os",
            )
            for c in selected
        ],
        batch_size=250,
    )
    for c, i in zip(selected, installations):
        c.installation = i
        c.automatic_installation = True
    AgentComponent.objects.bulk_update(
        selected, ["installation", "automatic_installation", "package_identity"], batch_size=250
    )
    device.software_sync_pending = candidates.exists()
    audit(None, device.organization, "agent.software_inventoried", device.pk, entries=len(selected))
    return len(selected)
