import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
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
    notification_enabled = models.BooleanField(
        default=False, help_text="Explicitly include this contact in vulnerability notification previews"
    )
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
    component_type = models.CharField(
        max_length=10, default="software", choices=[("software", "Software"), ("firmware", "Firmware")]
    )
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
    source_severity = models.CharField(
        max_length=10,
        default="unknown",
        db_index=True,
        editable=False,
        choices=[(v, v.title()) for v in ["critical", "high", "medium", "low", "none", "unknown"]],
    )

    def save(self, *args, **kwargs):
        fields = kwargs.get("update_fields")
        if self._state.adding or fields is None or "payload" in fields:
            from .presentation import vulnerability_summary

            self.source_severity = vulnerability_summary(self.payload)["severity"].lower()
            if fields is not None:
                kwargs["update_fields"] = set(fields) | {"source_severity"}
        return super().save(*args, **kwargs)

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


class NotificationBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    mode = models.CharField(
        max_length=10, choices=[("circl", "CIRCL outreach"), ("company", "Internal company")]
    )
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True)
    filters = models.JSONField(default=dict)
    transport = models.CharField(
        max_length=10, default="file", choices=[("file", "Local file"), ("smtp", "SMTP acceptance")]
    )
    transport_fingerprint = models.CharField(max_length=64, blank=True)
    subject_template = models.CharField(max_length=250)
    body_template = models.TextField()
    status = models.CharField(max_length=20, default="draft")
    created_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(null=True)


class NotificationDelivery(models.Model):
    batch = models.ForeignKey(NotificationBatch, on_delete=models.PROTECT, related_name="deliveries")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    findings = models.ManyToManyField(Finding, through="NotificationDeliveryFinding")
    issues = models.ManyToManyField("AssetIssue", through="NotificationDeliveryIssue")
    snapshot = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    subject = models.CharField(max_length=250)
    body = models.TextField()
    status = models.CharField(max_length=20, default="draft")
    filed_at = models.DateTimeField(null=True)
    acknowledged_at = models.DateTimeField(null=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)


class NotificationReceipt(models.Model):
    """Committed before file I/O: an interrupted attempt is never silently retried."""

    fingerprint = models.CharField(max_length=64, unique=True)
    delivery = models.OneToOneField(NotificationDelivery, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class NotificationDeliveryFinding(models.Model):
    delivery = models.ForeignKey(NotificationDelivery, on_delete=models.PROTECT)
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["delivery", "finding"], name="unique_notification_finding")
        ]


class FlowIntelInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250)
    browser_url = models.URLField(max_length=250, blank=True)
    bearings_url = models.URLField(
        max_length=250, blank=True, help_text="Bearings browser origin for case links"
    )
    token_env_var = models.CharField(max_length=100)
    service_org_id = models.PositiveIntegerField(
        help_text="Expected CIRCL/service organization ID in FlowIntel"
    )
    enabled = models.BooleanField(default=True)
    allow_private = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @property
    def available(self):
        import os

        return self.enabled and not (
            os.getenv("BEARINGS_DEV_STACK") == "1"
            and self.name == "bundled-flowintel"
            and os.getenv("BEARINGS_FLOWINTEL") != "1"
        )

    def clean(self):
        import re
        from urllib.parse import urlsplit
        from .connectors.http import ConnectorError, validate_base

        for field in ["base_url", "browser_url", "bearings_url"]:
            value = getattr(self, field)
            if not value:
                continue
            try:
                parsed = urlsplit(value)
                if (
                    field == "bearings_url"
                    and settings.DEBUG
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1"}
                    and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
                ):
                    parsed.port
                else:
                    validate_base(value)
            except (ConnectorError, ValueError):
                raise ValidationError({field: "Use an approved credential-free HTTPS URL"}) from None
            setattr(self, field, value.rstrip("/"))
        if not self.base_url or not self.service_org_id:
            raise ValidationError("A FlowIntel endpoint and positive service organization ID are required")
        if not re.fullmatch(r"FLOWINTEL_[A-Z0-9_]*TOKEN", self.token_env_var):
            raise ValidationError({"token_env_var": "Use a FLOWINTEL_*TOKEN variable name, never its value"})
        if self.pk and FlowIntelCase.objects.filter(instance_id=self.pk).exists():
            old = FlowIntelInstance.objects.get(pk=self.pk)
            if any(
                getattr(old, field) != getattr(self, field)
                for field in ["base_url", "token_env_var", "service_org_id"]
            ):
                raise ValidationError(
                    "An instance with case identities cannot be repointed; configure a new instance"
                )


class FlowIntelCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(FlowIntelInstance, on_delete=models.PROTECT)
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name="flowintel_cases")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    title = models.CharField(max_length=240)
    description = models.TextField()
    deadline = models.DateField(null=True, blank=True)
    reason = models.TextField()
    state = models.CharField(max_length=20, default="draft")
    remote_id = models.PositiveIntegerField(null=True, blank=True)
    remote_uuid = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=250, blank=True)
    summary = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["instance", "finding"], name="unique_flowintel_finding"),
            models.UniqueConstraint(
                fields=["instance", "remote_id"],
                condition=Q(remote_id__isnull=False),
                name="unique_flowintel_remote_case",
            ),
        ]

    @property
    def case_url(self):
        from .connectors.http import validate_base, ConnectorError

        if not self.remote_id or not self.remote_uuid:
            return ""
        try:
            base = validate_base(self.instance.browser_url or self.instance.base_url).geturl().rstrip("/")
        except ConnectorError:
            return ""
        return f"{base}/case/{self.remote_id}"


class FlowIntelTask(models.Model):
    case = models.ForeignKey(FlowIntelCase, on_delete=models.PROTECT, related_name="tasks")
    step = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=240)
    description = models.TextField()
    state = models.CharField(max_length=20, default="pending")
    remote_id = models.PositiveIntegerField(null=True, blank=True)

    @property
    def label(self):
        return self.title.rsplit(" [", 1)[0]

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "step"], name="unique_flowintel_step")]


class AssetIssue(models.Model):
    """Common asset problem; linked CVE reviews keep their original assessment authority."""

    KINDS = [
        (key, label)
        for key, label in [
            ("vulnerability", "Vulnerability"),
            ("eol", "End of life"),
            ("support", "Support expiry"),
            ("license", "License expiry"),
            ("maintenance", "Maintenance expiry"),
            ("warranty", "Warranty expiry"),
            ("exposure", "Network exposure"),
            ("other", "Other asset issue"),
        ]
    ]
    STATUSES = [
        (key, key.replace("_", " ").title())
        for key in [
            "new",
            "under_review",
            "confirmed",
            "resolved",
            "accepted_risk",
            "false_positive",
        ]
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="asset_issues")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="issues")
    installation = models.ForeignKey(Installation, on_delete=models.PROTECT, null=True, blank=True)
    finding = models.OneToOneField(
        Finding, on_delete=models.PROTECT, null=True, blank=True, related_name="asset_issue"
    )
    kind = models.CharField(max_length=20, choices=KINDS)
    title = models.CharField(max_length=220)
    status = models.CharField(max_length=20, choices=STATUSES, default="new")
    priority = models.CharField(
        max_length=10,
        default="review",
        choices=[("critical", "Critical"), ("high", "High"), ("review", "Review"), ("low", "Low")],
    )
    owner_team = models.CharField(max_length=180, blank=True)
    event_date = models.DateField(
        null=True, blank=True, help_text="Reported end/expiry date; blank means unknown"
    )
    action_due = models.DateField(
        null=True, blank=True, help_text="Organization's action deadline, separate from expiry"
    )
    fact_scope = models.CharField(
        max_length=20,
        default="asset",
        choices=[
            ("asset", "This asset"),
            ("installation", "This installation"),
            ("vendor_lifecycle", "Vendor/product lifecycle"),
            ("entitlement", "Organization contract/entitlement"),
        ],
    )
    contract_reference = models.CharField(max_length=250, blank=True)
    source_label = models.CharField(max_length=250)
    source_url = models.URLField(max_length=500, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    fact_status = models.CharField(
        max_length=15,
        default="unverified",
        choices=[
            ("unverified", "Unverified assertion"),
            ("verified", "Verified against evidence"),
            ("disputed", "Disputed"),
            ("unknown", "Unknown"),
        ],
    )
    evidence_text = models.TextField(max_length=12000)
    consequence = models.TextField(max_length=4000, blank=True)
    next_action = models.TextField(max_length=4000, blank=True)
    operator_only = models.BooleanField(default=False)
    shareable = models.BooleanField(
        default=False, help_text="Evidence may be exported after a separate approval"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_asset_issues",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def current_status(self):
        return self.finding.status if self.finding_id else self.status

    @property
    def active(self):
        return self.current_status in {"new", "under_review", "confirmed"}

    @property
    def deadline(self):
        return self.action_due or self.event_date

    @property
    def timing(self):
        if not self.active:
            return "closed"
        if self.deadline is None:
            return "unknown"
        days = (self.deadline - timezone.localdate()).days
        return "overdue" if days < 0 else "soon" if days <= 30 else "scheduled"

    def clean(self):
        from .connectors.http import ConnectorError, validate_base

        if self.asset_id and (
            self.asset.organization_id != self.organization_id
            or self.asset.source.organization_id != self.organization_id
        ):
            raise ValidationError("Issue asset/source must belong to the issue organization")
        if self.installation_id and (
            self.installation.asset_id != self.asset_id
            or self.installation.product.organization_id != self.organization_id
        ):
            raise ValidationError("Issue installation must belong to this asset and organization")
        if (self.kind == "vulnerability") != bool(self.finding_id):
            raise ValidationError("Vulnerability issues must reference an existing finding")
        if self.finding_id and (
            self.finding.organization_id != self.organization_id
            or self.finding.installation_id != self.installation_id
            or self.finding.record.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Issue finding and evidence must belong to this organization and installation"
            )
        if self.fact_scope in {"installation", "vendor_lifecycle"} and not self.installation_id:
            raise ValidationError("Select an installation for product lifecycle facts")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError("Evidence validity ends before it begins")
        if self.observed_at and self.observed_at > timezone.now():
            raise ValidationError("Observation time cannot be in the future")
        if self.source_url:
            try:
                validate_base(self.source_url)
            except ConnectorError:
                raise ValidationError({"source_url": "Use a credential-free HTTPS evidence URL"}) from None
        if self.pk:
            old = AssetIssue.objects.filter(pk=self.pk).first()
            if old and any(
                getattr(old, field) != getattr(self, field)
                for field in ["organization_id", "asset_id", "installation_id", "finding_id", "kind"]
            ):
                raise ValidationError("Issue target/type cannot be repointed; create a separate issue")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(kind="vulnerability", finding__isnull=False)
                | (~Q(kind="vulnerability") & Q(finding__isnull=True)),
                name="issue_vulnerability_reference",
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "event_date"])]


class IssueRevision(models.Model):
    issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="revisions")
    digest = models.CharField(max_length=64)
    snapshot = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issue", "digest"], name="unique_issue_revision")]


class IssueHistory(models.Model):
    issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="history")
    revision = models.ForeignKey(IssueRevision, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    changes = models.JSONField(default=dict)
    reason = models.TextField(max_length=4000)
    created_at = models.DateTimeField(default=timezone.now)


class IssueRiskLink(models.Model):
    issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="risk_scenarios")
    issue_revision = models.ForeignKey(IssueRevision, on_delete=models.PROTECT)
    risk_revision = models.ForeignKey(MOSPRiskRevision, on_delete=models.PROTECT)
    reason = models.TextField(max_length=4000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(max_length=4000, blank=True)

    def clean(self):
        if self.issue_id and self.issue_revision_id and self.issue_revision.issue_id != self.issue_id:
            raise ValidationError("Risk reference must pin evidence from the same issue")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "issue_revision", "risk_revision"],
                condition=Q(withdrawn_at__isnull=True),
                name="unique_active_issue_risk",
            )
        ]


class RTInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Blank: CIRCL-only service queue; otherwise this company's queue",
    )
    base_url = models.URLField(max_length=250)
    browser_url = models.URLField(max_length=250, blank=True)
    token_env_var = models.CharField(max_length=100)
    queue_id = models.PositiveIntegerField()
    product = models.CharField(max_length=10, default="rt", choices=[("rt", "RT"), ("rtir", "RTIR queue")])
    incident_queue_id = models.PositiveIntegerField(null=True, blank=True)
    custom_fields = models.JSONField(
        default=dict, blank=True, help_text="Operator-approved numeric custom-field IDs to fixed text values"
    )
    enabled = models.BooleanField(default=False)
    allow_private = models.BooleanField(default=False)
    private_queue_confirmed = models.BooleanField(
        default=False, help_text="Operator verified queue access and notification scrips"
    )

    def __str__(self):
        return self.name

    def clean(self):
        import re
        from .connectors.http import ConnectorError, validate_base

        try:
            validate_base(self.base_url)
            if self.browser_url:
                validate_base(self.browser_url)
        except ConnectorError:
            raise ValidationError("Configure credential-free HTTPS RT API/browser bases") from None
        if not re.fullmatch(r"RT_[A-Z0-9_]*TOKEN", self.token_env_var) or not self.queue_id:
            raise ValidationError("Configure an RT_*TOKEN reference and positive queue ID")
        if (
            not isinstance(self.custom_fields, dict)
            or len(self.custom_fields) > 20
            or any(
                not re.fullmatch(r"[1-9][0-9]{0,8}", str(k)) or not isinstance(v, str) or len(v) > 1000
                for k, v in self.custom_fields.items()
            )
        ):
            raise ValidationError(
                "Custom fields must be at most 20 numeric IDs with bounded fixed text values"
            )
        if self.product == "rtir" and (
            self.organization_id or not self.incident_queue_id or self.incident_queue_id == self.queue_id
        ):
            raise ValidationError(
                "RTIR coordination requires CIRCL-only, distinct Incident and Investigation queues"
            )
        if self.product != "rtir" and self.incident_queue_id:
            raise ValidationError("An Incident queue requires an RTIR connection")
        if self.pk and RTTicket.objects.filter(instance_id=self.pk).exists():
            old = RTInstance.objects.get(pk=self.pk)
            if any(
                getattr(old, field) != getattr(self, field)
                for field in [
                    "base_url",
                    "token_env_var",
                    "queue_id",
                    "incident_queue_id",
                    "organization_id",
                    "product",
                ]
            ):
                raise ValidationError("An RT connection with hand-offs cannot be repointed")


class RTTicket(models.Model):
    role = models.CharField(
        max_length=20,
        default="ticket",
        choices=[("ticket", "Ticket"), ("incident", "Incident"), ("investigation", "Investigation")],
    )
    incident = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="investigations"
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(RTInstance, on_delete=models.PROTECT)
    issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="rt_tickets")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    subject = models.CharField(max_length=220)
    content = models.TextField()
    reason = models.TextField(max_length=3000)
    state = models.CharField(max_length=20, default="draft")
    remote_id = models.PositiveIntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    error = models.CharField(max_length=250, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    def clean(self):
        if self.instance.product == "rtir":
            if self.role not in {"incident", "investigation"}:
                raise ValidationError("RTIR hand-offs require an explicit Incident or Investigation role")
        elif self.role != "ticket":
            raise ValidationError("Incident and Investigation lifecycles require RTIR")
        if self.role == "investigation":
            if (
                not self.incident_id
                or self.incident_id == self.pk
                or self.incident.role != "incident"
                or self.incident.instance_id != self.instance_id
            ):
                raise ValidationError("An Investigation requires an Incident on the same RTIR connection")
        elif self.incident_id:
            raise ValidationError("Only an Investigation may have a parent Incident")
        old = type(self).objects.filter(pk=self.pk).first()
        if (
            old
            and old.attempted_at
            and any(
                getattr(old, field) != getattr(self, field)
                for field in [
                    "instance_id",
                    "issue_id",
                    "role",
                    "incident_id",
                    "subject",
                    "content",
                    "fingerprint",
                    "reason",
                    "creator_id",
                ]
            )
        ):
            raise ValidationError("An attempted RT export and its approved relationships are immutable")

    def __str__(self):
        return self.subject or str(self.pk)

    @property
    def ticket_url(self):
        if not self.remote_id or not self.last_success:
            return ""
        from .connectors.http import validate_base

        return validate_base(self.instance.browser_url or self.instance.base_url).geturl().rstrip("/") + (
            f"/RTIR/Display.html?id={self.remote_id}"
            if self.instance.product == "rtir"
            else f"/Ticket/Display.html?id={self.remote_id}"
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["instance", "issue", "role"], name="unique_rt_issue_role"),
            models.CheckConstraint(
                condition=(
                    Q(role="investigation", incident__isnull=False)
                    | Q(role__in=["ticket", "incident"], incident__isnull=True)
                ),
                name="rt_role_parent_consistent",
            ),
            models.UniqueConstraint(
                fields=["instance", "remote_id"],
                condition=Q(remote_id__isnull=False),
                name="unique_rt_identity",
            ),
        ]


class PlumInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250)
    token_env_var = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=False)
    allow_private = models.BooleanField(default=False)
    fixture = models.BooleanField(
        default=False, help_text="DEBUG-only offline synthetic data; network requests prohibited"
    )
    organizations = models.ManyToManyField(
        Organization,
        blank=True,
        related_name="plum_instances",
        help_text="Organizations explicitly allowed to read their scoped observations",
    )

    def __str__(self):
        return self.name

    def clean(self):
        import re
        from .connectors.http import ConnectorError, validate_base

        try:
            validate_base(self.base_url)
        except ConnectorError:
            raise ValidationError("Plum Island requires an approved credential-free HTTPS endpoint") from None
        if self.fixture and not settings.DEBUG:
            raise ValidationError("Synthetic Plum sources require DEBUG")
        if not self.fixture and not re.fullmatch(r"PLUM_[A-Z0-9_]*TOKEN", self.token_env_var):
            raise ValidationError("Use an operator-managed PLUM_*TOKEN reference for the API JWT")
        if self.pk and PlumSnapshot.objects.filter(source_id=self.pk).exists():
            old = PlumInstance.objects.get(pk=self.pk)
            if any(
                getattr(old, field) != getattr(self, field)
                for field in ["base_url", "token_env_var", "fixture"]
            ):
                raise ValidationError("A Plum source with observations cannot be repointed")


class PlumSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="plum_snapshots")
    source = models.ForeignKey(PlumInstance, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True)
    scope_claim = models.ForeignKey(InfrastructureClaim, on_delete=models.PROTECT)
    proof_kind = models.CharField(max_length=10)
    proof_value = models.CharField(max_length=255)
    proof_context = models.CharField(max_length=100, blank=True)
    proof_from = models.DateTimeField()
    proof_until = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField()
    window_start = models.DateTimeField()
    window_stop = models.DateTimeField()
    state = models.CharField(
        max_length=15, choices=[("indexed", "Indexed"), ("not_indexed", "Never indexed")]
    )
    report_count = models.PositiveIntegerField(default=0)
    ports = models.JSONField(default=list)
    source_digest = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    ingested_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "organization", "fingerprint"], name="unique_plum_snapshot"
            ),
            models.CheckConstraint(
                condition=Q(window_stop__gte=F("window_start")), name="ordered_plum_window"
            ),
        ]
        indexes = [models.Index(fields=["organization", "ip", "window_stop"])]


class ExposureReview(models.Model):
    issue = models.OneToOneField(AssetIssue, on_delete=models.PROTECT, related_name="exposure_review")
    observation = models.ForeignKey(PlumSnapshot, on_delete=models.PROTECT)
    identity = models.CharField(max_length=64, unique=True)
    port = models.PositiveIntegerField()
    protocol = models.CharField(max_length=10)


class NotificationDeliveryIssue(models.Model):
    delivery = models.ForeignKey(NotificationDelivery, on_delete=models.PROTECT)
    issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["delivery", "issue"], name="unique_notification_issue")
        ]


class NotificationSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    mode = models.CharField(max_length=10, choices=[("company", "Company"), ("circl", "CIRCL")])
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True)
    filters = models.JSONField(default=dict)
    subject_template = models.CharField(max_length=250)
    body_template = models.TextField(max_length=12000)
    enabled = models.BooleanField(default=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_fingerprint = models.CharField(max_length=64, blank=True)
    last_batch = models.ForeignKey(NotificationBatch, on_delete=models.PROTECT, null=True, blank=True)
    error = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class FederationGrant(models.Model):
    """Explicit single-company export permission; only a digest of its bearer secret is retained."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64)
    client_id = models.UUIDField()
    inventory = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class CompanyInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    remote_organization = models.UUIDField(help_text="Export identity supplied by the company grant")
    client_id = models.UUIDField(default=uuid.uuid4, editable=False)
    base_url = models.URLField(max_length=250)
    token_env_var = models.CharField(max_length=100)
    enabled = models.BooleanField(default=False)
    allow_private = models.BooleanField(default=False)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return self.name

    def clean(self):
        import re
        from .connectors.http import ConnectorError, validate_base

        try:
            validate_base(self.base_url)
        except ConnectorError:
            raise ValidationError("Company instances require approved credential-free HTTPS") from None
        if not re.fullmatch(r"FEDERATION_[A-Z0-9_]*TOKEN", self.token_env_var):
            raise ValidationError("Use a server-side FEDERATION_*TOKEN credential reference")
        if self.pk and FederatedReport.objects.filter(source_id=self.pk).exists():
            old = CompanyInstance.objects.get(pk=self.pk)
            if any(
                getattr(old, f) != getattr(self, f)
                for f in ["organization_id", "remote_organization", "client_id", "base_url", "token_env_var"]
            ):
                raise ValidationError("A company source with reports cannot be repointed")


class FederatedReport(models.Model):
    source = models.ForeignKey(CompanyInstance, on_delete=models.PROTECT, related_name="reports")
    resource = models.CharField(max_length=20, choices=[("issues", "Issues"), ("inventory", "Inventory")])
    remote_id = models.UUIDField()
    payload = models.JSONField()
    digest = models.CharField(max_length=64)
    seen_at = models.DateTimeField()
    missing_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "resource", "remote_id"], name="unique_federated_report"
            )
        ]
