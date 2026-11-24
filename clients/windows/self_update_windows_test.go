// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"
)

func buildSyntheticClient(t *testing.T, path string, info clientBuildInfo) []byte {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	flags := "-X main.defaultServer=" + info.Origin + " -X main.releasePublicKey=" + info.Key + " -X main.releaseCommit=" + info.Version + " -X main.releaseSequence=" + strconv.FormatInt(info.Sequence, 10)
	cmd := exec.CommandContext(ctx, "go", "build", "-trimpath", "-ldflags", flags, "-o", path, ".")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("build synthetic client: %v\n%s", err, output)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestSelfUpdateNativeRoundTrip(t *testing.T) {
	value, key, _ := updateFixture(t)
	var archive []byte
	var downloads int
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == releasePath {
			w.Write(signedRelease(t, value, key))
			return
		}
		if r.URL.Path != "/downloads/windows/"+value.Assets[runtime.GOARCH].Name {
			t.Errorf("unexpected update path %s", r.URL.Path)
			w.WriteHeader(404)
			return
		}
		downloads++
		w.Write(archive)
	}))
	defer server.Close()
	value.Origin = server.URL
	dir := t.TempDir()
	program := filepath.Join(dir, "bearings-windows.exe")
	info := clientBuildInfo{"bearings.windows-build.v1", server.URL, base64.StdEncoding.EncodeToString(key.Public().(ed25519.PublicKey)), strings.Repeat("a", 40), 100, runtime.GOARCH}
	old := buildSyntheticClient(t, program, info)
	next := info
	next.Sequence = 101
	next.Version = strings.Repeat("b", 40)
	candidate := buildSyntheticClient(t, filepath.Join(dir, "new.exe"), next)
	archive = zipFixture(t, map[string][]byte{"bearings-windows.exe": candidate})
	value.Version = next.Version
	value.Sequence = next.Sequence
	asset := value.Assets[runtime.GOARCH]
	asset.Size = int64(len(archive))
	asset.SHA256 = digest(archive)
	asset.EXESize = int64(len(candidate))
	asset.EXESHA256 = digest(candidate)
	value.Assets[runtime.GOARCH] = asset
	ca := filepath.Join(dir, "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	stateDir := filepath.Join(dir, "state")
	s, err := openStore(stateDir, true)
	if err != nil {
		t.Fatal(err)
	}
	s.state.URL = server.URL
	s.state.CAFile = ca
	s.state.DeviceID = "11111111-1111-4111-8111-111111111111"
	expiry := time.Now().Add(24 * time.Hour)
	s.state.ExpiresAt = &expiry
	s.state.Counter = 79
	s.state.Queue = []string{"retained-exact-synthetic-report-bytes"}
	before := s.state
	if err = s.save(); err != nil {
		t.Fatal(err)
	}
	s.close()
	runUpdate := func(args ...string) {
		t.Helper()
		ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
		defer cancel()
		cmd := exec.CommandContext(ctx, program, append([]string{"update", "--state-dir", stateDir}, args...)...)
		if raw, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("synthetic self-update: %v\n%s", err, raw)
		}
	}
	runUpdate()
	installed, err := os.ReadFile(program)
	if err != nil || !bytes.Equal(installed, candidate) {
		t.Fatalf("installed executable mismatch: %v", err)
	}
	s, err = openStore(stateDir, false)
	if err != nil {
		t.Fatal(err)
	}
	if s.state.Update == nil || s.state.Update.Sequence != 101 || s.state.Update.Status != "updated" {
		t.Fatal("missing successful update state")
	}
	after := s.state
	after.Update = nil
	if !reflect.DeepEqual(before, after) {
		t.Fatal("self-update changed enrollment, device key, counter or exact outbox bytes")
	}
	s.close()
	runUpdate()
	if downloads != 1 {
		t.Fatal("downloaded installed release again")
	}
	runUpdate("--auto-update=disable")
	s, err = openStore(stateDir, false)
	if err != nil {
		t.Fatal(err)
	}
	if !s.state.Update.Disabled {
		t.Fatal("disable preference was not persisted")
	}
	s.close()
	// A post-swap state failure restores the complete previous executable.
	// Target remains running in this test during the separate atomic-replacement exercise below.
	if err := os.WriteFile(program, old, 0600); err != nil {
		t.Fatal(err)
	}
	saves := 0
	err = installRelease(program, candidate, next, func() error { saves++; return errors.New("synthetic state failure") })
	restored, readErr := os.ReadFile(program)
	if err == nil || readErr != nil || saves != 1 || !bytes.Equal(restored, old) {
		t.Fatalf("failed update did not roll back: %v, %v", err, readErr)
	}
	wrong := next
	wrong.Sequence++
	if err := installRelease(program, candidate, wrong, func() error { t.Fatal("saved unverified candidate"); return nil }); err == nil {
		t.Fatal("accepted wrong startup identity")
	}
	restored, _ = os.ReadFile(program)
	if !bytes.Equal(restored, old) {
		t.Fatal("probe failure modified installed executable")
	}
}

func TestSelfUpdateHoldingProcess(t *testing.T) {
	marker := os.Getenv("BEARINGS_SYNTHETIC_HOLD")
	if marker == "" {
		return
	}
	if err := os.WriteFile(marker, []byte("ready"), 0600); err != nil {
		os.Exit(3)
	}
	select {}
}

func TestSelfUpdateExecutingTarget(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "executing.exe")
	raw, err := os.ReadFile(os.Args[0])
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(target, raw, 0600); err != nil {
		t.Fatal(err)
	}
	marker := filepath.Join(dir, "ready")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, target, "-test.run=^TestSelfUpdateHoldingProcess$")
	cmd.Env = append(os.Environ(), "BEARINGS_SYNTHETIC_HOLD="+marker)
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { cmd.Process.Kill(); cmd.Wait() }()
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(marker); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("synthetic holding process did not start")
		}
		time.Sleep(20 * time.Millisecond)
	}
	replacement := append(append([]byte(nil), raw...), []byte("synthetic PE overlay")...)
	staged, err := stagedExecutable(dir, replacement)
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(staged)
	if err := replaceExecutable(staged, target); err != nil {
		t.Fatalf("atomic replacement of executing image: %v", err)
	}
	installed, err := os.ReadFile(target)
	if err != nil || !bytes.Equal(installed, replacement) {
		t.Fatal("executing target was not replaced")
	}
}
