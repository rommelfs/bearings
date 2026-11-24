"""Actual NetBox permission/token checks in an outer rollback; no production endpoints."""

import uuid
from django.db import transaction
from django.contrib.auth import get_user_model
from users.models import Token, ObjectPermission
from virtualization.models import VirtualMachine
from tenancy.models import Tenant

namespace = {"__name__": "native_inventory_checks"}
source = globals().get("NATIVE_INVENTORY_SOURCE")
if not isinstance(source, str):
    raise RuntimeError("Use the guarded lab or disposable native driver")
exec(source, namespace)
provision = namespace["provision"]
with transaction.atomic():
    marker = uuid.uuid4().hex
    actor = get_user_model().objects.create_user(username="native-check-" + marker, is_superuser=True)
    data = {"key": str(uuid.uuid4()), "actor": actor.username}
    saved = provision(data)
    user = get_user_model().objects.get(pk=saved["user"])
    assert not user.is_superuser and not user.has_usable_password()
    assert not Token.objects.get(pk=saved["token_id"]).write_enabled
    other = Tenant.objects.create(name="Other", slug="other-" + marker)
    permission = ObjectPermission.objects.filter(users=user, object_types__model="device").get()
    assert permission.actions == ["view"] and permission.constraints == {"tenant_id": saved["tenant"]}
    # Real NetBox permission backend: own-tenant query only; no other tenant or add/change.
    own = VirtualMachine.objects.create(name="native-own-" + marker, tenant_id=saved["tenant"])
    foreign = VirtualMachine.objects.create(name="native-foreign-" + marker, tenant_id=other.pk)
    assert user.has_perm("virtualization.view_virtualmachine", own)
    assert not user.has_perm("virtualization.view_virtualmachine", foreign)
    assert not user.has_perm("virtualization.add_virtualmachine", own)
    assert not user.has_perm("virtualization.change_virtualmachine", own)
    assert provision({**data, "saved": saved}) == saved
    token = Token.objects.get(pk=saved["token_id"])
    token.enabled = False
    token.save()
    try:
        provision({**data, "saved": saved})
        raise AssertionError("Revoked token restored")
    except ValueError:
        pass
    assert not Token.objects.get(pk=token.pk).enabled
    transaction.set_rollback(True)
print("Native tenant permission isolation, GET-only token, repeat and revocation checks passed")
