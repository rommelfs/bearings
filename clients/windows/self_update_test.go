// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"debug/pe"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func updateFixture(t *testing.T) (clientRelease, ed25519.PrivateKey, []byte) {
	t.Helper()
	// Minimal, synthetic PE image, never executed by these portable tests.
	image := make([]byte, 512)
	copy(image, "MZ")
	binary.LittleEndian.PutUint32(image[60:], 128)
	copy(image[128:], "PE\x00\x00")
	binary.LittleEndian.PutUint16(image[132:], 0x8664)
	binary.LittleEndian.PutUint16(image[148:], 240)
	binary.LittleEndian.PutUint16(image[150:], 2)
	binary.LittleEndian.PutUint16(image[152:], 0x20b)
	binary.LittleEndian.PutUint32(image[260:], 16)
	if _, err := pe.NewFile(bytes.NewReader(image)); err != nil {
		t.Fatalf("synthetic PE: %v", err)
	}
	raw := zipFixture(t, map[string][]byte{"bearings-windows.exe": image, "README.md": []byte("synthetic")})
	assets := map[string]releaseAsset{}
	for arch, a := range updateArchitectures {
		assets[arch] = releaseAsset{"bearings-windows-" + a.label + ".zip", digest(raw), int64(len(raw)), digest(image), int64(len(image))}
	}
	key := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{19}, 32))
	return clientRelease{"bearings.windows-release.v1", "https://bearings.example.invalid", strings.Repeat("a", 40), 101, assets}, key, raw
}
func zipFixture(t *testing.T, files map[string][]byte) []byte {
	t.Helper()
	var buffer bytes.Buffer
	archive := zip.NewWriter(&buffer)
	for name, data := range files {
		entry, err := archive.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err = entry.Write(data); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}
func signedRelease(t *testing.T, value clientRelease, key ed25519.PrivateKey) []byte {
	t.Helper()
	payload, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	envelope := releaseEnvelope{"bearings.windows-release-envelope.v1", base64.StdEncoding.EncodeToString(payload), base64.StdEncoding.EncodeToString(ed25519.Sign(key, payload))}
	raw, err := json.Marshal(envelope)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
func TestSelfUpdateAuthenticityAndBinding(t *testing.T) {
	value, key, _ := updateFixture(t)
	public := key.Public().(ed25519.PublicKey)
	if _, err := verifyRelease(signedRelease(t, value, key), public, value.Origin, "amd64"); err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name   string
		change func(*clientRelease)
	}{
		{"origin", func(v *clientRelease) { v.Origin = "https://other.example.invalid" }},
		{"schema", func(v *clientRelease) { v.Schema = "future" }},
		{"sequence", func(v *clientRelease) { v.Sequence = 0 }},
		{"version", func(v *clientRelease) { v.Version = "latest" }},
		{"extra architecture", func(v *clientRelease) { v.Assets["riscv"] = v.Assets["amd64"] }},
		{"missing architecture", func(v *clientRelease) { delete(v.Assets, "386") }},
		{"path", func(v *clientRelease) { a := v.Assets["amd64"]; a.Name = "../evil.zip"; v.Assets["amd64"] = a }},
		{"oversize", func(v *clientRelease) { a := v.Assets["amd64"]; a.Size = maxUpdateArchive + 1; v.Assets["amd64"] = a }},
		{"digest", func(v *clientRelease) { a := v.Assets["amd64"]; a.EXESHA256 = ""; v.Assets["amd64"] = a }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			v, k, _ := updateFixture(t)
			test.change(&v)
			if _, err := verifyRelease(signedRelease(t, v, k), public, value.Origin, "amd64"); err == nil {
				t.Fatal("accepted invalid signed release")
			}
		})
	}
	raw := signedRelease(t, value, key)
	if _, err := verifyRelease(raw, ed25519.NewKeyFromSeed(bytes.Repeat([]byte{20}, 32)).Public().(ed25519.PublicKey), value.Origin, "amd64"); err == nil {
		t.Fatal("accepted another key")
	}
	raw = bytes.Replace(raw, []byte(`"signature":"`), []byte(`"signature":"A`), 1)
	if _, err := verifyRelease(raw, public, value.Origin, "amd64"); err == nil {
		t.Fatal("accepted tampering")
	}
}
func TestSelfUpdatePackageValidation(t *testing.T) {
	v, _, raw := updateFixture(t)
	asset := v.Assets["amd64"]
	if _, err := releaseExecutable(raw, asset, "amd64"); err != nil {
		t.Fatal(err)
	}
	for _, arch := range []string{"386", "arm64", "unknown"} {
		if _, err := releaseExecutable(raw, asset, arch); err == nil {
			t.Fatal("accepted wrong PE machine")
		}
	}
	if _, err := releaseExecutable(append(raw, 0), asset, "amd64"); err == nil {
		t.Fatal("accepted bad archive hash")
	}
	archive, _ := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	reader, _ := archive.File[0].Open()
	image, _ := io.ReadAll(reader)
	reader.Close()
	// Locate the executable independently of ZIP entry order.
	for _, entry := range archive.File {
		if entry.Name == "bearings-windows.exe" {
			r, _ := entry.Open()
			image, _ = io.ReadAll(r)
			r.Close()
		}
	}
	for _, name := range []string{"../escape", "/absolute", "x\\evil", "x/../evil"} {
		bad := zipFixture(t, map[string][]byte{"bearings-windows.exe": image, name: []byte("bad")})
		a := asset
		a.Size = int64(len(bad))
		a.SHA256 = digest(bad)
		if _, err := releaseExecutable(bad, a, "amd64"); err == nil {
			t.Fatalf("accepted unsafe member %q", name)
		}
	}
	wrong := asset
	wrong.EXESHA256 = strings.Repeat("0", 64)
	if _, err := releaseExecutable(raw, wrong, "amd64"); err == nil {
		t.Fatal("accepted bad executable digest")
	}
	var dup bytes.Buffer
	z := zip.NewWriter(&dup)
	for i := 0; i < 2; i++ {
		w, _ := z.Create("bearings-windows.exe")
		w.Write(image)
	}
	z.Close()
	a := asset
	a.Size = int64(dup.Len())
	a.SHA256 = digest(dup.Bytes())
	if _, err := releaseExecutable(dup.Bytes(), a, "amd64"); err == nil {
		t.Fatal("accepted duplicate executable")
	}
}
func TestSelfUpdateDownloadAndReplay(t *testing.T) {
	value, key, archive := updateFixture(t)
	downloads := 0
	redirect := false
	tamper := false
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "" || r.Header.Get("X-Bearings-Key") != "" || r.Header.Get("Signature") != "" {
			t.Error("update request leaked device credentials")
		}
		if redirect {
			http.Redirect(w, r, "https://other.example.invalid", 302)
			return
		}
		if r.URL.Path == releasePath {
			w.Write(signedRelease(t, value, key))
			return
		}
		if r.URL.Path != "/downloads/windows/bearings-windows-x64.zip" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		downloads++
		if tamper {
			w.Write([]byte("tampered"))
			return
		}
		w.Write(archive)
	}))
	defer server.Close()
	value.Origin = server.URL
	client := server.Client()
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	info := clientBuildInfo{"bearings.windows-build.v1", server.URL, base64.StdEncoding.EncodeToString(key.Public().(ed25519.PublicKey)), strings.Repeat("b", 40), 100, "amd64"}
	s := initialState()
	s.URL = server.URL
	s.Counter = 79
	s.Queue = []string{"retained signed report"}
	if _, exe, err := obtainUpdate(&s, info, client); err != nil || len(exe) == 0 {
		t.Fatalf("update: %v", err)
	}
	if downloads != 1 || s.Counter != 79 || len(s.Queue) != 1 {
		t.Fatal("changed report state")
	}
	s.Update = &clientUpdateState{Sequence: 101, Version: value.Version}
	info.Sequence = 101
	info.Version = value.Version
	if _, exe, err := obtainUpdate(&s, info, client); err != nil || exe != nil || downloads != 1 {
		t.Fatal("replayed installed sequence")
	}
	info.Sequence = 100
	info.Version = strings.Repeat("b", 40)
	if _, exe, err := obtainUpdate(&s, info, client); err != nil || exe == nil || downloads != 2 {
		t.Fatal("older executable sharing state did not catch up to the exact installed release")
	}
	info.Sequence = 101
	info.Version = strings.Repeat("c", 40)
	if _, _, err := obtainUpdate(&s, info, client); err == nil {
		t.Fatal("accepted reused sequence with different version")
	}
	s.Update = nil
	info.Sequence = 102
	if _, exe, err := obtainUpdate(&s, info, client); err != nil || exe != nil || downloads != 2 {
		t.Fatal("accepted downgrade")
	}
	info.Sequence = 100
	info.Version = strings.Repeat("b", 40)
	redirect = true
	if _, _, err := obtainUpdate(&s, info, client); err == nil {
		t.Fatal("accepted redirect")
	}
	redirect = false
	tamper = true
	if _, _, err := obtainUpdate(&s, info, client); err == nil {
		t.Fatal("accepted package tampering")
	}
	tamper = false
	info.Origin = "https://other.example.invalid"
	if _, _, err := obtainUpdate(&s, info, client); err == nil {
		t.Fatal("accepted enrollment origin change")
	}
}
