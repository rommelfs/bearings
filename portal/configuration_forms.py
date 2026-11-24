"""Bounded owner configuration; public communication material never grants identity or authority."""

import base64
import binascii
import re
from django import forms
from .scope import normalize


class PublicKeysForm(forms.Form):
    pgp_public_key = forms.CharField(
        required=False,
        max_length=50000,
        label="PGP public key (optional)",
        widget=forms.Textarea(attrs={"rows": 5, "spellcheck": "false"}),
        help_text="Paste an armored PUBLIC key, never a private key. Identity and encryption capability are not verified.",
    )
    smime_certificate = forms.CharField(
        required=False,
        max_length=30000,
        label="S/MIME public certificate (optional)",
        widget=forms.Textarea(attrs={"rows": 5, "spellcheck": "false"}),
        help_text="Paste a PEM X.509 certificate. No private key or PKCS#12 file. Saving it does not enable encrypted mail.",
    )

    def clean_pgp_public_key(self):
        value = self.cleaned_data["pgp_public_key"].strip()
        if not value:
            return ""
        lines = value.splitlines()
        if (
            lines[0] != "-----BEGIN PGP PUBLIC KEY BLOCK-----"
            or lines[-1] != "-----END PGP PUBLIC KEY BLOCK-----"
        ):
            raise forms.ValidationError("Use an armored PGP PUBLIC KEY BLOCK only.")
        body = []
        for line in lines[1:-1]:
            if not line.strip() or line.startswith(("Version:", "Comment:", "=")):
                continue
            body.append(line.strip())
        try:
            raw = base64.b64decode("".join(body), validate=True)
            offset, public = 0, False
            while offset < len(raw):
                header = raw[offset]
                offset += 1
                if not header & 128:
                    raise ValueError()
                if header & 64:
                    tag = header & 63
                    length = raw[offset]
                    offset += 1
                    if length < 192:
                        pass
                    elif length < 224:
                        length = ((length - 192) << 8) + raw[offset] + 192
                        offset += 1
                    elif length == 255:
                        length = int.from_bytes(raw[offset : offset + 4], "big")
                        offset += 4
                    else:
                        raise ValueError()  # No partial body lengths in submitted certificates.
                else:
                    tag = (header >> 2) & 15
                    size = [1, 2, 4, 0][header & 3]
                    if not size:
                        raise ValueError()
                    length = int.from_bytes(raw[offset : offset + size], "big")
                    offset += size
                if tag not in {2, 6, 10, 12, 13, 14, 17} or length < 1 or offset + length > len(raw):
                    raise ValueError()
                if tag == 6:
                    public = True
                    if length < 8 or raw[offset] not in {4, 5, 6}:
                        raise ValueError()
                offset += length
            if not public:
                raise ValueError()
        except (ValueError, IndexError, binascii.Error):
            raise forms.ValidationError(
                "Enter a public PGP certificate; secret-key or malformed packets are refused."
            ) from None
        return value

    def clean_smime_certificate(self):
        from cryptography import x509

        value = self.cleaned_data["smime_certificate"].strip()
        if not value:
            return ""
        if not re.fullmatch(r"-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----", value):
            raise forms.ValidationError("Use a single PEM public CERTIFICATE only.")
        try:
            x509.load_pem_x509_certificate(value.encode("ascii"))
        except (ValueError, UnicodeError):
            raise forms.ValidationError("Enter a parseable PEM X.509 public certificate.") from None
        return value


class ScopeConfigurationForm(forms.Form):
    networks = forms.CharField(
        required=False,
        max_length=6000,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One strict CIDR prefix or start-end IP range per line.",
    )
    ips = forms.CharField(
        required=False, max_length=6000, label="Static IP addresses", widget=forms.Textarea(attrs={"rows": 3})
    )
    domains = forms.CharField(
        required=False,
        max_length=6000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One DNS name per line, without URL or wildcard.",
    )
    network_context = forms.CharField(
        required=False,
        max_length=100,
        help_text="For private networks, identify the internal network context.",
    )

    def clean(self):
        data = super().clean()
        scopes = []
        for field in ("networks", "ips", "domains"):
            for line in data.get(field, "").splitlines():
                if not line.strip():
                    continue
                kind = (
                    "domain"
                    if field == "domains"
                    else "ip"
                    if field == "ips"
                    else "network"
                    if "/" in line
                    else "range"
                )
                try:
                    value = normalize(kind, line)
                except forms.ValidationError as error:
                    self.add_error(field, error)
                    continue
                item = {"kind": kind, "value": value, "network_context": data.get("network_context", "")}
                if item not in scopes:
                    scopes.append(item)
        if len(scopes) > 100:
            self.add_error(None, "Use at most 100 declarations in this editor.")
        data["scopes"] = scopes
        return data


class InventoryConfigurationForm(forms.Form):
    asset_name = forms.CharField(required=False, max_length=180, label="Asset name")
    asset_kind = forms.ChoiceField(
        required=False,
        choices=[
            ("server", "Server"),
            ("vm", "Virtual machine"),
            ("desktop", "Desktop"),
            ("laptop", "Laptop"),
            ("appliance", "Appliance"),
        ],
        initial="server",
    )
    software_name = forms.CharField(required=False, max_length=180, label="Software / operating system")
    version = forms.CharField(
        required=False,
        max_length=120,
        help_text="Leave blank if unknown; a blank version remains a visible gap.",
    )
    is_operating_system = forms.BooleanField(required=False, label="This is the operating system")

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.manual = bool(
            organization
            and hasattr(organization, "inventory_source")
            and organization.inventory_source.mode == "manual"
        )
        if not self.manual:
            for key in ("asset_name", "asset_kind", "software_name", "version", "is_operating_system"):
                self.fields.pop(key)

    def clean(self):
        data = super().clean()
        if self.manual:
            if (data.get("software_name") or data.get("version")) and not data.get("asset_name"):
                self.add_error("asset_name", "Name the asset before adding software.")
            if data.get("version") and not data.get("software_name"):
                self.add_error("software_name", "Name the software for this version.")
        return data

    notes = forms.CharField(
        required=False,
        max_length=2000,
        label="Inventory notes / remaining work",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="For example, teams or systems still to be added. Add actual assets and versions using the inventory links below.",
    )


class MonitoringConfigurationForm(forms.Form):
    enabled = forms.BooleanField(required=False, label="Prepare indicators for manual AIL import")
    keywords = forms.CharField(
        required=False,
        max_length=6000,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One company name, brand, domain or other search term per line; at most 100 terms.",
    )
    honeytokens = forms.CharField(
        required=False,
        max_length=6000,
        label="Dedicated Honeytoken indicators",
        widget=forms.Textarea(attrs={"rows": 3, "spellcheck": "false"}),
        help_text="One deliberately planted indicator per line. Keep these separate from keywords. Never enter working passwords or private keys.",
    )
    notification_email = forms.EmailField(
        required=False,
        label="AIL notification team email (optional)",
        help_text="If a different team handles leaks. Stored as an unverified routing preference; no mail is sent yet.",
    )

    def clean(self):
        data = super().clean()
        for key in ("keywords", "honeytokens"):
            values = list(
                dict.fromkeys(line.strip() for line in data.get(key, "").splitlines() if line.strip())
            )
            if len(values) > 100 or any(len(value) > 255 for value in values):
                self.add_error(key, "Use at most 100 indicators, each at most 255 characters.")
            data[key + "_list"] = values
        if data.get("enabled") and not (data["keywords_list"] or data["honeytokens_list"]):
            self.add_error(None, "Add a keyword or Honeytoken, or leave monitoring unselected.")
        return data


class ContactConfigurationForm(PublicKeysForm):
    postal_address = forms.CharField(
        required=False, max_length=1000, label="Company address", widget=forms.Textarea(attrs={"rows": 3})
    )
