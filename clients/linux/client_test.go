// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"bytes"
	"crypto/ed25519"
	"encoding/json"
	"encoding/pem"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestIndependentRFC9421Vector(t *testing.T) {
	raw, err := os.ReadFile("testdata/http-signature.json")
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		Note     string
		Body     string
		Identity string
		URL      string
		Headers  map[string]string
	}
	if err = json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	seed := make([]byte, 32)
	for i := range seed {
		seed[i] = byte(i)
	}
	req, _ := http.NewRequest("POST", v.URL, strings.NewReader(v.Body))
	sign(req, []byte(v.Body), ed25519.NewKeyFromSeed(seed), v.Identity, time.Unix(1700000000, 0), "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
	for k, want := range v.Headers {
		if got := req.Header.Get(k); got != want {
			t.Errorf("%s differs from independent Python oracle:\n%s\n%s", k, got, want)
		}
	}
}
func TestOriginsAndPrivateState(t *testing.T) {
	for _, u := range []string{"http://localhost:8000", "https://name:password@example.org", "https://example.org/other", "https://example.org/?token=secret"} {
		if _, err := origin(u); err == nil {
			t.Fatal("unsafe origin accepted", u)
		}
	}
	dir := filepath.Join(t.TempDir(), "state")
	s, err := openStore(dir, true)
	if err != nil {
		t.Fatal(err)
	}
	public := s.public()
	if _, err = openStore(dir, false); err == nil {
		t.Fatal("concurrent state writer accepted")
	}
	s.close()
	s, err = openStore(dir, true)
	if err != nil {
		t.Fatal(err)
	}
	if s.public() != public {
		t.Fatal("repeat init rotated the device key")
	}
	s.close()
	if err = os.Chmod(filepath.Join(dir, "key"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err = openStore(dir, false); err == nil {
		t.Fatal("world-readable private key accepted")
	}
	link := filepath.Join(t.TempDir(), "symlink")
	os.Symlink(dir, link)
	if _, err = openStore(link, false); err == nil {
		t.Fatal("symlink state accepted")
	}
}
func TestNativePackageVersionsAndParallelRPM(t *testing.T) {
	deb, err := parsePackages([]byte("installed\tnginx\t1:1.24.0-2ubuntu7.5\tamd64\nconfig-files\tremoved\t1\tall\ninstalled\tlibc6\t2.39-0ubuntu8\tarm64\n"), "dpkg")
	if err != nil || len(deb) != 2 || deb[1].Version != "1:1.24.0-2ubuntu7.5" {
		t.Fatal(deb, err)
	}
	rpm, err := parsePackages([]byte("kernel-core\t0:5.14.0-1.el9\tx86_64\nkernel-core\t0:5.14.0-2.el9\tx86_64\ngpg-pubkey\t0:123-456\t(none)\nnginx\t1:1.20.1-10.el9\tx86_64\n"), "rpm")
	if err != nil || len(rpm) != 3 || rpm[0].Key == rpm[1].Key || !strings.Contains(rpm[0].Key, "@") {
		t.Fatal(rpm, err)
	}
	for _, raw := range []string{"installed\tnginx\t1\tamd64\ninstalled\tnginx\t1\tamd64\n", "truncated\n", ""} {
		if _, err = parsePackages([]byte(raw), "dpkg"); err == nil {
			t.Fatal("partial/ambiguous package list accepted")
		}
	}
	vars := osRelease([]byte("ID=ubuntu\nVERSION_ID=\"24.04\"\nEVIL=$(touch /tmp/not-executed)\n"))
	if vars["ID"] != "ubuntu" || len(vars) != 2 {
		t.Fatal(vars)
	}
}
func trustedTestServer(t *testing.T, handler http.Handler) (*httptest.Server, string) {
	t.Helper()
	srv := httptest.NewTLSServer(handler)
	t.Cleanup(srv.Close)
	path := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: srv.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	return srv, path
}
func TestTLSVerificationRedirectRefusalAndQueueReceipt(t *testing.T) {
	mode := "bad_receipt"
	requests := 0
	srv, ca := trustedTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		raw, _ := io.ReadAll(r.Body)
		var report report
		json.Unmarshal(raw, &report)
		if mode == "redirect" {
			http.Redirect(w, r, "https://example.invalid", http.StatusTemporaryRedirect)
			return
		}
		h := digest(raw)
		if mode == "bad_receipt" {
			h = "wrong"
		}
		w.WriteHeader(202)
		json.NewEncoder(w).Encode(receipt{Schema: "bearings.agent.receipt.v1", ReportID: report.ReportID, Sequence: report.Sequence, Hash: h, Status: "pending", ReceivedAt: time.Now().UTC().Format(time.RFC3339)})
	}))
	s, err := openStore(filepath.Join(t.TempDir(), "state"), true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	s.config = configuration{URL: srv.URL, DeviceID: newID(), CAFile: ca, ExpiresAt: time.Now().Add(time.Hour).UTC().Format(time.RFC3339)}
	pending := &report{Schema: tag, ReportID: newID(), Services: []service{}}
	if err = s.enqueue(pending); err != nil {
		t.Fatal(err)
	}
	if err = flush(s); err == nil {
		t.Fatal("unmatched receipt removed a pending report")
	}
	names, _, _ := s.queue()
	if len(names) != 1 {
		t.Fatal("lost pending report")
	}
	mode = "redirect"
	if err = flush(s); err == nil {
		t.Fatal("redirect accepted")
	}
	s.config.CAFile = ""
	if err = flush(s); err == nil {
		t.Fatal("untrusted server certificate accepted")
	}
	s.config.CAFile = ca
	mode = "good"
	if err = flush(s); err != nil {
		t.Fatal(err)
	}
	names, _, _ = s.queue()
	if len(names) != 0 {
		t.Fatal("durably acknowledged input not removed")
	}
	if requests != 3 {
		t.Fatal("unexpected redirect or TLS-bypassed request", requests)
	}
}
func TestRunningOldExecutableAfterAtomicUpdate(t *testing.T) {
	dir := t.TempDir()
	installed := filepath.Join(dir, "nginx")
	binary, err := os.ReadFile(os.Args[0])
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(installed, binary, 0700); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(installed, "-test.run=^TestExecutableChild$")
	cmd.Env = append(os.Environ(), "BEARINGS_TEST_EXECUTABLE_CHILD=1")
	in, _ := cmd.StdinPipe()
	out, _ := cmd.StdoutPipe()
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { in.Close(); cmd.Process.Kill(); cmd.Wait() }()
	ready := make([]byte, 1)
	if _, err = io.ReadFull(out, ready); err != nil {
		t.Fatal(err)
	}
	match, err := compareExecutable("/proc", cmd.Process.Pid, installed)
	if err != nil || !match {
		t.Fatal("initial executable mismatch", err)
	}
	updated := filepath.Join(dir, "updated")
	if err = os.WriteFile(updated, []byte("new package executable"), 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Rename(updated, installed); err != nil {
		t.Fatal(err)
	}
	match, err = compareExecutable("/proc", cmd.Process.Pid, installed)
	if err != nil || match {
		t.Fatal("old running executable was mistaken for updated file", match, err)
	}
}
func TestExecutableChild(t *testing.T) {
	if os.Getenv("BEARINGS_TEST_EXECUTABLE_CHILD") != "1" {
		return
	}
	os.Stdout.Write([]byte{'R'})
	io.Copy(io.Discard, os.Stdin)
	os.Exit(0)
}
func TestOutboxNeverEvictsAndDoesNotExecuteVersionCommands(t *testing.T) {
	s, err := openStore(filepath.Join(t.TempDir(), "state"), true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	for i := 0; i < 64; i++ {
		if err = s.enqueue(&report{Schema: tag, ReportID: newID()}); err != nil {
			t.Fatal(err)
		}
	}
	if err = s.enqueue(&report{Schema: tag, ReportID: newID()}); err == nil {
		t.Fatal("outbox quota bypassed")
	}
	names, _, _ := s.queue()
	if len(names) != 64 {
		t.Fatal("pending input evicted")
	}
	if _, err = collect(false, nil, "../../bin/sh"); err == nil {
		t.Fatal("arbitrary service command accepted")
	}
	var b cappedBuffer
	b.limit = 2
	if _, err = b.Write(bytes.Repeat([]byte{'x'}, 3)); err == nil {
		t.Fatal("output bound bypassed")
	}
}

func TestBootstrapRefusesRetargetedGrantAndChangedRollout(t *testing.T) {
	s, err := openStore(filepath.Join(t.TempDir(), "state"), true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	requests := 0
	srv, ca := trustedTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		if r.URL.Path != "/api/v1/agent/bootstrap/" {
			t.Error("untrusted grant was redeemed")
		}
		json.NewEncoder(w).Encode(grant{Schema: "bearings.agent.grant.v1", URL: "https://another.example.invalid", PublicKey: s.public(), RegisterHost: true, Grant: newID() + "." + strings.Repeat("s", 43), ExpiresAt: time.Now().Add(time.Minute).Format(time.RFC3339)})
	}))
	token := newID() + "." + strings.Repeat("x", 43)
	if err = bootstrap(s, srv.URL, ca, strings.NewReader(token)); err == nil {
		t.Fatal("retargeted grant accepted")
	}
	if _, err = os.Stat(filepath.Join(s.dir, "bootstrap-grant.json")); !os.IsNotExist(err) {
		t.Fatal("untrusted grant persisted")
	}
	if err = bootstrap(s, srv.URL, ca, strings.NewReader(newID()+"."+strings.Repeat("x", 43))); err == nil {
		t.Fatal("different pending rollout accepted")
	}
	if err = bootstrap(s, srv.URL, ca, strings.NewReader(strings.Repeat("x", 151))); err == nil {
		t.Fatal("oversized secret accepted")
	}
	if requests != 1 {
		t.Fatal("unexpected bootstrap retry", requests)
	}
}

func TestDpkgSourcePackageMetadataAndLegacyCompatibility(t *testing.T) {
	rows, err := parsePackages([]byte("installed\tlibssl3\t3.0.16-1~deb12u1+b1\tamd64\topenssl\t3.0.16-1~deb12u1\n"), "dpkg")
	if err != nil {
		t.Fatal(err)
	}
	if rows[0].Source == nil || rows[0].Source.Name != "openssl" || rows[0].Source.Version != "3.0.16-1~deb12u1" {
		t.Fatal("source version was inferred from the binary version", rows)
	}
	old, err := parsePackages([]byte("installed\tlibssl3\t3.0.16-1~deb12u1\tamd64\n"), "dpkg")
	if err != nil || old[0].Source != nil {
		t.Fatal("legacy observation stopped working")
	}
	if _, err = parsePackages([]byte("installed\tlibssl3\t3.0\tamd64\topenssl\t\n"), "dpkg"); err == nil {
		t.Fatal("empty source version accepted as complete")
	}
}

func TestArchiveBootstrapAfterRolloutDenial(t *testing.T) {
	s, err := openStore(filepath.Join(t.TempDir(), "state"), true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	key := s.public()
	srv, ca := trustedTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	token := newID() + "." + strings.Repeat("x", 43)
	if err = bootstrap(s, srv.URL, ca, strings.NewReader(token)); err == nil || !strings.Contains(err.Error(), "invalid or expired") {
		t.Fatalf("rollout denial did not explain invalid or expired keys: %v", err)
	}
	path := filepath.Join(s.dir, "bootstrap.json")
	pending, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	grantPath := filepath.Join(s.dir, "bootstrap-grant.json")
	if err = os.WriteFile(grantPath, []byte("synthetic"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = archiveBootstrap(s); err == nil {
		t.Fatal("archive allowed when a grant was retained")
	}
	if err = os.Remove(grantPath); err != nil {
		t.Fatal(err)
	}
	name, err := archiveBootstrap(s)
	if err != nil || name == "" {
		t.Fatalf("archive failed: %s %v", name, err)
	}
	raw, err := os.ReadFile(filepath.Join(s.dir, name))
	if err != nil || !bytes.Equal(raw, pending) || s.public() != key || bytes.Contains(raw, []byte(token)) {
		t.Fatal("archive did not preserve the attempt and device key without the bearer")
	}
	if next, err := archiveBootstrap(s); err != nil || next != "" {
		t.Fatalf("archive should be idempotent: %s %v", next, err)
	}
	newToken := newID() + "." + strings.Repeat("y", 43)
	if err = bootstrap(s, srv.URL, ca, strings.NewReader(newToken)); err == nil || !strings.Contains(err.Error(), "invalid or expired") {
		t.Fatalf("fresh rollout was blocked locally: %v", err)
	}
}
