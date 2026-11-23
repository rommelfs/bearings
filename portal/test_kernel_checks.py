"""Kernel source scope, exact ABI expressions, complete accounting and retained evidence."""

from pathlib import Path
import tempfile
from django.test import SimpleTestCase
from django.urls import reverse
from .tests import Fixture
from . import distro_oval, distro_kernel, agents, distro_cves
from .models import Finding, DistroKernelRevision

XML = r"""<oval_definitions xmlns="http://oval.mitre.org/XMLSchema/oval-definitions-5" xmlns:i="http://oval.mitre.org/XMLSchema/oval-definitions-5#independent" xmlns:u="http://oval.mitre.org/XMLSchema/oval-definitions-5#unix">
<definitions><definition id="synthetic:kernel:1" class="vulnerability"><metadata><title>Synthetic kernel test only</title><reference source="CVE" ref_id="CVE-2099-10001"/><description>Synthetic structural Canonical expression; not operational intelligence</description></metadata><criteria operator="AND"><criterion test_ref="flavor"/><criterion test_ref="version"/></criteria></definition></definitions>
<tests><u:uname_test id="flavor" check="all"><u:object object_ref="uname"/><u:state state_ref="flavorstate"/></u:uname_test><i:variable_test id="version" check="all" check_existence="all_exist"><i:object object_ref="varobj"/><i:state state_ref="versionstate"/></i:variable_test></tests>
<objects><u:uname_object id="uname"/><i:variable_object id="varobj"><i:var_ref>abivar</i:var_ref></i:variable_object></objects>
<states><u:uname_state id="flavorstate"><u:os_release operation="pattern match">6\.8\.0\-\d+(\-generic|\-generic\-64k)</u:os_release></u:uname_state><i:variable_state id="versionstate"><i:value datatype="debian_evr_string" operation="less than">0:6.8.0-35</i:value></i:variable_state></states>
<variables><local_variable id="abivar" datatype="debian_evr_string"><concat><literal_component>0:</literal_component><regex_capture pattern="^([\d|\.]+-\d+)[-|\w]+$"><object_component object_ref="uname" item_field="os_release"/></regex_capture></concat></local_variable></variables>
</oval_definitions>"""


def compiled(xml=XML):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "kernel.xml"
        path.write_text(xml)
        return list(distro_oval.compile_feed(path, "ubuntu", "24.04"))


class KernelExpressionTests(SimpleTestCase):
    def test_vendor_expression_and_version_boundary_flavor_and_unknown_inputs(self):
        row = compiled()[0]
        self.assertEqual(row["packages"], [("kernel", "runtime")])
        for kernel, scope, expected in [
            ("6.8.0-34-generic", "host", True),
            ("6.8.0-35-generic", "host", False),
            ("6.8.0-34-aws", "host", False),
            ("6.8.0-34-generic", "shared", None),
            ("6.8.0-34-generic", "unknown", None),
            ("custom", "host", None),
        ]:
            with self.subTest(kernel=kernel, scope=scope):
                value = distro_oval.evaluate_matches(
                    row["criteria"], {}, True, {"kernel": kernel, "kernel_scope": scope}
                )
                self.assertIs(value[1].get("__runtime_kernel__"), expected)
        self.assertIsNone(
            distro_kernel.release_condition(
                "6.8.0-34-generic", {"operation": "pattern match", "text": "(a+)+$"}
            )
        )
        self.assertEqual(distro_kernel.abi("6.8.0-35-generic"), "0:6.8.0-35")

    def test_unknown_expression_is_not_executed_and_presence_is_not_version_proof(self):
        bad = compiled(XML.replace("0:</literal_component>", "9:</literal_component>"))[0]
        self.assertIsNone(
            distro_oval.evaluate(
                bad["criteria"], {}, True, {"kernel": "6.8.0-34-generic", "kernel_scope": "host"}
            )[0]
        )
        presence = compiled(XML.replace('<i:state state_ref="versionstate"/>', ""))[0]
        truth, matches = distro_oval.evaluate_matches(
            presence["criteria"], {}, True, {"kernel": "6.8.0-34-generic", "kernel_scope": "host"}
        )
        self.assertTrue(truth)
        self.assertIsNone(matches["__runtime_kernel__"])


class KernelDeviceTests(Fixture):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    setUp = _Distro.setUp
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    load = _Distro.load
    relax = _Distro.relax

    def prepare(self, scope="host", kernel="6.8.0-34-generic", packages=True):
        self.enroll()
        data = self.data()
        data["os"].update(kernel_scope=scope, kernel=kernel)
        self.send(data)
        agents.process_pending()
        if not packages:
            component = self.device.components.get()
            installation = component.installation
            component.installation = None
            component.save(update_fields=["installation"])
            installation.delete()
        self.load(XML)
        return distro_cves.evaluate_device(self.device.pk)

    def test_own_kernel_retains_positive_evidence_and_reader_scoped_full_route(self):
        summary = self.prepare()
        self.assertEqual(summary["kernel"]["counts"], {"matched": 1, "not_matched": 0, "unresolved": 0})
        self.assertFalse(Finding.objects.exists())  # Never attach a kernel rule to nginx.
        revision = DistroKernelRevision.objects.get()
        self.assertEqual(len(revision.snapshot["matches"]), 1)
        self.assertEqual(revision.snapshot["matches"][0]["comparisons"][0]["vendor_version"], "0:6.8.0-35")
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(DistroKernelRevision.objects.count(), 1)
        self.login(self.reader)
        response = self.client.get(reverse("kernel-evidence", args=[self.a.slug, self.device.pk]))
        self.assertContains(response, "CVE-2099-10001")
        self.assertContains(response, "0:6.8.0-35")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            self.client.get(reverse("kernel-evidence", args=[self.b.slug, self.device.pk])).status_code, 404
        )

    def test_container_guest_never_claims_host_kernel_affectedness(self):
        summary = self.prepare(scope="shared")
        self.assertEqual(summary["kernel"]["state"], "shared_host_required")
        self.assertEqual(summary["kernel"]["counts"]["unresolved"], 1)
        self.assertEqual(summary["state"], "partial")
        self.assertFalse(DistroKernelRevision.objects.get().snapshot["matches"])
        self.device.refresh_from_db()
        self.device.os["kernel_scope"] = "host"
        self.device.save(update_fields=["os"])
        self.asset.kind = "vm"
        self.asset.virtualization_type = "lxc"
        self.asset.save()
        summary = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(summary["kernel"]["state"], "shared_host_required")

    def test_unsupported_running_build_stays_explicitly_unresolved(self):
        summary = self.prepare(kernel="5.4.0-65-generic")
        self.assertEqual(summary["kernel"]["state"], "kernel_build_not_covered")
        self.assertEqual(summary["kernel"]["counts"]["unresolved"], 1)
        self.assertFalse(DistroKernelRevision.objects.get().snapshot["matches"])

    def test_kernel_only_host_still_gets_a_visible_review_action(self):
        self.prepare(packages=False)
        self.login(self.reader)
        response = self.client.get(reverse("overview"))
        self.assertContains(response, "Review running-kernel version matches")
        self.assertContains(response, "1 vendor kernel definitions match")

    def test_legacy_scope_is_unknown_and_malformed_scope_is_rejected(self):
        self.enroll()
        malformed = self.data()
        malformed["os"]["kernel_scope"] = []
        self.assertEqual(self.send(malformed).status_code, 403)
        self.relax()
        self.send(self.data())
        agents.process_pending()
        self.load(XML)
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["kernel"]["state"], "scope_required")
        self.assertEqual(result["kernel"]["counts"]["unresolved"], 1)
