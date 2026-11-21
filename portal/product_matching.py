"""Local, explainable product identities. Names never establish affectedness."""

import re
from django.conf import settings
from django.db import transaction
from django.db.models import F
from .access import audit
from .models import Product, ProductWatch

KEY_PATTERN = r"[a-z0-9][a-z0-9_.+ -]{0,119}"
KNOWN_PRODUCTS = {
    "misp": ("misp", "misp"),
    "apache log4j": ("apache", "log4j"),
    "log4j": ("apache", "log4j"),
    "microsoft exchange server": ("microsoft", "exchange_server"),
    "microsoft exchange": ("microsoft", "exchange_server"),
    "fortinet fortios": ("fortinet", "fortios"),
    "fortios": ("fortinet", "fortios"),
}
KNOWN_PACKAGES = {
    "pkg:maven/org.apache.logging.log4j/log4j-core": ("apache", "log4j"),
    "pkg:maven/org.apache.logging.log4j/log4j-api": ("apache", "log4j"),
}


def valid_key(value):
    return isinstance(value, str) and re.fullmatch(KEY_PATTERN, value) is not None and value == value.strip()


def suggestions(product):
    candidates = {}

    def add(pair, reason):
        candidates.setdefault(pair, []).append(reason)

    identifier = product.identifier.strip()
    if identifier.startswith("cpe:2.3:") and "\\" not in identifier:
        parts = identifier.split(":")
        if len(parts) == 13 and parts[2] in {"a", "h", "o"} and all(valid_key(key) for key in parts[3:5]):
            add(tuple(parts[3:5]), "Concrete CPE 2.3 vendor/product identity")
    package = identifier.split("?", 1)[0].split("#", 1)[0].split("@", 1)[0]
    if package in KNOWN_PACKAGES:
        add(KNOWN_PACKAGES[package], "Known package identity")
    name = " ".join(product.name.split()).casefold()
    if name in KNOWN_PRODUCTS:
        add(KNOWN_PRODUCTS[name], "Known product name (exact match)")
    return [
        {"vendor": vendor, "product_key": key, "reason": "; ".join(reasons)}
        for (vendor, key), reasons in candidates.items()
    ]


@transaction.atomic
def ensure_watch(product, actor=None, *, identity=None):
    # Same product lock as manual configuration; never replace/pause/re-enable a saved watch.
    product = Product.objects.select_for_update().get(pk=product.pk)
    existing = ProductWatch.objects.filter(product=product).first()
    if existing:
        if identity is not None and tuple(identity) != (existing.vendor, existing.product_key):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                "Existing product monitoring identity is preserved; review its mapping separately"
            )
        return existing, False
    if identity is not None:
        from django.core.exceptions import ValidationError

        if (
            not isinstance(identity, (tuple, list))
            or len(identity) != 2
            or not all(valid_key(key) for key in identity)
        ):
            raise ValidationError("Choose valid public manufacturer and product keys")
        matches = [
            {"vendor": identity[0], "product_key": identity[1], "reason": "Explicit public catalog selection"}
        ]
    else:
        matches = suggestions(product)
    if len(matches) != 1:
        return None, False
    match = matches[0]
    watch = ProductWatch(
        product=product,
        source_url=settings.VULNERABILITY_LOOKUP_URL.rstrip("/"),
        vendor=match["vendor"],
        product_key=match["product_key"],
        enabled=True,
        requested=True,
    )
    watch.full_clean()
    watch.save()
    audit(
        actor,
        product.organization,
        "vulnerability.watch_auto_configured",
        watch.pk,
        vendor=watch.vendor,
        product=watch.product_key,
        reason=match["reason"],
    )
    return watch, True


def enroll_products():
    from django.core.exceptions import ValidationError

    created = 0
    products = (
        Product.objects.filter(
            watch__isnull=True,
            installation__asset__lifecycle="active",
            installation__asset__organization_id=F("organization_id"),
            installation__asset__source__organization_id=F("organization_id"),
        )
        # Distro packages require distro-aware advisories, never upstream name guesses.
        .exclude(identifier__startswith="pkg:deb/")
        .exclude(identifier__startswith="pkg:rpm/")
        .distinct()
        .order_by("pk")
    )
    for product in products.iterator(chunk_size=200):
        if not suggestions(product):
            continue
        try:
            _, new = ensure_watch(product)
        except ValidationError:
            # Misconfigured operator source remains an explicit coverage gap, never a false success.
            continue
        created += int(new)
    return created


def catalog_cpe(vendor, product):
    """Only identities independently verified in NVD become a CPE automatically.

    Public CNA vendor/product keys are not necessarily CPE dictionary keys,
    nor do they prove the CPE part (application, OS or hardware).
    """
    if (vendor, product) == ("misp", "misp"):
        return "cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*"
    return ""
