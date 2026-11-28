// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"regexp"
)

const maxMacBinary = 32 * 1024 * 1024

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

func verifyMacRelease(raw []byte, server string, key ed25519.PublicKey) (macRelease, error) {
	var envelope struct {
		Schema    string `json:"schema"`
		Payload   string `json:"payload"`
		Signature string `json:"signature"`
	}
	var release macRelease
	invalid := errors.New("invalid or unauthenticated macOS client release")
	if len(raw) > 65536 || len(key) != ed25519.PublicKeySize ||
		decode(raw, &envelope) != nil || envelope.Schema != "bearings.macos-release-envelope.v1" {
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
	if release.Schema != "bearings.macos-release.v1" || release.Origin != server || release.Sequence < 1 || len(release.Assets) != 2 {
		return release, invalid
	}
	for _, arch := range []string{"amd64", "arm64"} {
		asset := release.Assets[arch]
		if !sha256Hex.MatchString(asset.Hash) || asset.Size < 1 || asset.Size > maxMacBinary {
			return release, invalid
		}
	}
	return release, nil
}
