import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from social_django.models import UserSocialAuth
from config.oidc import identity_uid
from portal.access import audit


class Command(BaseCommand):
    help = "Explicitly link/revoke a verified issuer+subject to an existing account; no role changes"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Existing active platform administrator")
        parser.add_argument("--username", required=True)
        parser.add_argument(
            "--subject", required=True, help="Verified immutable IdP subject, never email/name"
        )
        parser.add_argument("--revoke", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not actor or not user or not settings.SSO_ENABLED:
            raise CommandError(
                "Configured SSO, an existing account and an active platform administrator are required"
            )
        try:
            uid = identity_uid(settings.SSO_ISSUER, options["subject"])
        except ValueError:
            raise CommandError("Use a nonempty immutable IdP subject of at most 255 characters") from None
        existing = UserSocialAuth.objects.select_for_update().filter(provider="oidc", uid=uid).first()
        if existing and existing.user_id != user.pk:
            raise CommandError("Identity belongs to another account; no reassignment performed")
        if options["revoke"]:
            if existing:
                existing.extra_data.update(enabled=False, generation=str(uuid.uuid4()), last_verified=0)
                existing.save(update_fields=["extra_data"])
        elif existing:
            existing.extra_data.update(enabled=True, generation=str(uuid.uuid4()), last_verified=0)
            existing.save(update_fields=["extra_data"])
        else:
            UserSocialAuth.objects.create(
                provider="oidc",
                uid=uid,
                user=user,
                extra_data={
                    "issuer": settings.SSO_ISSUER,
                    "subject": options["subject"],
                    "enabled": True,
                    "generation": str(uuid.uuid4()),
                },
            )
        audit(
            actor,
            None,
            "sso.identity_revoked" if options["revoke"] else "sso.identity_linked",
            user.pk,
            identity=uid,
            issuer=settings.SSO_ISSUER,
        )
        self.stdout.write("OIDC binding updated; account password, memberships and privileges unchanged.")
