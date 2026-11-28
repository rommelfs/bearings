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
	ok, err := scanMacRoot(apps, false, seen)
	if !ok || err != nil || len(seen) != 1 {
		t.Fatalf("app coverage: %t %v %v", ok, err, seen)
	}
	path := filepath.Join(apps, "Utilities", "Example.app")
	key := "bundle:com.example.App:" + digest([]byte(path))
	if seen[key].Version != "3.2" || seen[key].Name != "Example" {
		t.Fatalf("wrong app observation: %+v", seen[key])
	}
	write(apps, "Broken.app/Contents/Info.plist", "invalid")
	if ok, err = scanMacRoot(apps, false, seen); ok || err != nil {
		t.Fatalf("failing app must mark coverage incomplete: %t %v", ok, err)
	}
	receipts := t.TempDir()
	write(receipts, "com.example.pkg.plist", `<plist><dict>
		<key>PackageIdentifier</key><string>com.example.pkg</string>
		<key>PackageVersion</key><string>1.4</string>
	</dict></plist>`)
	ok, err = scanMacRoot(receipts, true, seen)
	if !ok || err != nil || seen["receipt:com.example.pkg"].Version != "1.4" {
		t.Fatalf("wrong receipt observation: %t %v %+v", ok, err, seen)
	}
	cellar := t.TempDir()
	write(cellar, "python@3.12/3.12.1/INSTALL_RECEIPT.json", "{}")
	if err := scanHomebrew(cellar, seen); err != nil || len(seen) != 3 {
		t.Fatalf("wrong Homebrew observation: %v %+v", err, seen)
	}
}
