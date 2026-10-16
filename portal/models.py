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


class NetBoxInstance(models.Model):
    """Operator-approved endpoint and capabilities; credentials remain in the environment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250, help_text="Approved HTTPS endpoint; never include credentials")
    browser_url = models.URLField(
        max_length=250,
        blank=True,
        help_text="Optional operator-approved HTTPS browser base; API credentials are never sent here",
    )
    token_env_var = models.CharField(
        max_length=100, help_text="Environment variable NAME only, e.g. NETBOX_ACME_TOKEN"
    )
    auth_scheme = models.CharField(
        max_length=6,
        choices=[("Bearer", "Bearer (current tokens)"), ("Token", "Token (legacy)")],
        default="Bearer",
    )
    access_mode = models.CharField(
        max_length=12,
        choices=[("read_only", "Read only"), ("read_write", "Read and write")],
        default="read_only",
    )
    enabled = models.BooleanField(default=True)
    allow_private = models.BooleanField(
        default=False, help_text="Explicit approval for a private/VPN destination"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Dedicated organization, or blank for a shared instance requiring tenant-scoped bindings",
    )
    site_id = models.PositiveIntegerField(null=True, blank=True)
    role_id = models.PositiveIntegerField(null=True, blank=True)
    device_type_id = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

    def clean(self):
        import re
        from .connectors.http import ConnectorError, validate_base

        try:
            self.base_url = validate_base(self.base_url).geturl().rstrip("/")
        except ConnectorError as exc:
            raise ValidationError({"base_url": str(exc)}) from None
        if self.browser_url:
            try:
                self.browser_url = validate_base(self.browser_url).geturl().rstrip("/")
            except ConnectorError as exc:
                raise ValidationError({"browser_url": str(exc)}) from None
        if not re.fullmatch(r"NETBOX_[A-Z0-9_]*TOKEN", self.token_env_var):
            raise ValidationError(
                {"token_env_var": "Use a NETBOX_*TOKEN environment variable name, never a token value"}
            )
        previous = type(self).objects.filter(pk=self.pk).first()
        if (
            previous
            and previous.inventorysource_set.exists()
            and (
                previous.base_url.rstrip("/") != self.base_url
                or previous.organization_id != self.organization_id
            )
        ):
            raise ValidationError(
                "A bound instance endpoint/ownership is immutable; perform a reviewed source migration"
            )


class InventorySource(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="inventory_source"
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(
        max_length=12,
        choices=[
            ("development", "DEVELOPMENT fixture"),
            ("central", "Central NetBox"),
            ("external", "Organization NetBox"),
        ],
    )
    instance = models.ForeignKey(NetBoxInstance, on_delete=models.PROTECT, null=True, blank=True)
    tenant_id = models.PositiveIntegerField(null=True, blank=True)
    last_read_attempt = models.DateTimeField(null=True, blank=True)
    last_read_success = models.DateTimeField(null=True, blank=True)
    read_error = models.CharField(max_length=200, blank=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    import_enabled = models.BooleanField(default=True, help_text="Enable periodic GET-only inventory import")
    import_interval_minutes = models.PositiveIntegerField(default=15)
    import_requested = models.BooleanField(default=False, editable=False)
    last_import_attempt = models.DateTimeField(null=True, blank=True)
    last_import_success = models.DateTimeField(null=True, blank=True)
    import_error = models.CharField(max_length=200, blank=True)
    import_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(import_interval_minutes__gte=1), name="positive_import_interval"
            )
        ]

    @property
    def import_stale(self):
        from datetime import timedelta

        return not self.last_import_success or timezone.now() - self.last_import_success > timedelta(
            minutes=2 * self.import_interval_minutes
        )

    def clean(self):
        if self.import_interval_minutes < 1:
            raise ValidationError({"import_interval_minutes": "Use an interval of at least one minute"})
        previous = type(self).objects.filter(pk=self.pk).first()
        if (
            previous
            and previous.asset_set.exists()
            and (
                previous.mode != self.mode
                or previous.tenant_id != self.tenant_id
                or previous.organization_id != self.organization_id
                or (previous.instance_id is not None and previous.instance_id != self.instance_id)
            )
        ):
            raise ValidationError(
                "Existing inventory binding cannot be repointed; perform a reviewed source migration"
            )
        if self.tenant_id is not None and self.tenant_id < 1:
            raise ValidationError("NetBox tenant ID must be positive or explicitly unset")
        if self.mode == "development":
            if self.instance_id:
                raise ValidationError("Development sources cannot use a live NetBox instance")
        else:
            if not self.instance_id:
                raise ValidationError("Select an operator-approved NetBox instance")
            if self.instance.organization_id and self.instance.organization_id != self.organization_id:
                raise ValidationError("Dedicated NetBox instance belongs to another organization")
            if not self.tenant_id and self.instance.organization_id != self.organization_id:
                raise ValidationError("Shared NetBox instances require an explicit tenant ID")

    @property
    def can_write(self):
        if self.mode == "development":
            return self.instance_id is None
        return bool(
            self.mode in {"central", "external"}
            and self.instance_id
            and self.instance.enabled
            and self.instance.access_mode == "read_write"
            and (self.tenant_id is None or self.tenant_id > 0)
            and (not self.instance.organization_id or self.instance.organization_id == self.organization_id)
            and (self.tenant_id or self.instance.organization_id == self.organization_id)
        )


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="assets")
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    kind = models.CharField(
        max_length=20,
        choices=[
            (x, x.title()) for x in ["server", "desktop", "laptop", "appliance", "vm", "ip_address", "prefix"]
        ],
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

    upstream_data = models.JSONField(default=dict, blank=True)
    inventory_seen_at = models.DateTimeField(null=True, blank=True)
    missing_since = models.DateTimeField(null=True, blank=True)
    missing_reviewed_at = models.DateTimeField(null=True, blank=True)
    missing_review_reason = models.CharField(max_length=1000, blank=True)

    @property
    def source_url(self):
        from .connectors.http import ConnectorError, validate_base

        paths = {
            "dcim.device": "dcim/devices",
            "virtualization.virtualmachine": "virtualization/virtual-machines",
            "ipam.ipaddress": "ipam/ip-addresses",
            "ipam.prefix": "ipam/prefixes",
        }
        if not self.source.instance_id or self.object_type not in paths or not self.external_id.isdecimal():
            return ""
        try:
            base = (
                validate_base(self.source.instance.browser_url or self.source.instance.base_url)
                .geturl()
                .rstrip("/")
            )
        except ConnectorError:
            return ""
        return f"{base}/{paths[self.object_type]}/{self.external_id}/"

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


class SourceRecordRevision(models.Model):
    record = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name="revisions")
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["record", "content_hash"], name="unique_evidence_revision")
        ]


class MOSPSource(models.Model):
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250, default="https://objects.monarc.lu")
    publisher = models.CharField(max_length=100, default="MONARC")
    language = models.CharField(max_length=2, default="EN")
    enabled = models.BooleanField(default=True)
    refresh_minutes = models.PositiveIntegerField(default=1440)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name

    def clean(self):
        from .connectors.http import validate_base, ConnectorError

        try:
            self.base_url = validate_base(self.base_url).geturl().rstrip("/")
        except ConnectorError as exc:
            raise ValidationError({"base_url": str(exc)}) from None
        if self.language not in {"EN", "DE", "FR", "NL"} or self.refresh_minutes < 1:
            raise ValidationError("Choose a supported language and positive refresh interval")
        old = type(self).objects.filter(pk=self.pk).first()
        if (
            old
            and old.risks.exists()
            and (old.base_url, old.publisher, old.language) != (self.base_url, self.publisher, self.language)
        ):
            raise ValidationError("An imported catalog source cannot be repointed")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(refresh_minutes__gte=1), name="positive_catalog_interval")
        ]


class MOSPRisk(models.Model):
    source = models.ForeignKey(MOSPSource, on_delete=models.PROTECT, related_name="risks")
    uuid = models.UUIDField()
    external_id = models.PositiveIntegerField()
    description = models.TextField()
    payload = models.JSONField()
    content_hash = models.CharField(max_length=64)
    current_revision = models.ForeignKey(
        "MOSPRiskRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    last_seen = models.DateTimeField(default=timezone.now)
    missing_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "uuid"], name="unique_mosp_risk")]

    def __str__(self):
        return self.description[:180]

    @property
    def source_url(self):
        return self.source.base_url + "/api/v2/object/?uuid=" + str(self.uuid)


class MOSPRiskRevision(models.Model):
    risk = models.ForeignKey(MOSPRisk, on_delete=models.PROTECT, related_name="revisions")
    content_hash = models.CharField(max_length=64)
    risk_hash = models.CharField(max_length=64)
    payload = models.JSONField(help_text="Pinned CC0 risk, asset type, threat and general weakness")
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["risk", "content_hash"], name="unique_mosp_revision")]


class RiskLink(models.Model):
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name="risk_links")
    evidence_revision = models.ForeignKey(SourceRecordRevision, on_delete=models.PROTECT)
    risk_revision = models.ForeignKey(MOSPRiskRevision, on_delete=models.PROTECT)
    reason = models.TextField(max_length=4000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(max_length=4000, blank=True)

    def clean(self):
        if (
            self.finding_id
            and self.evidence_revision_id
            and self.finding.record_id != self.evidence_revision.record_id
        ):
            raise ValidationError("Risk link evidence must belong to the selected finding")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["finding", "evidence_revision", "risk_revision"],
                condition=Q(withdrawn_at__isnull=True),
                name="unique_active_risk_link",
            )
        ]
