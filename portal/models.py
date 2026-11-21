import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
from django.db.models.functions import Coalesce, Upper
from django.utils import timezone


class Organization(models.Model):
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="merged_organizations",
        editable=False,
    )
    name = models.CharField(max_length=180)
    postal_address = models.TextField(max_length=1000, blank=True)
    slug = models.SlugField(unique=True)
    misp_org_uuid = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        help_text="Optional MISP organization reference, manually checked by the platform operator. This is not proof of a user's membership.",
    )
    misp_uuid_attested_at = models.DateTimeField(null=True, blank=True)
    misp_uuid_attested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="misp_organization_attestations",
    )
    operator_visibility = models.BooleanField(
        default=False, help_text="Allow CIRCL analysts to access this organization"
    )

    @property
    def display_label(self):
        label = f"{self.name} · {self.slug} · #{self.pk}"
        return label + (f" · Archived → #{self.merged_into_id}" if self.merged_into_id else "")

    def __str__(self):
        return self.display_label


class Membership(models.Model):
    ROLES = [("admin", "Organization administrator"), ("editor", "Inventory editor"), ("reader", "Reader")]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLES)

    def __str__(self):
        return f"{self.user.get_username()} · {self.organization.name} · {self.get_role_display()}"

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
    function = models.CharField(
        max_length=12,
        default="security",
        choices=[
            ("security", "Security"),
            ("technical", "Technical owner"),
            ("management", "Management / escalation"),
            ("dpo", "Data protection officer"),
        ],
    )
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

    def __str__(self):
        return f"{self.name} · {self.get_function_display()} · {self.email}"

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
    virtualization_tags = models.JSONField(default=dict, blank=True, editable=False)
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
    agent_export_policy = models.JSONField(default=dict, blank=True, editable=False)
    agent_managed = models.BooleanField(default=False, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="inventory_source"
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(
        max_length=12,
        choices=[
            ("development", "DEVELOPMENT fixture"),
            ("manual", "Company-reported inventory"),
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
        if self.mode in {"development", "manual"}:
            if self.instance_id:
                raise ValidationError("Local sources cannot use a live NetBox instance")
            if self.mode == "manual" and self.tenant_id is not None:
                raise ValidationError("Manual inventory cannot bind a NetBox tenant")
        else:
            if not self.instance_id:
                raise ValidationError("Select an operator-approved NetBox instance")
            if self.instance.organization_id and self.instance.organization_id != self.organization_id:
                raise ValidationError("Dedicated NetBox instance belongs to another organization")
            if not self.tenant_id and self.instance.organization_id != self.organization_id:
                raise ValidationError("Shared NetBox instances require an explicit tenant ID")

    @property
    def can_write(self):
        if self.mode in {"development", "manual"}:
            return self.instance_id is None and (self.mode != "manual" or self.tenant_id is None)
        return bool(
            self.mode in {"central", "external"}
            and self.instance_id
            and self.instance.enabled
            and self.instance.access_mode == "read_write"
            and (self.tenant_id is None or self.tenant_id > 0)
            and (not self.instance.organization_id or self.instance.organization_id == self.organization_id)
            and (self.tenant_id or self.instance.organization_id == self.organization_id)
        )


VIRTUALIZATION_TYPES = [
    ("", "Not specified"),
    ("lxc", "LXC"),
    ("incus", "Incus"),
    ("proxmox", "Proxmox"),
    ("vmware", "VMware"),
    ("kvm", "KVM"),
    ("hyperv", "Hyper-V"),
]


class Asset(models.Model):
    network_host = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_addresses",
        editable=False,
    )
    virtualization_type = models.CharField(
        max_length=20, choices=VIRTUALIZATION_TYPES, blank=True, default=""
    )
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
    responsible_contact = models.ForeignKey(
        Contact, on_delete=models.PROTECT, null=True, blank=True, related_name="owned_assets"
    )
    object_type = models.CharField(max_length=60, default="dcim.device")
    external_id = models.CharField(max_length=100, blank=True)
    state = models.CharField(
        max_length=12,
        default="pending",
        choices=[(x, x.title()) for x in ["pending", "synced", "failed", "recorded"]],
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
        if self.network_host_id:
            parent = self.network_host
            if (
                self.object_type != "ipam.ipaddress"
                or parent.object_type not in {"dcim.device", "virtualization.virtualmachine"}
                or parent.pk == self.pk
                or parent.organization_id != self.organization_id
                or parent.source_id != self.source_id
            ):
                raise ValidationError(
                    "Address assignment must reference a host in the same source and organization"
                )
        if self.virtualization_type and self.kind != "vm":
            raise ValidationError("Virtualization type is only supported for virtual machines")
        if self.source_id and self.organization_id != self.source.organization_id:
            raise ValidationError("Asset and source must belong to the same organization")
        if self.responsible_contact_id and self.responsible_contact.organization_id != self.organization_id:
            raise ValidationError("Responsible contact must belong to the asset organization")


class InventoryWrite(models.Model):
    agent_managed = models.BooleanField(default=False, editable=False)
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
        indexes = [
            models.Index(Upper("name"), name="product_name_upper_idx"),
            models.Index(Upper("identifier"), name="product_ident_upper_idx"),
            models.Index(
                fields=["id"],
                condition=~Q(identifier__startswith="pkg:deb/") & ~Q(identifier__startswith="pkg:rpm/"),
                name="product_upstream_candidates",
            ),
        ]


class ProductWatch(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="watch")
    vendor = models.CharField(max_length=120)
    product_key = models.CharField(max_length=120)
    source_url = models.URLField(max_length=250)
    enabled = models.BooleanField(default=True)
    interval_minutes = models.PositiveIntegerField(default=60)
    requested = models.BooleanField(default=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=250, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(interval_minutes__gte=15), name="watch_interval_min")
        ]

    def clean(self):
        from .product_matching import valid_key
        from .connectors.http import validate_base, ConnectorError

        for field in ("vendor", "product_key"):
            if not valid_key(getattr(self, field)):
                raise ValidationError({field: "Use the exact lowercase public vendor/product key"})
        try:
            self.source_url = validate_base(self.source_url).geturl().rstrip("/")
        except ConnectorError as exc:
            raise ValidationError({"source_url": str(exc)}) from None
        if self.interval_minutes < 15:
            raise ValidationError("The minimum refresh interval is 15 minutes")
        old = type(self).objects.filter(pk=self.pk).first()
        if old and old.source_url != self.source_url:
            raise ValidationError("An existing watch source cannot be repointed")

    @property
    def stale(self):
        from datetime import timedelta

        return bool(
            self.error
            or not self.last_success
            or timezone.now() - self.last_success > timedelta(minutes=self.interval_minutes * 2)
        )


class DiscoveryMatch(models.Model):
    watch = models.ForeignKey(ProductWatch, on_delete=models.PROTECT)
    finding = models.OneToOneField("Finding", on_delete=models.PROTECT, related_name="discovery")
    evidence_revision = models.ForeignKey("SourceRecordRevision", on_delete=models.PROTECT)
    input_hash = models.CharField(max_length=64)
    explanation = models.TextField()
    result = models.CharField(max_length=20)
    evaluated_at = models.DateTimeField(default=timezone.now)
    review_required = models.BooleanField(default=True)

    @property
    def inputs_changed(self):
        from .intelligence import digest

        installation = self.finding.installation
        return self.input_hash != digest(
            [
                digest(self.finding.record.payload),
                self.watch.vendor,
                self.watch.product_key,
                installation.product.identifier,
                installation.version,
                installation.build,
                installation.edition,
            ]
        )


class DiscoveryRevision(models.Model):
    match = models.ForeignKey(DiscoveryMatch, on_delete=models.PROTECT, related_name="history")
    fingerprint = models.CharField(max_length=64)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match", "fingerprint"], name="unique_discovery_revision")
        ]
        indexes = [
            models.Index(fields=["match", "created_at", "id"], name="discovery_first_idx"),
        ]


class BusinessRiskRevision(models.Model):
    issue = models.ForeignKey("AssetIssue", on_delete=models.PROTECT, related_name="business_risks")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    snapshot = models.JSONField()
    evidence_hash = models.CharField(max_length=64)
    previous = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["-pk"]


class OutreachPolicy(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="outreach_policy"
    )
    include_dpo = models.BooleanField(
        default=False, help_text="Include opted-in DPOs in new previews by default"
    )
    reminder_days = models.PositiveSmallIntegerField(default=0, help_text="0 disables timed reminder drafts")
    escalation_days = models.PositiveSmallIntegerField(
        default=0, help_text="0 disables management escalation drafts"
    )

    def clean(self):
        if self.escalation_days and self.reminder_days and self.escalation_days <= self.reminder_days:
            raise ValidationError("Escalation must follow the reminder")


class NotificationFollowup(models.Model):
    delivery = models.ForeignKey("NotificationDelivery", on_delete=models.PROTECT, related_name="followups")
    kind = models.CharField(max_length=12, choices=[("reminder", "Reminder"), ("escalation", "Escalation")])
    batch = models.OneToOneField(
        "NotificationBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="followup"
    )
    error = models.CharField(max_length=250, blank=True)
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["delivery", "kind"], name="unique_notification_followup")
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

    class Meta:
        indexes = [models.Index(fields=["product", "version", "asset"], name="installed_product_ver_idx")]

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

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"], name="finding_status_time_idx")]


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
    audience_report = models.JSONField(
        default=dict, help_text="Pinned campaign audience and explicit exclusions"
    )
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
    followup_checked_at = models.DateTimeField(null=True, blank=True)
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
        indexes = [
            models.Index(fields=["organization", "status", "event_date"]),
            models.Index(
                models.Case(
                    models.When(priority="critical", then=models.Value(0)),
                    models.When(priority="high", then=models.Value(1)),
                    models.When(priority="review", then=models.Value(2)),
                    default=models.Value(3),
                    output_field=models.IntegerField(),
                ),
                Coalesce("action_due", "event_date"),
                F("updated_at").desc(),
                F("id"),
                name="issue_attention_order_idx",
            ),
        ]


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


class DemoDataset(models.Model):
    """Retained ownership and removal tombstone; never inferred from labels or account names."""

    key = models.SlugField(max_length=80, unique=True)
    state = models.CharField(
        max_length=10, default="active", choices=[("active", "Active"), ("removed", "Removed")]
    )
    configuration = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    removed_at = models.DateTimeField(null=True, blank=True)


class DemoObject(models.Model):
    dataset = models.ForeignKey(DemoDataset, on_delete=models.CASCADE, related_name="entries")
    model_label = models.CharField(max_length=100)
    object_pk = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["model_label", "object_pk"], name="unique_demo_object_owner")
        ]


class InfrastructureRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    organization = models.OneToOneField(Organization, on_delete=models.PROTECT, null=True, blank=True)
    company_name = models.CharField(max_length=180)
    company_address = models.TextField(max_length=1000, blank=True)
    contact_name = models.CharField(max_length=180)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    email = models.EmailField(unique=True)
    notification_email = models.EmailField(blank=True)
    notification_contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="registration_notifications"
    )
    emergency_phone = models.CharField(max_length=80, blank=True)
    pgp_public_key = models.TextField(max_length=50000, blank=True)
    smime_certificate = models.TextField(max_length=30000, blank=True)
    authority_attested_at = models.DateTimeField(null=True, blank=True)
    periodic_review_consented_at = models.DateTimeField(null=True, blank=True)
    updates_committed_at = models.DateTimeField(null=True, blank=True)
    commitments_version = models.CharField(max_length=32, blank=True)
    scopes = models.JSONField(default=list)
    review_days = models.PositiveSmallIntegerField(default=90)
    email_reminders = models.BooleanField(default=True)
    consent_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=24,
        default="awaiting_email",
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["awaiting_email", "awaiting_review", "approved", "rejected"]
        ],
    )
    manually_activated_at = models.DateTimeField(null=True, blank=True)
    manually_activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="manually_activated_registrations",
    )
    manual_activation_note = models.TextField(max_length=2000, blank=True)
    verification_digest = models.CharField(max_length=64, unique=True)
    verification_expires = models.DateTimeField()
    verification_attempted_at = models.DateTimeField(null=True, blank=True)
    verification_error = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="infrastructure_registrations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(max_length=2000, blank=True)
    decision_mail_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class PublicRegistrationBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class InventoryReviewPolicy(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="inventory_review_policy"
    )
    interval_days = models.PositiveSmallIntegerField(default=90)
    reminder_days = models.PositiveSmallIntegerField(default=7)
    email_enabled = models.BooleanField(default=True)
    next_due = models.DateField(default=timezone.localdate, db_index=True)
    next_reminder_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(interval_days__gte=1, interval_days__lte=365),
                name="valid_inventory_review_interval",
            ),
            models.CheckConstraint(
                condition=Q(reminder_days__gte=1, reminder_days__lte=90),
                name="valid_inventory_reminder_interval",
            ),
        ]


class InventoryReviewConfirmation(models.Model):
    policy = models.ForeignKey(InventoryReviewPolicy, on_delete=models.PROTECT, related_name="confirmations")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(default=timezone.now)
    review_due_date = models.DateField(null=True, blank=True)
    data_digest = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64, unique=True)
    counts = models.JSONField(default=dict)
    next_due = models.DateField()


class InventoryReviewDelivery(models.Model):
    policy = models.ForeignKey(InventoryReviewPolicy, on_delete=models.PROTECT, related_name="deliveries")
    due_date = models.DateField()
    recipient = models.EmailField()
    fingerprint = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[(x, x.title()) for x in ["pending", "sent", "error", "suppressed"]],
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)
    transport = models.CharField(
        max_length=10,
        default="unknown",
        choices=[("unknown", "Legacy / unknown"), ("file", "Local file"), ("smtp", "SMTP relay")],
    )
    delivery_outcome = models.CharField(
        max_length=10,
        default="unknown",
        choices=[
            ("unknown", "Not known"),
            ("bounced", "Bounce reported"),
            ("delivered", "Delivery reported"),
        ],
    )
    feedback_at = models.DateTimeField(null=True, blank=True)
    feedback_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    feedback_note = models.CharField(max_length=1000, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_review_followups",
    )
    created_at = models.DateTimeField(default=timezone.now)


class OrganizationLocation(models.Model):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="map_location")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address_digest = models.CharField(max_length=64)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90), name="map_latitude_range"
            ),
            models.CheckConstraint(
                condition=Q(longitude__gte=-180, longitude__lte=180), name="map_longitude_range"
            ),
        ]


class OrganizationConfiguration(models.Model):
    """Owner-managed preferences; no AIL execution, mail proof or key identity claim."""

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="configuration")
    pgp_public_key = models.TextField(max_length=50000, blank=True)
    smime_certificate = models.TextField(max_length=30000, blank=True)
    ail_enabled = models.BooleanField(default=False)
    ail_keywords = models.JSONField(default=list)
    ail_honeytokens = models.JSONField(default=list)
    ail_notification_email = models.EmailField(blank=True)


class ConfigurationSection(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="configuration_sections"
    )
    section = models.CharField(max_length=20)
    revision = models.PositiveIntegerField(default=0)
    draft = models.JSONField(default=dict)
    reviewed = models.BooleanField(default=False)
    last_opened_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "section"], name="unique_configuration_section")
        ]


class MISPServer(models.Model):
    """Operator-approved destinations offered for optional customer-owned API credentials."""

    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250, default="https://misppriv.circl.lu", unique=True)
    enabled = models.BooleanField(default=False)
    allow_private = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def clean(self):
        from .connectors.http import validate_base, ConnectorError

        try:
            validate_base(self.base_url)
        except ConnectorError:
            raise ValidationError("Use an operator-approved credential-free HTTPS MISP URL") from None
        if self.pk:
            old = MISPServer.objects.get(pk=self.pk)
            if old.base_url != self.base_url:
                raise ValidationError(
                    "A saved MISP endpoint cannot be repointed; create a new approved server"
                )


class MISPInstance(models.Model):
    """An operator-approved read-only cache source; disabled until explicitly configured."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="personal_misp_sources",
    )
    misp_user_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Operator-verified MISP user ID owning this personal key; checked with users/view/me on every refresh",
    )
    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.PROTECT, related_name="personal_misp_sources"
    )
    server = models.ForeignKey(MISPServer, null=True, blank=True, on_delete=models.PROTECT)
    credential_kind = models.CharField(
        max_length=12,
        default="environment",
        choices=[("environment", "Operator secret reference"), ("encrypted", "Personal encrypted key")],
    )
    credential_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    credential_ciphertext = models.TextField(blank=True, editable=False)
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=250, default="https://misppriv.circl.lu")
    token_env_var = models.CharField(max_length=100, unique=True, default="MISP_CIRCL_TOKEN")
    enabled = models.BooleanField(default=False)
    allow_private = models.BooleanField(default=False)
    refresh_minutes = models.PositiveIntegerField(default=5)
    max_age_minutes = models.PositiveIntegerField(default=10)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=250, blank=True)
    generation = models.UUIDField(null=True, blank=True, editable=False)
    syncing_until = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return self.name

    def clean(self):
        import re
        from .connectors.http import ConnectorError, validate_base

        try:
            validate_base(self.base_url)
        except ConnectorError:
            raise ValidationError(
                "MISP requires an operator-approved credential-free HTTPS base URL"
            ) from None
        if not re.fullmatch(r"MISP_[A-Z0-9_]*TOKEN", self.token_env_var):
            raise ValidationError("Use a server-side MISP_*TOKEN credential reference")
        if not 5 <= self.refresh_minutes <= 60 or not self.refresh_minutes <= self.max_age_minutes <= 60:
            raise ValidationError("Refresh must be 5–60 minutes and maximum cache age refresh–60 minutes")
        if self.organization_id and (self.credential_kind != "encrypted" or not self.server_id):
            raise ValidationError(
                "Customer connections require the customer's own encrypted key and an approved endpoint; operator/CIRCL environment keys cannot be assigned to a company"
            )
        if self.enabled:
            from .misp import owner_eligible, endpoint_eligible

            if (
                not self.owner_id
                or not self.misp_user_id
                or not owner_eligible(self)
                or not endpoint_eligible(self)
            ):
                raise ValidationError(
                    "An enabled MISP source requires its current personal owner, company membership where applicable, approved endpoint and pinned native user ID"
                )
            if self.credential_kind == "encrypted" and (
                not self.organization_id or not self.credential_ciphertext
            ):
                raise ValidationError(
                    "Personal customer connections require an encrypted key and company context"
                )
        if self.pk:
            old = MISPInstance.objects.get(pk=self.pk)
            protected = (
                old.credential_kind == "encrypted" or MISPEvent.objects.filter(source_id=self.pk).exists()
            )
            if protected and (
                old.base_url != self.base_url
                or old.token_env_var != self.token_env_var
                or old.owner_id != self.owner_id
                or old.misp_user_id != self.misp_user_id
                or old.organization_id != self.organization_id
                or old.server_id != self.server_id
                or old.credential_nonce != self.credential_nonce
            ):
                raise ValidationError(
                    "A source with a personal key or cached events cannot be repointed; create a new source"
                )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "organization", "server"],
                condition=Q(enabled=True),
                name="personal_customer_misp_connection",
            )
        ]


class MISPEvent(models.Model):
    source = models.ForeignKey(MISPInstance, on_delete=models.PROTECT, related_name="events")
    event_uuid = models.UUIDField()
    remote_id = models.PositiveBigIntegerField()
    timestamp = models.PositiveBigIntegerField()
    info = models.CharField(max_length=1000)
    payload = models.JSONField(default=dict)
    digest = models.CharField(max_length=64)
    available = models.BooleanField(default=True)
    cached_at = models.DateTimeField(default=timezone.now)
    review_digest = models.CharField(max_length=64, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=1000, blank=True)
    readers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="permitted_misp_events",
        help_text="Explicit authorized CIRCL recipients for this exact event revision, including all nested restrictions. No participant access.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "event_uuid"], name="misp_source_event_uuid")
        ]
        indexes = [models.Index(fields=["source", "available", "-timestamp"])]

    def __str__(self):
        return str(self.event_uuid)


class InventoryCSVBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rows = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    baseline = models.CharField(max_length=64)
    status = models.CharField(max_length=12, default="preview")
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)


class CSVAssetBinding(models.Model):
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    asset = models.OneToOneField(Asset, on_delete=models.PROTECT, related_name="csv_binding")
    key = models.CharField(max_length=100)
    managed_digest = models.CharField(max_length=64)
    installations = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "key"], name="csv_source_key")]


class OrganizationInvitation(models.Model):
    domain_code = models.ForeignKey("OrganizationDomainCode", null=True, blank=True, on_delete=models.PROTECT)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Membership.ROLES)
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    mail_error = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class OrganizationDomainCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    domain = models.CharField(max_length=253)
    role = models.CharField(max_length=10, choices=[("reader", "Reader"), ("editor", "Inventory editor")])
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    max_acceptances = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"{self.organization} · @{self.domain} · {self.get_role_display()}"


class NationalState(models.Model):
    organization = models.OneToOneField(
        Organization, primary_key=True, on_delete=models.CASCADE, related_name="national_state"
    )
    dirty = models.BooleanField(default=True, db_index=True)
    projection_version = models.PositiveSmallIntegerField(null=True)
    refreshed_at = models.DateTimeField(null=True)
    operator_counts = models.JSONField(default=dict)
    shared_counts = models.JSONField(default=dict)
    inventory_assets = models.PositiveIntegerField(default=0)
    installations = models.PositiveIntegerField(default=0)
    unknown_versions = models.PositiveIntegerField(default=0)


class NationalVersion(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, db_constraint=False)
    product_name = models.CharField(max_length=180)
    identity = models.CharField(max_length=255)
    name = models.CharField(max_length=180)
    version = models.CharField(max_length=120)
    assets = models.PositiveIntegerField()
    total = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product_name", "identity", "version"], name="national_org_version"
            )
        ]


class NationalProblem(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, db_constraint=False)
    shared = models.BooleanField()
    external_id = models.CharField(max_length=120)
    reviews = models.PositiveIntegerField()
    assets = models.PositiveIntegerField()
    affected = models.PositiveIntegerField()
    accepted = models.PositiveIntegerField()
    severity_rank = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "shared", "external_id"], name="national_org_problem"
            )
        ]


class NationalActivity(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, db_constraint=False)
    shared = models.BooleanField()
    day = models.DateField(db_index=True)
    new = models.PositiveIntegerField(default=0)
    closed = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "shared", "day"], name="national_org_activity")
        ]


class NationalProductVersion(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, db_constraint=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, db_constraint=False)
    version = models.CharField(max_length=120)
    total = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "version"], name="national_product_version")
        ]


class AgentFleet(models.Model):
    """Expiring company-scoped rollout authorization; shared secret is never stored."""

    inventory_mode = models.CharField(
        max_length=12,
        default="observed",
        choices=[("observed", "Bearings only"), ("managed", "Managed NetBox")],
        editable=False,
    )
    virtualization_type = models.CharField(
        max_length=20, choices=VIRTUALIZATION_TYPES, blank=True, default=""
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, editable=False)
    source_fingerprint = models.CharField(max_length=64, editable=False)
    new_asset_kind = models.CharField(
        max_length=20,
        choices=[
            ("vm", "Virtual machine"),
            ("server", "Server"),
            ("desktop", "Desktop"),
            ("laptop", "Laptop"),
        ],
    )
    max_devices = models.PositiveIntegerField(default=1000)
    issued_devices = models.PositiveIntegerField(default=0, editable=False)
    enabled = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(max_devices__gte=1, max_devices__lte=100000), name="agent_fleet_device_limit"
            ),
            models.CheckConstraint(
                condition=Q(issued_devices__lte=F("max_devices")), name="agent_fleet_quota"
            ),
        ]


class AgentEnrollment(models.Model):
    """One-use, public-key-bound authorization, created by a company administrator."""

    virtualization_type = models.CharField(
        max_length=20, choices=VIRTUALIZATION_TYPES, blank=True, default=""
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    fleet = models.ForeignKey(AgentFleet, on_delete=models.PROTECT, null=True, blank=True)
    observed_only = models.BooleanField(default=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True)
    new_asset_kind = models.CharField(max_length=20, blank=True)
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    public_key = models.CharField(max_length=44, db_index=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    signed_body = models.BinaryField(default=bytes, blank=True)
    signature_input = models.TextField(blank=True)
    signature = models.TextField(blank=True)
    request_url = models.CharField(max_length=2048, blank=True)
    device_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)


class AgentFleetRegistration(models.Model):
    fleet = models.ForeignKey(AgentFleet, on_delete=models.PROTECT, related_name="registrations")
    public_key = models.CharField(max_length=44, unique=True)
    request_id = models.UUIDField()
    enrollment = models.OneToOneField(AgentEnrollment, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class AgentDevice(models.Model):
    netbox_export_pending = models.BooleanField(default=False)
    netbox_export_after = models.DateTimeField(default=timezone.now)
    netbox_export_receipt = models.JSONField(default=dict, blank=True, editable=False)
    netbox_export_error = models.CharField(max_length=180, blank=True)
    network_observed_at = models.DateTimeField(null=True, blank=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="agent_devices")
    source = models.ForeignKey(InventorySource, on_delete=models.PROTECT)
    public_key = models.CharField(max_length=44, unique=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_sequence = models.PositiveBigIntegerField(default=0)
    daily_bytes = models.PositiveBigIntegerField(default=0)
    daily_reports = models.PositiveIntegerField(default=0)
    applied_sequence = models.PositiveBigIntegerField(default=0)
    distro_requested = models.BooleanField(default=True)
    distro_checked_at = models.DateTimeField(null=True, blank=True)
    distro_summary = models.JSONField(default=dict, blank=True)
    auto_software = models.BooleanField(default=True)
    software_sync_pending = models.BooleanField(default=True)
    last_received_at = models.DateTimeField(null=True, blank=True)
    last_observed_at = models.DateTimeField(null=True, blank=True)
    last_complete_at = models.DateTimeField(null=True, blank=True)
    reported_network = models.JSONField(default=dict, blank=True)
    os = models.JSONField(default=dict, blank=True)
    services = models.JSONField(default=list, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["netbox_export_after"],
                condition=Q(netbox_export_pending=True),
                name="agent_netbox_export_due_idx",
            ),
            models.Index(
                fields=["id"],
                condition=Q(enabled=True, distro_requested=True),
                name="agent_distro_pending_idx",
            ),
            models.Index(
                fields=["id"],
                condition=Q(enabled=True, auto_software=True, software_sync_pending=True),
                name="agent_software_pending_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["asset"], condition=Q(enabled=True), name="one_active_agent_per_asset"
            )
        ]

    @property
    def stale(self):
        from datetime import timedelta

        return not self.last_observed_at or self.last_observed_at < timezone.now() - timedelta(hours=12)

    @property
    def runtime_services(self):
        from datetime import timedelta
        from django.utils.dateparse import parse_datetime

        result = []
        for item in self.services:
            observed = parse_datetime(item.get("observed_at", ""))
            result.append({**item, "stale": not observed or observed < timezone.now() - timedelta(hours=12)})
        return result

    def __str__(self):
        return f"{self.asset.name} · {self.id}"


class AgentReport(models.Model):
    """Exact signed input, retained independently of its current inventory projection."""

    id = models.UUIDField(primary_key=True, editable=False)
    device = models.ForeignKey(AgentDevice, on_delete=models.PROTECT, related_name="reports")
    sequence = models.PositiveBigIntegerField()
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    body = models.BinaryField()
    body_hash = models.CharField(max_length=64)
    signature_input = models.TextField()
    signature = models.TextField()
    request_url = models.CharField(max_length=2048)
    content_type = models.CharField(max_length=100)
    public_key = models.CharField(max_length=44)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[(s, s) for s in ["pending", "applied", "rejected", "superseded"]],
    )
    error = models.CharField(max_length=120, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    component_count = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "sequence"], name="agent_device_sequence")]
        indexes = [models.Index(fields=["status", "received_at"], name="agent_pending_reports_idx")]


class AgentComponent(models.Model):
    distro_check = models.JSONField(default=dict, blank=True, editable=False)
    package_source = models.JSONField(default=dict, blank=True)
    package_identity = models.JSONField(default=dict, blank=True)
    automatic_installation = models.BooleanField(default=False)
    inventory_excluded = models.BooleanField(default=False)
    binary = models.JSONField(default=dict, blank=True)
    device = models.ForeignKey(AgentDevice, on_delete=models.PROTECT, related_name="components")
    key = models.CharField(max_length=255)
    name = models.CharField(max_length=128)
    manager = models.CharField(max_length=8)
    architecture = models.CharField(max_length=64)
    version = models.CharField(max_length=120)
    observed_at = models.DateTimeField()
    missing_since = models.DateTimeField(null=True, blank=True)
    last_report = models.ForeignKey(AgentReport, on_delete=models.PROTECT)
    installation = models.OneToOneField(
        Installation, on_delete=models.PROTECT, null=True, blank=True, related_name="agent_component"
    )

    @property
    def stale(self):
        from datetime import timedelta

        return self.observed_at < timezone.now() - timedelta(hours=12)

    class Meta:
        indexes = [
            models.Index(
                fields=["device", "id"],
                condition=Q(installation__isnull=True, inventory_excluded=False),
                name="agent_unbound_inventory_idx",
            )
        ]
        constraints = [models.UniqueConstraint(fields=["device", "key"], name="agent_component_identity")]


class DistroFeed(models.Model):
    key = models.CharField(max_length=40, unique=True)
    enabled = models.BooleanField(default=True)
    generation = models.UUIDField(null=True, editable=False)
    content_hash = models.CharField(max_length=64, blank=True, editable=False)
    last_attempt = models.DateTimeField(null=True, editable=False)
    last_success = models.DateTimeField(null=True, editable=False)
    error = models.CharField(max_length=200, blank=True, editable=False)
    summary = models.JSONField(default=dict, blank=True, editable=False)
    lease_id = models.UUIDField(null=True, editable=False)
    lease_until = models.DateTimeField(null=True, editable=False)


class DistroAdvisory(models.Model):
    feed = models.ForeignKey(DistroFeed, on_delete=models.PROTECT)
    identity = models.CharField(max_length=200)
    generation = models.UUIDField()
    metadata = models.JSONField()
    criteria = models.JSONField()
    content_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "identity"], name="distro_definition_identity")
        ]


class DistroAdvisoryPackage(models.Model):
    feed = models.ForeignKey(DistroFeed, on_delete=models.CASCADE)
    advisory = models.ForeignKey(DistroAdvisory, on_delete=models.CASCADE)
    manager = models.CharField(max_length=8)
    name = models.CharField(max_length=128)

    class Meta:
        indexes = [models.Index(fields=["feed", "manager", "name"], name="distro_package_lookup_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["advisory", "manager", "name"], name="distro_package_rule_identity"
            )
        ]


class DistroMatch(models.Model):
    finding = models.OneToOneField(Finding, on_delete=models.PROTECT, related_name="distro_match")
    component = models.ForeignKey(AgentComponent, on_delete=models.PROTECT)
    advisory = models.ForeignKey(DistroAdvisory, on_delete=models.PROTECT)
    result = models.CharField(
        max_length=20, choices=[(v, v) for v in ["potential", "unknown", "not_affected", "not_observed"]]
    )
    evidence_revision = models.ForeignKey(SourceRecordRevision, on_delete=models.PROTECT)
    input_hash = models.CharField(max_length=64)
    snapshot = models.JSONField(default=dict)
    evaluated_at = models.DateTimeField(default=timezone.now)
    review_required = models.BooleanField(default=True)

    @property
    def inputs_changed(self):
        return (
            self.snapshot.get("version") != self.component.version
            or self.snapshot.get("source_package", {}) != self.component.package_source
            or self.component.installation_id != self.finding.installation_id
            or self.component.stale
            or self.component.missing_since is not None
            or not self.component.device.enabled
            or self.component.device.expires_at <= timezone.now()
        )


class DistroMatchRevision(models.Model):
    match = models.ForeignKey(DistroMatch, on_delete=models.PROTECT, related_name="history")
    fingerprint = models.CharField(max_length=64)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match", "fingerprint"], name="distro_match_revision_unique")
        ]
