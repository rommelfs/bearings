"""Company-only setup surfaces. Every save rechecks authorization and optional approval."""

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from .access import require, can_review_contact, organization
from .circl_views import private_response
from .models import ConfigurationSection
from .configuration import (
    FORMS,
    SECTIONS,
    wizard_available,
    initial_data,
    digest,
    progress,
    apply_section,
    locked_owner,
    completion_error,
)


def owner(request, slug):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    return org


@login_required
@never_cache
@require_http_methods(["GET"])
def center(request, slug):
    org = owner(request, slug)
    return private_response(
        render(
            request,
            "portal/configuration_center.html",
            {
                "org": org,
                "setup": progress(org),
                "available": wizard_available(org),
                "member_admin": org.membership_set.filter(user=request.user, role="admin").exists(),
            },
        )
    )


@login_required
@never_cache
@require_http_methods(["GET"])
def resume(request, slug):
    org = owner(request, slug)
    if not wizard_available(org):
        return redirect("configuration", slug=slug)
    state = org.configuration_sections.order_by("-last_opened_at", "-pk").first()
    return redirect(
        "setup-section", slug=slug, section=state.section if state and state.section in FORMS else "scope"
    )


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def section(request, slug, section, guided=False):
    if section not in FORMS:
        raise Http404()
    org = owner(request, slug)
    if guided:
        require(wizard_available(org))
    state = ConfigurationSection.objects.filter(organization=org, section=section).first()
    initial = initial_data(org, section)
    # Invalid drafts are resumable except rejected key material, which is never persisted.
    if state and state.draft.get("_invalid"):
        initial.update({k: v for k, v in state.draft.items() if k in FORMS[section].base_fields})
    form = FORMS[section](
        request.POST if request.method == "POST" else None,
        initial=initial,
        **({"organization": org} if section == "inventory" else {}),
    )
    status = 200
    if request.method == "POST":
        json_request = request.headers.get("Accept") == "application/json"
        with transaction.atomic():
            org = locked_owner(request.user, org)
            if guided:
                require(wizard_available(org))
            state, _ = ConfigurationSection.objects.get_or_create(organization=org, section=section)
            state = ConfigurationSection.objects.select_for_update().get(pk=state.pk)
            if str(state.revision) != request.POST.get("revision") or digest(
                org, section
            ) != request.POST.get("baseline"):
                message = "This section changed elsewhere. Your unsaved text is still on this page; reload and reconcile before saving."
                if json_request:
                    return private_response(JsonResponse({"conflict": True, "message": message}, status=409))
                form.add_error(None, message)
                status = 409
            else:
                valid = form.is_valid()
                if valid and section == "inventory":
                    if state.draft.get("_asset_pk") and not form.cleaned_data.get("asset_name"):
                        form.add_error(
                            None,
                            "Use Add another asset to start a new entry; existing inventory is preserved.",
                        )
                        valid = False
                    if state.draft.get("_installation_pk") and not form.cleaned_data.get("software_name"):
                        form.add_error(
                            None,
                            "Use the individual software editor to change existing software; it cannot be removed by clearing this field.",
                        )
                        valid = False
                if valid:
                    try:
                        # Savepoint protects against a later validation failure during scope replacement.
                        with transaction.atomic():
                            apply_section(request.user, org, section, form.cleaned_data, state)
                    except ValidationError as error:
                        form.add_error(None, error)
                        valid = False
                draft, unsaved_fields = {}, []
                for key, field in form.fields.items():
                    if key in {"pgp_public_key", "smime_certificate"}:
                        if key in form.errors:
                            unsaved_fields.append(key)
                        continue
                    value = form.data.get(key, "")
                    if len(value) > (getattr(field, "max_length", None) or 100):
                        unsaved_fields.append(key)
                    else:
                        draft[key] = value
                if not valid:
                    draft["_invalid"] = True
                for key in ("_asset_pk", "_installation_pk"):
                    if key in state.draft:
                        draft[key] = state.draft[key]
                state.draft = draft
                if valid and request.POST.get("action") == "another":
                    state.draft = {"notes": draft.get("notes", "")}
                state.revision += 1
                state.last_opened_at = timezone.now()
                state.reviewed = False
                if valid and request.POST.get("action") == "complete":
                    error = completion_error(org, section, form.cleaned_data)
                    if error:
                        form.add_error(None, error)
                    else:
                        state.reviewed = True
                state.save()
                setup = progress(org)
                payload = {
                    "valid": valid and not form.errors,
                    "revision": state.revision,
                    "baseline": digest(org, section),
                    "progress": setup,
                    "errors": form.errors.get_json_data(),
                    "restart_inventory": valid and request.POST.get("action") == "another",
                    "unsaved_fields": unsaved_fields,
                    "message": "Saved"
                    if valid and not form.errors
                    else "Correct the highlighted fields. Non-key draft text is saved; invalid public/private key material is not stored.",
                }
                if json_request:
                    return private_response(JsonResponse(payload))
                if not form.errors:
                    messages.success(request, "Configuration saved.")
                    if guided and state.reviewed:
                        keys = list(FORMS)
                        next_key = keys[(keys.index(section) + 1) % len(keys)]
                        if setup["done"] == setup["total"]:
                            return redirect("configuration", slug=slug)
                        return redirect("setup-section", slug=slug, section=next_key)
                    return redirect(request.path)
    index = list(FORMS).index(section)
    next_key = list(FORMS)[index + 1] if index + 1 < len(FORMS) else None
    from .models import Asset

    assets = (
        Asset.objects.filter(organization=org, source__organization=org)
        .select_related("source")
        .order_by("name", "pk")
    )
    return private_response(
        render(
            request,
            "portal/configuration_section.html",
            {
                "org": org,
                "form": form,
                "section": section,
                "guided": guided,
                "title": SECTIONS[index][1],
                "setup": progress(org),
                "revision": state.revision if state else 0,
                "draft_invalid": bool(state and state.draft.get("_invalid")),
                "baseline": digest(org, section),
                "next_url": reverse("setup-section", args=[slug, next_key])
                if next_key and guided
                else reverse("configuration", args=[slug]),
                "assets": assets[:25] if section == "inventory" else [],
                "asset_count": assets.count() if section == "inventory" else 0,
            },
            status=status,
        )
    )


@login_required
@never_cache
@require_http_methods(["POST"])
def export_ail(request, slug):
    from django.http import HttpResponse
    from .configuration import ail_yara
    from .access import audit

    org = owner(request, slug)
    try:
        content = ail_yara(org)
    except ValidationError:
        messages.warning(request, "Save your indicators and select manual AIL preparation before exporting.")
        return redirect("configuration-section", slug=slug, section="ail")
    audit(request.user, org, "configuration.ail_exported")
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="bearings-ail.yar"'
    response["X-Content-Type-Options"] = "nosniff"
    return private_response(response)
