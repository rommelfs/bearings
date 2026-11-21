"""Write-only personal API credentials, encrypted at rest and bound to their connection identity."""

import base64
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from django.utils.crypto import salted_hmac
from .connectors.http import ConnectorError


def encryption_ready():
    return (
        len(settings.SECRET_KEY) >= 32 and settings.SECRET_KEY != "development-only-unsafe-key-do-not-deploy"
    )


@sensitive_variables()
def cipher(source, secret):
    context = f"{source.owner_id}:{source.organization_id}:{source.credential_nonce}"
    key = salted_hmac("bearings.misp.customer-key/v1", context, secret=secret, algorithm="sha256").digest()
    return Fernet(base64.urlsafe_b64encode(key))


@sensitive_variables()
def encrypt(source, value):
    if not encryption_ready():
        raise ConnectorError("Private credential encryption is not configured")
    return cipher(source, settings.SECRET_KEY).encrypt(value.encode()).decode()


@sensitive_variables()
def decrypt(source):
    if not source.credential_ciphertext:
        raise ConnectorError("Personal MISP credential is unavailable; no service-key fallback")
    for secret in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]:
        try:
            return cipher(source, secret).decrypt(source.credential_ciphertext.encode()).decode()
        except (InvalidToken, ValueError, UnicodeError):
            continue
    raise ConnectorError(
        "Personal MISP credential cannot be decrypted; reconnect without a service-key fallback"
    )
