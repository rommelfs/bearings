// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"golang.org/x/sys/windows"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
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
	flags := "-X main.version=" + info.Version[:12] + " -X main.defaultServer=" + info.Origin + " -X main.releasePublicKey=" + info.Key + " -X main.releaseCommit=" + info.Version + " -X main.releaseSequence=" + strconv.FormatInt(info.Sequence, 10)
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
	value.envelope = signedRelease(t, value, key)
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
	beforeJSON, err := json.Marshal(before)
	if err != nil {
		t.Fatal(err)
	}
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
	// A post-swap state failure restores the complete previous executable.
	// Target remains running in this test during the separate atomic-replacement exercise below.
	if err := os.WriteFile(program, old, 0600); err != nil {
		t.Fatal(err)
	}
	saves := 0
	err = installRelease(program, candidate, value, next, func() error { saves++; return errors.New("synthetic state failure") })
	restored, readErr := os.ReadFile(program)
	if err == nil || readErr != nil || saves != 1 || !bytes.Equal(restored, old) {
		t.Fatalf("failed update did not roll back: %v, %v", err, readErr)
	}
	wrong := next
	wrong.Sequence++
	if err := installRelease(program, candidate, value, wrong, func() error { t.Fatal("saved unverified candidate"); return nil }); err == nil {
		t.Fatal("accepted wrong startup identity")
	}
	restored, _ = os.ReadFile(program)
	if !bytes.Equal(restored, old) {
		t.Fatal("probe failure modified installed executable")
	}
	runUpdate()
	installed, err := os.ReadFile(program)
	if err != nil || !bytes.Equal(installed, old) {
		t.Fatalf("stable bootstrap executable was overwritten: %v", err)
	}
	active, err := activeProgram(dir, info)
	if err != nil || active == "" {
		t.Fatalf("new executable was not activated: %v", err)
	}
	activated, err := os.ReadFile(active)
	if err != nil || !bytes.Equal(activated, candidate) {
		t.Fatal("activated executable mismatch")
	}
	cmd := exec.Command(program, "update", "--state-dir", stateDir, "--auto-update=status")
	raw, err := cmd.Output()
	if err != nil {
		t.Fatal(err)
	}
	var local struct {
		Build clientBuildInfo `json:"client_build"`
	}
	if json.Unmarshal(raw, &local) != nil || local.Build != next {
		t.Fatal("stable bootstrap did not start the activated client")
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
	afterJSON, marshalErr := json.Marshal(after)
	if marshalErr != nil || !bytes.Equal(beforeJSON, afterJSON) {
		t.Fatal("self-update changed enrollment, device key, counter or exact outbox bytes")
	}
	s.close()
	runUpdate()
	if downloads != 1 {
		t.Fatal("downloaded installed release again")
	}
	previousActivation, err := os.ReadFile(filepath.Join(dir, activationName))
	if err != nil {
		t.Fatal(err)
	}
	if err := installRelease(program, candidate, value, next, func() error { return errors.New("synthetic save failure with existing activation") }); err == nil {
		t.Fatal("ignored activation save failure")
	}
	afterActivation, err := os.ReadFile(filepath.Join(dir, activationName))
	if err != nil || !bytes.Equal(afterActivation, previousActivation) {
		t.Fatal("prior signed activation was not restored")
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

}

func TestSelfUpdateHoldingProcess(t *testing.T) {
	marker := os.Getenv("BEARINGS_SYNTHETIC_HOLD")
	if marker == "" {
		return
	}
	if err := os.WriteFile(marker, []byte("ready"), 0600); err != nil {
		os.Exit(3)
	}
	for {
		time.Sleep(time.Second)
	}
}

func TestSelfUpdateActivationWhileBootstrapRuns(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "bootstrap.exe")
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
			t.Fatal("synthetic bootstrap did not start")
		}
		time.Sleep(20 * time.Millisecond)
	}
	handle, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(cmd.Process.Pid))
	if err != nil {
		t.Fatal(err)
	}
	defer windows.CloseHandle(handle)
	if result, err := windows.WaitForSingleObject(handle, 0); err != nil || result != uint32(windows.WAIT_TIMEOUT) {
		t.Fatal("bootstrap exited before activation")
	}
	record := filepath.Join(dir, activationName)
	if err := atomicControlFile(record, []byte("old synthetic activation")); err != nil {
		t.Fatal(err)
	}
	expected := []byte("new synthetic activation")
	if err := atomicControlFile(record, expected); err != nil {
		t.Fatal(err)
	}
	actual, err := os.ReadFile(record)
	if err != nil || !bytes.Equal(actual, expected) {
		t.Fatal("activation was not switched atomically")
	}
	installed, err := os.ReadFile(target)
	if err != nil || !bytes.Equal(installed, raw) {
		t.Fatal("running bootstrap was modified")
	}
	if result, err := windows.WaitForSingleObject(handle, 0); err != nil || result != uint32(windows.WAIT_TIMEOUT) {
		t.Fatal("bootstrap did not survive activation")
	}
}

func TestSelfUpdateRemovalKeepsUnrelatedFiles(t *testing.T) {
	root := t.TempDir()
	programDir, stateDir := filepath.Join(root, "program"), filepath.Join(root, "state")
	for _, dir := range []string{programDir, stateDir} {
		if err := os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
	}
	program := filepath.Join(programDir, "bearings-windows.exe")
	release := filepath.Join(programDir, "bearings-windows-release-123-"+strings.Repeat("a", 64)+".exe")
	activation := filepath.Join(programDir, activationName)
	protected := filepath.Join(stateDir, "state.dpapi")
	unrelated := filepath.Join(programDir, "bearings-windows-release-local-copy.exe")
	raw := []byte("synthetic uninstall fixture")
	for _, path := range []string{program, release, activation, protected, unrelated} {
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	system, err := windows.GetSystemDirectory()
	if err != nil {
		t.Fatal(err)
	}
	task := reporterTask{
		program: program, scheduler: filepath.Join(system, "schtasks.exe"),
		name: "Bearings fixture " + digest([]byte(root))[:12],
	}
	if err := removeWindowsInstallation(task, stateDir, digest(raw), 0, false); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{program, release, activation, stateDir} {
		if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("expected %s to be removed: %v", filepath.Base(path), err)
		}
	}
	if kept, err := os.ReadFile(unrelated); err != nil || !bytes.Equal(kept, raw) {
		t.Fatalf("unrelated file changed: %v", err)
	}
}
