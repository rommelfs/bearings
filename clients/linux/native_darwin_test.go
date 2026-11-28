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
