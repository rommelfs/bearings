// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMacInventoryBundleAndReceipt(t *testing.T) {
	apps := t.TempDir()
	write := func(root, relative, body string) {
		t.Helper()
		path := filepath.Join(root, relative)
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(body), 0600); err != nil {
			t.Fatal(err)
		}
	}
	write(apps, "Utilities/Example.app/Contents/Info.plist", `<plist><dict>
		<key>CFBundleIdentifier</key><string>com.example.App</string>
		<key>CFBundleName</key><string>Example</string>
		<key>CFBundleShortVersionString</key><string>3.2</string>
		<key>Other</key><dict><key>CFBundleIdentifier</key><string>unrelated</string></dict>
	</dict></plist>`)
	seen := map[string]component{}
	ok, err := scanMacRoot(apps, false, seen, nil)
	if !ok || err != nil || len(seen) != 1 {
		t.Fatalf("app coverage: %t %v %v", ok, err, seen)
	}
	path := filepath.Join(apps, "Utilities", "Example.app")
	key := "bundle:com.example.App:" + digest([]byte(path))
	if seen[key].Version != "3.2" || seen[key].Name != "Example" {
		t.Fatalf("wrong app observation: %+v", seen[key])
	}
	write(apps, "Broken.app/Contents/Info.plist", "invalid")
	if ok, err = scanMacRoot(apps, false, seen, nil); ok || err != nil {
		t.Fatalf("failing app must mark coverage incomplete: %t %v", ok, err)
	}
	receipts := t.TempDir()
	write(receipts, "com.example.pkg.plist", `<plist><dict>
		<key>PackageIdentifier</key><string>com.example.pkg</string>
		<key>PackageVersion</key><string>1.4</string>
	</dict></plist>`)
	ok, err = scanMacRoot(receipts, true, seen, nil)
	if !ok || err != nil || seen["receipt:com.example.pkg"].Version != "1.4" {
		t.Fatalf("wrong receipt observation: %t %v %+v", ok, err, seen)
	}
	cellar := t.TempDir()
	write(cellar, "python@3.12/3.12.1/INSTALL_RECEIPT.json", "{}")
	if err := scanHomebrew(cellar, seen); err != nil || len(seen) != 3 {
		t.Fatalf("wrong Homebrew observation: %v %+v", err, seen)
	}
}

func TestMacCoverageIdentifiesSourcesAndAcceptsMissingHomebrew(t *testing.T) {
	apps, systemApps, receipts := t.TempDir(), t.TempDir(), t.TempDir()
	missingCellar := filepath.Join(t.TempDir(), "missing")
	seen := map[string]component{}
	if gaps := macInventoryGaps(seen, apps, systemApps, receipts, []string{missingCellar}, nil); len(gaps) != 0 {
		t.Fatalf("optional Homebrew is not a gap: %v", gaps)
	}
	if err := os.Mkdir(filepath.Join(apps, "Broken.app"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(receipts, "com.example.pkg.plist"), []byte("invalid"), 0600); err != nil {
		t.Fatal(err)
	}
	var issues []macCoverageIssue
	gaps := macInventoryGaps(seen, apps, systemApps, receipts, []string{missingCellar}, func(issue macCoverageIssue) {
		issues = append(issues, issue)
	})
	if len(issues) != 2 || issues[0].Path != filepath.Join(apps, "Broken.app", "Contents", "Info.plist") ||
		issues[1].Source != "macos-installer-receipts" {
		t.Fatalf("unexpected local diagnostics: %v", issues)
	}
	if len(gaps) != 2 || gaps[0] != "macos-applications" || gaps[1] != "macos-installer-receipts" {
		t.Fatalf("wrong macOS coverage detail: %v", gaps)
	}
	capture := report{Scope: macScope, Gaps: &gaps}
	capture.applyCoverageCapabilities(inventoryBaseline{MacCoverage: true})
	if capture.Gaps == nil {
		t.Fatal("capable receiver lost the source details")
	}
	capture.applyCoverageCapabilities(inventoryBaseline{Supported: true})
	if capture.Gaps != nil {
		t.Fatal("older receiver was sent unsupported source details")
	}
}

func TestMacApplicationInventoryReadsFlatAndWrappedBundles(t *testing.T) {
	apps := t.TempDir()
	add := func(relative, id string) {
		t.Helper()
		path := filepath.Join(apps, relative)
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		data := "<plist><dict><key>CFBundleIdentifier</key><string>" + id + "</string></dict></plist>"
		if err := os.WriteFile(path, []byte(data), 0600); err != nil {
			t.Fatal(err)
		}
	}
	add("Flat.app/Info.plist", "com.example.flat")
	add("Wrapper.app/Wrapper/Mobile.app/Info.plist", "com.example.mobile")
	add("Linked.app/Wrapper/Linked.app/Contents/Info.plist", "com.example.linked")
	if err := os.Symlink("Wrapper/Linked.app", filepath.Join(apps, "Linked.app", "WrappedBundle")); err != nil {
		t.Fatal(err)
	}
	add("Alias.app/Wrapper/Mobile.app/Info.plist", "com.example.alias")
	if err := os.Symlink("Wrapper/Mobile.app/Info.plist", filepath.Join(apps, "Alias.app", "Info.plist")); err != nil {
		t.Fatal(err)
	}
	seen := map[string]component{}
	if complete, err := scanMacRoot(apps, false, seen, nil); err != nil || !complete {
		t.Fatalf("valid alternate layout was skipped: %t %v", complete, err)
	}
	for bundle, id := range map[string]string{"Flat.app": "flat", "Wrapper.app": "mobile", "Linked.app": "linked", "Alias.app": "alias"} {
		key := "bundle:com.example." + id + ":" + digest([]byte(filepath.Join(apps, bundle)))
		if seen[key].Name != "com.example."+id {
			t.Fatalf("no observation for %s", bundle)
		}
	}
	if err := os.Mkdir(filepath.Join(apps, "OutOfBundle.app"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("../Flat.app", filepath.Join(apps, "OutOfBundle.app", "WrappedBundle")); err != nil {
		t.Fatal(err)
	}
	if complete, err := scanMacRoot(apps, false, seen, nil); err != nil || complete || len(seen) != 4 {
		t.Fatalf("accepted a wrapped bundle outside the app directory: %t %v %+v", complete, err, seen)
	}
}

func TestMacPlistRetainsUnambiguousFieldsAfterDuplicates(t *testing.T) {
	info, err := plistInfo([]byte(`<plist><dict>
		<key>CFBundleIdentifier</key><string>com.example.app</string>
		<key>CFBundleIdentifier</key><string>com.example.app</string>
		<key>CFBundleName</key><string>Example</string>
		<key>CFBundleVersion</key><string>1</string>
		<key>CFBundleVersion</key><string>2</string>
		<key>CFBundleVersion</key><string>1</string>
	</dict></plist>`))
	if err != nil || info["CFBundleIdentifier"] != "com.example.app" || info["CFBundleName"] != "Example" || info["CFBundleVersion"] != "" {
		t.Fatalf("unambiguous fields lost or conflicting version accepted: %v %v", info, err)
	}
	info, err = plistInfo([]byte(`<plist><dict>
		<key>CFBundleIdentifier</key><string>com.example.first</string>
		<key>CFBundleIdentifier</key><string>com.example.second</string>
	</dict></plist>`))
	if err != nil || info["CFBundleIdentifier"] != "" {
		t.Fatalf("selected a conflicting bundle identity: %v %v", info, err)
	}
}
