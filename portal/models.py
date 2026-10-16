import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Organization(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    operator_visibility = models.BooleanField(
        default=False, help_text="Allow CIRCL analysts to access this organization"
    )

    def __str__(self):
        return self.name


class Membership(models.Model):
    ROLES = [("admin", "Organization administrator"), ("editor", "Inventory editor"), ("reader", "Reader")]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="unique_membership")]


class AuditEvent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=180, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)


class Contact(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=180)
    role = models.CharField(max_length=120, default="Primary security contact")
    email = models.EmailField()
    phone = models.CharField(max_length=80, blank=True)
    emergency_phone = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=30, default="en")
    time_zone = models.CharField(max_length=60, default="Europe/Luxembourg")
    availability = models.CharField(
        max_length=200, blank=True, help_text="Declared arrangements; not verified by email"
    )
    secure_communication = models.TextField(blank=True)
    scope = models.CharField(max_length=200, blank=True)
    escalation_order = models.PositiveSmallIntegerField(default=1)
    reachable_at = models.DateTimeField(null=True, blank=True)
    invalid_delivery = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    next_review = models.DateField(null=True, blank=True)
    availability_confirmed_at = models.DateTimeField(null=True, blank=True)

    @property
    def overdue(self):
        return not self.next_review or self.next_review <= timezone.localdate()


class ContactToken(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class InfrastructureClaim(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="claims")
    kind = models.CharField(
        max_length=10,
        choices=[
            ("ip", "IP address"),
            ("network", "IP prefix"),
            ("range", "IP range (start-end)"),
            ("domain", "Domain or hostname"),
        ],
    )
    value = models.CharField(max_length=255)
    network_context = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=12,
        choices=[(x, x.title()) for x in ["declared", "verified", "disputed", "expired"]],
        default="declared",
    )
    method = models.CharField(max_length=200, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    def clean(self):
        from .scope import normalize

        self.value = normalize(self.kind, self.value)
        if self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError("End of assignment must follow its start")


class InventorySource(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="inventory_source"
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(
        max_length=12, choices=[("development", "DEVELOPMENT fixture"), ("central", "Central NetBox")]
    )
    tenant_id = models.PositiveIntegerField(null=True, blank=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    def clean(self):
        previous = type(self).objects.filter(pk=self.pk).first()
        if (
            previous
            and previous.asset_set.exists()
            and (
                previous.mode != self.mode
                or previous.tenant_id != self.tenant_id
                or previous.organization_id != self.organization_id
            )
        ):
            raise ValidationError(
                "Existing inventory binding cannot be repointed; perform a reviewed source migration"
            )
        if self.mode == "central" and not self.tenant_id:
            raise ValidationError("Central NetBox requires an operator-assigned tenant ID")


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="assets")
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    kind = models.CharField(
        max_length=20, choices=[(x, x.title()) for x in ["server", "desktop", "laptop", "appliance", "vm"]]
    )
    criticality = models.CharField(
        max_length=10, choices=[("normal", "Normal"), ("high", "High")], default="normal"
    )
    lifecycle = models.CharField(
        max_length=20, default="active", choices=[("active", "Active"), ("retired", "Retired")]
    )
    responsible_team = models.CharField(max_length=180, blank=True)
    object_type = models.CharField(max_length=60, default="dcim.device")
    external_id = models.CharField(max_length=100, blank=True)
    state = models.CharField(
        max_length=12, default="pending", choices=[(x, x.title()) for x in ["pending", "synced", "failed"]]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "object_type", "external_id"],
                condition=~Q(external_id=""),
                name="unique_external_identity",
            )
        ]

    def clean(self):
        if self.source_id and self.organization_id != self.source.organization_id:
            raise ValidationError("Asset and source must belong to the same organization")


class InventoryWrite(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="write")
    attempts = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True)
    completed_at = models.DateTimeField(null=True)
    next_attempt = models.DateTimeField(default=timezone.now)


class Product(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=180)
    identifier = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional CPE or Package URL; manually supplied, not validated applicability",
    )

    def __str__(self):
        return self.name + (f" ({self.identifier})" if self.identifier else " (unnormalized)")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "name", "identifier"], name="unique_product")
        ]


class Installation(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="installations")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    version = models.CharField(max_length=120, blank=True, help_text="Blank means unknown")
    edition = models.CharField(max_length=120, blank=True)
    build = models.CharField(max_length=120, blank=True)
    is_operating_system = models.BooleanField(default=False)

    def clean(self):
        if self.asset_id and self.product_id and self.asset.organization_id != self.product.organization_id:
            raise ValidationError("Installation must not link organizations")


class SourceRecord(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    source = models.CharField(max_length=250)
    external_id = models.CharField(max_length=120)
    payload = models.JSONField()
    ingested_at = models.DateTimeField(default=timezone.now)
    shareable = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "source", "external_id"], name="unique_record")
        ]


class Finding(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="findings")
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE)
    record = models.ForeignKey(SourceRecord, on_delete=models.PROTECT)
    category = models.CharField(max_length=50, default="technological_relevance")
    analyst_applicability = models.CharField(max_length=20, default="unassessed")
    confidence = models.CharField(max_length=20, default="unassessed")
    priority = models.CharField(max_length=20, default="review")
    applicability = models.CharField(max_length=20, default="unknown")
    status = models.CharField(
        max_length=20,
        default="new",
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["new", "under_review", "confirmed", "resolved", "false_positive", "accepted_risk"]
        ],
    )
    explanation = models.TextField()
    rule = models.CharField(max_length=100, default="manual-cve-review/v1")
    observed_at = models.DateTimeField(null=True, blank=True)
    evaluated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["installation", "record", "rule"], name="deduplicate_finding")
        ]

    def clean(self):
        if self.installation_id and self.installation.asset.organization_id != self.organization_id:
            raise ValidationError("Finding installation belongs to another organization")
        if self.record_id and self.record.organization_id != self.organization_id:
            raise ValidationError("Finding evidence belongs to another organization")


class FindingHistory(models.Model):
    finding = models.ForeignKey(Finding, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    previous_assessment = models.CharField(max_length=20, default="unassessed")
    assessment = models.CharField(max_length=20, default="unassessed")
    previous_status = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    reason = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
