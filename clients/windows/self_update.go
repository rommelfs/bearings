// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"debug/pe"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"path"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const releasePath = "/downloads/windows/update.json"
const maxRelease = 65536
const maxUpdateArchive = 32 * 1024 * 1024

var releasePublicKey, releaseSequence, releaseCommit string // Embedded by the operator's publisher.
var releaseHash = regexp.MustCompile(`^[0-9a-f]{64}$`)
var releaseVersion = regexp.MustCompile(`^[0-9a-f]{40}$`)
var updateArchitectures = map[string]struct {
	label   string
	machine uint16
}{
	"amd64": {"x64", pe.IMAGE_FILE_MACHINE_AMD64}, "arm64": {"arm64", pe.IMAGE_FILE_MACHINE_ARM64}, "386": {"x86", pe.IMAGE_FILE_MACHINE_I386},
}

type releaseAsset struct {
	Name      string `json:"name"`
	SHA256    string `json:"sha256"`
	Size      int64  `json:"size"`
	EXESHA256 string `json:"exe_sha256"`
	EXESize   int64  `json:"exe_size"`
}
type clientRelease struct {
	Schema   string                  `json:"schema"`
	Origin   string                  `json:"origin"`
	Version  string                  `json:"version"`
	Sequence int64                   `json:"sequence"`
	Assets   map[string]releaseAsset `json:"assets"`
}
type releaseEnvelope struct {
	Schema    string `json:"schema"`
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
}
type clientUpdateState struct {
	Disabled  bool      `json:"disabled"`
	CheckedAt time.Time `json:"checked_at"`
	Status    string    `json:"status"`
	Version   string    `json:"version,omitempty"`
	Sequence  int64     `json:"sequence,omitempty"`
	Error     string    `json:"error,omitempty"`
}
type clientBuildInfo struct {
	Schema       string `json:"schema"`
	Origin       string `json:"origin"`
	Key          string `json:"key"`
	Version      string `json:"version"`
	Sequence     int64  `json:"sequence"`
	Architecture string `json:"architecture"`
}

func buildInfo() clientBuildInfo {
	n, _ := strconv.ParseInt(releaseSequence, 10, 64)
	return clientBuildInfo{"bearings.windows-build.v1", defaultServer, releasePublicKey, releaseCommit, n, runtime.GOARCH}
}
func decodeStrict(raw []byte, target any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(target); err != nil {
		return err
	}
	if d.Decode(new(any)) != io.EOF {
		return errors.New("trailing JSON data")
	}
	return nil
}
func verifyRelease(raw []byte, key ed25519.PublicKey, server, architecture string) (clientRelease, error) {
	var envelope releaseEnvelope
	var result clientRelease
	invalid := errors.New("invalid or unauthenticated client release")
	if len(raw) > maxRelease || len(key) != ed25519.PublicKeySize || decodeStrict(raw, &envelope) != nil || envelope.Schema != "bearings.windows-release-envelope.v1" {
		return result, invalid
	}
	body, err := base64.StdEncoding.Strict().DecodeString(envelope.Payload)
	if err != nil || len(body) > maxRelease {
		return result, invalid
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(envelope.Signature)
	if err != nil || !ed25519.Verify(key, body, signature) || decodeStrict(body, &result) != nil {
		return result, invalid
	}
	expected, err := origin(server)
	if err != nil {
		return result, invalid
	}
	actual, err := origin(result.Origin)
	if err != nil || actual != expected || result.Schema != "bearings.windows-release.v1" || !releaseVersion.MatchString(result.Version) || result.Sequence < 1 || len(result.Assets) != 3 {
		return result, invalid
	}
	for arch, asset := range result.Assets {
		a, ok := updateArchitectures[arch]
		if !ok || asset.Name != "bearings-windows-"+a.label+".zip" || !releaseHash.MatchString(asset.SHA256) || !releaseHash.MatchString(asset.EXESHA256) || asset.Size < 1 || asset.Size > maxUpdateArchive || asset.EXESize < 1 || asset.EXESize > maxUpdateArchive {
			return result, invalid
		}
	}
	if _, ok := result.Assets[architecture]; !ok {
		return result, invalid
	}
	return result, nil
}
func releaseExecutable(raw []byte, asset releaseAsset, architecture string) ([]byte, error) {
	invalid := errors.New("client package digest, architecture or contents invalid")
	a, ok := updateArchitectures[architecture]
	if !ok || int64(len(raw)) != asset.Size || digest(raw) != asset.SHA256 {
		return nil, invalid
	}
	archive, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil || len(archive.File) > 64 {
		return nil, invalid
	}
	var executable []byte
	for _, member := range archive.File {
		name := member.Name
		if len(name) > 1024 || name == "." || path.IsAbs(name) || path.Clean(name) != name || strings.HasPrefix(name, "../") || strings.Contains(name, "\\") || !member.Mode().IsRegular() {
			return nil, invalid
		}
		if name != "bearings-windows.exe" {
			continue
		}
		if executable != nil || member.UncompressedSize64 != uint64(asset.EXESize) {
			return nil, invalid
		}
		reader, err := member.Open()
		if err != nil {
			return nil, invalid
		}
		executable, err = io.ReadAll(io.LimitReader(reader, asset.EXESize+1))
		reader.Close()
		if err != nil || int64(len(executable)) != asset.EXESize || digest(executable) != asset.EXESHA256 {
			return nil, invalid
		}
	}
	if executable == nil {
		return nil, invalid
	}
	image, err := pe.NewFile(bytes.NewReader(executable))
	if err != nil {
		return nil, invalid
	}
	defer image.Close()
	if image.Machine != a.machine || image.OptionalHeader == nil || image.Characteristics&pe.IMAGE_FILE_DLL != 0 {
		return nil, invalid
	}
	return executable, nil
}
func getReleaseFile(client *http.Client, server, path string, limit int64) ([]byte, error) {
	response, err := client.Get(server + path)
	if err != nil {
		return nil, errors.New("client update download failed")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK || response.ContentLength > limit {
		return nil, errors.New("client update download unavailable or oversized")
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil || int64(len(raw)) > limit {
		return nil, errors.New("client update download incomplete or oversized")
	}
	return raw, nil
}

// Update failure is independent of report delivery and never resets credentials/outbox.
func obtainUpdate(s *state, info clientBuildInfo, client *http.Client) (clientRelease, []byte, error) {
	var empty clientRelease
	server, err := origin(s.URL)
	if err != nil {
		return empty, nil, err
	}
	configured, err := origin(info.Origin)
	if err != nil || configured != server {
		return empty, nil, errors.New("client update origin differs from enrolled server")
	}
	key, err := base64.StdEncoding.Strict().DecodeString(info.Key)
	if err != nil || len(key) != 32 || info.Sequence < 1 {
		return empty, nil, errors.New("client has no embedded release trust anchor")
	}
	raw, err := getReleaseFile(client, server, releasePath, maxRelease)
	if err != nil {
		return empty, nil, err
	}
	release, err := verifyRelease(raw, key, server, info.Architecture)
	if err != nil {
		return empty, nil, err
	}
	floor := info.Sequence
	if s.Update != nil && s.Update.Sequence > floor {
		floor = s.Update.Sequence
	}
	if (release.Sequence == info.Sequence && release.Version != info.Version) || (s.Update != nil && release.Sequence == s.Update.Sequence && s.Update.Version != "" && release.Version != s.Update.Version) {
		return empty, nil, errors.New("client release sequence was reused for a different version")
	}
	// Another copy sharing this state may have installed the same release already.
	// Permit that exact trusted release to bring this older executable up to date.
	if release.Sequence < floor || release.Sequence == info.Sequence {
		return release, nil, nil
	}
	asset := release.Assets[info.Architecture]
	raw, err = getReleaseFile(client, server, "/downloads/windows/"+asset.Name, maxUpdateArchive)
	if err != nil {
		return empty, nil, err
	}
	executable, err := releaseExecutable(raw, asset, info.Architecture)
	return release, executable, err
}
