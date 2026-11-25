// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestNativeProtectedStateAndLock(t *testing.T) {
	if dir := os.Getenv("BEARINGS_TEST_LOCK_PROBE"); dir != "" {
		s, err := openStore(dir, false)
		if err == nil {
			s.close()
			os.Exit(2)
		}
		if err.Error() != "state is already in use or cannot be locked" {
			os.Exit(3)
		}
		os.Exit(0)
	}
	dir := t.TempDir()
	s, err := openStore(dir, true)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if s != nil {
			s.close()
		}
	}()
	key := s.state.publicKey()
	if err = enqueue(&s.state, s.save, &report{Schema: tag, ID: identifier()}); err != nil {
		t.Fatal(err)
	}
	queued := s.state.Queue[0]
	cmd := exec.Command(os.Args[0], "-test.run=^TestNativeProtectedStateAndLock$")
	cmd.Env = append(os.Environ(), "BEARINGS_TEST_LOCK_PROBE="+dir)
	if err = cmd.Run(); err != nil {
		t.Fatalf("a second process did not report lock contention: %v", err)
	}
	s.close()
	s = nil
	path := filepath.Join(dir, "state.dpapi")
	raw, err := os.ReadFile(path)
	if err != nil || bytes.Contains(raw, []byte(queued)) {
		t.Fatal("protected state unavailable or plaintext")
	}
	s, err = openStore(dir, false)
	if err != nil || s.state.publicKey() != key || len(s.state.Queue) != 1 || s.state.Queue[0] != queued {
		t.Fatalf("reopening protected state did not preserve the key and queue: %v", err)
	}
	s.close()
	s = nil
	raw[len(raw)-1] ^= 1
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	if other, err := openStore(dir, true); err == nil {
		other.close()
		t.Fatal("tampered state opened or replaced")
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(after, raw) {
		t.Fatal("tampered state was rewritten")
	}
}

func TestNativeRegistry(t *testing.T) {
	value, err := collect()
	if err != nil {
		t.Fatal(err)
	}
	count := 0
	for _, c := range value.Components {
		if c.Windows.Kind == "os" {
			count++
		}
	}
	raw, err := reportBytes(value)
	if count != 1 || value.OS.ID != "windows" || err != nil || len(raw) > maxBody {
		t.Fatal("registry snapshot does not meet the inventory contract")
	}
}

func TestNativeUninstallKeepsChangedStateAndRemovesOnlyOwnedFiles(t *testing.T) {
	task, err := currentReporterTask()
	if err != nil {
		t.Fatal(err)
	}
	task.name = "Bearings Test " + identifier()
	task.program = filepath.Join(t.TempDir(), "bearings-windows.exe")
	dir := t.TempDir()
	statePath, userFile := filepath.Join(dir, "state.dpapi"), filepath.Join(dir, "keep.txt")
	for _, path := range []string{task.program, statePath, userFile} {
		if err := os.WriteFile(path, []byte("synthetic test"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := removeWindowsInstallation(task, dir, digest([]byte("other state")), 0, false); err == nil {
		t.Fatal("the helper accepted a changed state file")
	}
	if _, err := os.Stat(task.program); err != nil {
		t.Fatal(err)
	}
	stateHash, err := removalStateDigest(dir)
	if err != nil {
		t.Fatal(err)
	}
	if err := removeWindowsInstallation(task, dir, stateHash, 0, false); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{task.program, statePath} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("owned file remains: %v", err)
		}
	}
	if _, err := os.Stat(userFile); err != nil {
		t.Fatal(err)
	}
}
