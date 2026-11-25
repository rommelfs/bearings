from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from .access import audit, can_review_contact, require, organization
from .models import OutreachPolicy
from .outreach import PolicyForm


@login_required
def policy(request, slug):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    current = OutreachPolicy.objects.filter(organization=org).first() or OutreachPolicy(organization=org)
    form = PolicyForm(request.POST or None, instance=current)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            from .models import Organization

            Organization.objects.select_for_update().get(pk=org.pk)
            row, _ = OutreachPolicy.objects.get_or_create(organization=org)
            for name in form.Meta.fields:
                setattr(row, name, form.cleaned_data[name])
            row.full_clean()
            row.save()
            audit(request.user, org, "notification.policy_updated", row.pk, **form.cleaned_data)
        messages.success(
            request,
            "Contact policy saved. Timed follow-ups prepare drafts for approval; they do not automatically send messages.",
        )
        return redirect("organization", slug=slug)
    return render(
        request, "portal/form.html", {"org": org, "form": form, "title": "DPO, reminder & escalation policy"}
    )
