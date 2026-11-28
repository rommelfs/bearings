// SPDX-License-Identifier: AGPL-3.0-or-later

package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNativeMacInventoryAndPrivateState(t *testing.T) {
	s, err := openStore(filepath.Join(t.TempDir(), "state"), true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	if _, err := openStore(s.dir, false); err == nil {
		t.Fatal("the state lock allowed a second writer")
	}
	report, err := collectMac()
	if err != nil {
		t.Fatal(err)
	}
	if report.OS.ID != "macos" || report.OS.Build == "" || len(report.Components) == 0 {
		t.Fatal("native capture must include the operating system and its build")
	}
	if err := s.enqueue(report); err != nil {
		t.Fatal(err)
	}
	if dir, err := os.Stat(s.dir); err != nil || dir.Mode().Perm() != 0700 {
		t.Fatal("native state directory is not private")
	}
}

func TestNativeMacAdHocBundle(t *testing.T) {
	app := filepath.Join(t.TempDir(), "Bearings.app")
	contents := filepath.Join(app, "Contents")
	source, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	binary, err := os.ReadFile(source)
	if err != nil {
		t.Fatal(err)
	}
	plist, err := os.ReadFile("macos_app.plist")
	if err != nil {
		t.Fatal(err)
	}
	icon := filepath.Join(contents, "Resources", "Bearings.icns")
	for _, item := range []struct {
		path string
		body []byte
		mode os.FileMode
	}{
		{filepath.Join(contents, "Info.plist"), plist, 0600},
		{filepath.Join(contents, "MacOS", "bearings-macos"), binary, 0700},
		{icon, []byte("original resource"), 0600},
	} {
		if err := os.MkdirAll(filepath.Dir(item.path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(item.path, item.body, item.mode); err != nil {
			t.Fatal(err)
		}
	}
	if err := appleTool("/usr/bin/codesign", "--force", "--sign", "-", app); err != nil {
		t.Fatal(err)
	}
	if err := verifyMacBundle(app); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(icon, []byte("changed resource"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verifyMacBundle(app); err == nil {
		t.Fatal("accepted a tampered ad-hoc bundle")
	}
}

func TestNativeMacUTF16PropertyList(t *testing.T) {
	xml := `<?xml version="1.0" encoding="UTF-16"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>com.example.UTF16</string></dict></plist>`
	raw := []byte{0xff, 0xfe}
	for _, ch := range []byte(xml) {
		raw = append(raw, ch, 0)
	}
	info, err := plistInfo(raw)
	if err != nil || info["CFBundleIdentifier"] != "com.example.UTF16" {
		t.Fatalf("could not read native UTF-16 property list: %v %v", info, err)
	}
}
