from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from portal.access import audit
from portal.models import Contact, Organization


class Command(BaseCommand):
    help = "Prepare overdue-review reminders for organization administrators in the local mail sink only"

    def handle(self, *args, **options):
        count = 0
        for org in Organization.objects.all():
            with transaction.atomic():
                # Lock organization to serialize reminder deduplication on PostgreSQL.
                org = Organization.objects.select_for_update().get(pk=org.pk)
                contacts = [c for c in Contact.objects.filter(organization=org) if c.overdue]
                for c in contacts:
                    key = f"{c.pk}:{c.next_review}"
                    if org.auditevent_set.filter(action="contact.reminder_prepared", target=key).exists():
                        continue
                    recipients = list(
                        org.membership_set.filter(role="admin")
                        .exclude(user__email="")
                        .values_list("user__email", flat=True)
                    )
                    if not recipients:
                        continue
                    send_mail(
                        "Bearings development: contact review overdue",
                        "An emergency contact needs substantive review. Sign in to your organization portal.",
                        settings.DEFAULT_FROM_EMAIL,
                        recipients,
                    )
                    audit(None, org, "contact.reminder_prepared", key)
                    count += 1
        self.stdout.write(f"Prepared {count} reminders in local development mail sink.")
