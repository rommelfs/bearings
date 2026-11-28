// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
)

func TestMacReleaseAuthenticatesOriginAndAssets(t *testing.T) {
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	const server = "https://bearings.example"
	hash := strings.Repeat("a", 64)
	asset := map[string]any{"sha256": hash, "size": 12}
	payload, err := json.Marshal(map[string]any{
		"schema": "bearings.macos-release.v2", "origin": server, "sequence": 123,
		"assets": map[string]any{"arm64": asset, "amd64": asset},
	})
	if err != nil {
		t.Fatal(err)
	}
	envelope := map[string]string{
		"schema":    "bearings.macos-release-envelope.v2",
		"payload":   base64.StdEncoding.EncodeToString(payload),
		"signature": base64.StdEncoding.EncodeToString(ed25519.Sign(private, payload)),
	}
	raw, err := json.Marshal(envelope)
	if err != nil {
		t.Fatal(err)
	}
	release, err := verifyMacRelease(raw, server, public)
	if err != nil || release.Sequence != 123 || release.Assets["arm64"].Hash != hash {
		t.Fatalf("valid signed release: %+v %v", release, err)
	}
	if _, err := verifyMacRelease(raw, "https://other.example", public); err == nil {
		t.Fatal("accepted a release for a different server")
	}
	replaced := strings.Replace(string(payload), hash, strings.Repeat("b", 64), 1)
	envelope["payload"] = base64.StdEncoding.EncodeToString([]byte(replaced))
	raw, err = json.Marshal(envelope)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := verifyMacRelease(raw, server, public); err == nil {
		t.Fatal("accepted a tampered release manifest")
	}
}

func TestMacBundleArchiveRequiresResourcesAndResistsTraversal(t *testing.T) {
	pack := func(extra string, includeSeal bool) []byte {
		t.Helper()
		var body bytes.Buffer
		w := zip.NewWriter(&body)
		files := []string{"Info.plist", "MacOS/bearings-macos", "Resources/Bearings.icns"}
		if includeSeal {
			files = append(files, "_CodeSignature/CodeResources")
		}
		if extra != "" {
			files = append(files, extra)
		}
		for _, file := range files {
			if _, err := w.Create("Bearings.app/Contents/" + file); err != nil {
				t.Fatal(err)
			}
		}
		if err := w.Close(); err != nil {
			t.Fatal(err)
		}
		return body.Bytes()
	}
	if err := validateMacArchive(pack("", true)); err != nil {
		t.Fatal(err)
	}
	for _, unsupported := range [][]byte{pack("", false), pack("../../../elsewhere", true)} {
		if err := validateMacArchive(unsupported); err == nil {
			t.Fatal("accepted an unsealed or out-of-scope archive")
		}
	}
}
