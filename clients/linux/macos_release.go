// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"path"
	"regexp"
	"strings"
)

const maxMacArchive = 32 * 1024 * 1024

var appleTeamPattern = regexp.MustCompile(`^[A-Z0-9]{10}$`)
var sha256Hex = regexp.MustCompile(`^[0-9a-f]{64}$`)

type macRelease struct {
	Schema   string `json:"schema"`
	Origin   string `json:"origin"`
	Sequence int64  `json:"sequence"`
	Assets   map[string]struct {
		Hash string `json:"sha256"`
		Size int    `json:"size"`
	} `json:"assets"`
}

func verifyMacRelease(raw []byte, server string, key ed25519.PublicKey, appleSigned bool) (macRelease, error) {
	var envelope struct {
		Schema    string `json:"schema"`
		Payload   string `json:"payload"`
		Signature string `json:"signature"`
	}
	var release macRelease
	invalid := errors.New("invalid or unauthenticated macOS client release")
	envelopeSchema, payloadSchema := "bearings.macos-unsigned-envelope.v1", "bearings.macos-unsigned-release.v1"
	if appleSigned {
		envelopeSchema, payloadSchema = "bearings.macos-release-envelope.v2", "bearings.macos-release.v2"
	}
	if len(raw) > 65536 || len(key) != ed25519.PublicKeySize ||
		decode(raw, &envelope) != nil || envelope.Schema != envelopeSchema {
		return release, invalid
	}
	payload, err := base64.StdEncoding.Strict().DecodeString(envelope.Payload)
	if err != nil {
		return release, invalid
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(envelope.Signature)
	if err != nil || !ed25519.Verify(key, payload, signature) || decode(payload, &release) != nil {
		return release, invalid
	}
	if release.Schema != payloadSchema || release.Origin != server || release.Sequence < 1 || len(release.Assets) != 2 {
		return release, invalid
	}
	for _, arch := range []string{"amd64", "arm64"} {
		asset := release.Assets[arch]
		if !sha256Hex.MatchString(asset.Hash) || asset.Size < 1 || asset.Size > maxMacArchive {
			return release, invalid
		}
	}
	return release, nil
}

func validateMacArchive(raw []byte, appleSigned bool) error {
	invalid := errors.New("invalid macOS app archive")
	z, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil || len(z.File) > 128 {
		return invalid
	}
	seen := map[string]bool{}
	var total uint64
	for _, entry := range z.File {
		name := strings.TrimSuffix(entry.Name, "/")
		_, duplicate := seen[name]
		if name != path.Clean(name) || strings.ContainsAny(name, "\\\x00") || duplicate ||
			(name != "Bearings.app" && !strings.HasPrefix(name, "Bearings.app/") &&
				name != "__MACOSX" && !strings.HasPrefix(name, "__MACOSX/Bearings.app/") &&
				name != "__MACOSX/Bearings.app" && name != "__MACOSX/._Bearings.app") ||
			(!entry.Mode().IsDir() && !entry.Mode().IsRegular()) ||
			entry.UncompressedSize64 > maxMacArchive {
			return invalid
		}
		total += entry.UncompressedSize64
		if total > maxMacArchive {
			return invalid
		}
		seen[name] = !entry.Mode().IsDir()
	}
	if appleSigned != seen["Bearings.app/Contents/_CodeSignature/CodeResources"] {
		return invalid
	}
	for _, name := range []string{"Info.plist", "MacOS/bearings-macos", "Resources/Bearings.icns"} {
		if !seen["Bearings.app/Contents/"+name] {
			return invalid
		}
	}
	return nil
}
