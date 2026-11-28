// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
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
		"schema": "bearings.macos-release.v1", "origin": server, "sequence": 123,
		"assets": map[string]any{"arm64": asset, "amd64": asset},
	})
	if err != nil {
		t.Fatal(err)
	}
	envelope := map[string]string{
		"schema":    "bearings.macos-release-envelope.v1",
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
