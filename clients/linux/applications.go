// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"
)

type manifestEvidence struct {
	ProfileSHA256 string `json:"profile_sha256,omitempty"`
	Identifier    string `json:"identifier,omitempty"`
	Commit        string `json:"commit,omitempty"`
	Dirty         *bool  `json:"dirty,omitempty"`
	Method        string `json:"method"`
	Path          string `json:"path"`
	SHA256        string `json:"sha256"`
}
type applicationProbe struct {
	Name           string   `json:"name,omitempty"`
	Identifier     string   `json:"identifier,omitempty"`
	Fields         []string `json:"fields,omitempty"`
	VersionPattern string   `json:"version_pattern,omitempty"`
	ID             string   `json:"id"`
	Method         string   `json:"method"`
	Path           string   `json:"path"`
}
type applicationConfiguration struct {
	Schema       string             `json:"schema"`
	Applications []applicationProbe `json:"applications"`
}

// Resolve each segment using directory descriptors. Writable application trees
// are untrusted input: never follow links or execute anything from the tree.
func openManifestFile(path string) (*os.File, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || strings.HasPrefix(path, "//") || len(path) > 1024 || strings.ContainsFunc(path, func(r rune) bool { return r < 32 || r == 127 }) {
		return nil, errors.New("use a canonical absolute manifest path")
	}
	fd, err := syscall.Open("/", syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, errors.New("cannot open manifest root")
	}
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	for i, part := range parts {
		flags := syscall.O_RDONLY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC | syscall.O_NONBLOCK
		if i < len(parts)-1 {
			flags |= syscall.O_DIRECTORY
		}
		next, e := syscall.Openat(fd, part, flags, 0)
		syscall.Close(fd)
		if e != nil {
			return nil, errors.New("manifest unavailable or contains a symlink")
		}
		fd = next
	}
	f := os.NewFile(uintptr(fd), path)
	st, err := f.Stat()
	if err != nil || !st.Mode().IsRegular() || st.Size() > 65536 || st.Mode()&(os.ModeSetuid|os.ModeSetgid) != 0 {
		f.Close()
		return nil, errors.New("manifest must be a bounded regular file")
	}
	return f, nil
}
func mispManifest(p applicationProbe) (component, error) {
	if !probeID.MatchString(p.ID) || p.Method != "misp-version-json" || filepath.Base(p.Path) != "VERSION.json" {
		return component{}, errors.New("unsupported application probe")
	}
	f, err := openManifestFile(p.Path)
	if err != nil {
		return component{}, err
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil {
		return component{}, errors.New("manifest unavailable")
	}
	raw, err := io.ReadAll(io.LimitReader(f, 4097))
	if err != nil || len(raw) > 4096 {
		return component{}, errors.New("manifest exceeds size limit")
	}
	if uniqueProbeJSON(json.NewDecoder(bytes.NewReader(raw)), 0) != nil {
		return component{}, errors.New("invalid or duplicate manifest fields")
	}
	// Exact known schema. No strings, command lines, arbitrary JSON values or
	// configuration content are ever copied into the observation.
	var fields map[string]json.RawMessage
	if err = json.Unmarshal(raw, &fields); err != nil || len(fields) != 3 {
		return component{}, errors.New("unsupported MISP version manifest")
	}
	values := []int{}
	for _, key := range []string{"major", "minor", "hotfix"} {
		var n int
		value, ok := fields[key]
		if !ok || json.Unmarshal(value, &n) != nil || string(value) == "null" || n < 0 || n > 999999 {
			return component{}, errors.New("invalid MISP version number")
		}
		values = append(values, n)
	}
	after, err := f.Stat()
	if err != nil || !unchangedProbe(before, after) {
		return component{}, errors.New("manifest changed while reading")
	}
	again, err := openManifestFile(p.Path)
	if err != nil {
		return component{}, errors.New("manifest path changed while reading")
	}
	defer again.Close()
	named, err := again.Stat()
	if err != nil || !unchangedProbe(before, named) {
		return component{}, errors.New("manifest path changed while reading")
	}
	sum := sha256.Sum256(raw)
	return component{Key: "manifest:" + p.ID + ":all", Manager: "manifest", Name: "MISP", Version: fmt.Sprintf("%d.%d.%d", values[0], values[1], values[2]), Architecture: "all", Manifest: &manifestEvidence{Method: p.Method, Path: p.Path, SHA256: hex.EncodeToString(sum[:])}}, nil
}
func applicationProbes(config string) ([]applicationProbe, error) {
	if _, err := os.Lstat(config); os.IsNotExist(err) {
		paths := []string{"/var/www/MISP/VERSION.json", "/var/www/misp/VERSION.json", "/opt/MISP/VERSION.json", "/opt/misp/VERSION.json"}
		probes := []applicationProbe{}
		for _, path := range paths {
			if _, err := os.Lstat(path); err == nil || !os.IsNotExist(err) {
				sum := sha256.Sum256([]byte(path))
				probes = append(probes, applicationProbe{ID: "misp-" + hex.EncodeToString(sum[:8]), Method: "misp-version-json", Path: path})
			}
		}
		return probes, nil
	}
	f, err := openProbeFile(config, 65536)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, 65537))
	if err != nil || len(raw) > 65536 || uniqueProbeJSON(json.NewDecoder(bytes.NewReader(raw)), 0) != nil {
		return nil, errors.New("invalid application probe configuration")
	}
	var cfg applicationConfiguration
	if decode(raw, &cfg) != nil || cfg.Schema != "bearings.application-probes.v1" || cfg.Applications == nil || len(cfg.Applications) > 16 {
		return nil, errors.New("unsupported application probe configuration")
	}
	ids, paths := map[string]bool{}, map[string]bool{}
	for _, p := range cfg.Applications {
		if !probeID.MatchString(p.ID) || ids[p.ID] || paths[p.Path] || !filepath.IsAbs(p.Path) || filepath.Clean(p.Path) != p.Path || len(p.Path) > 1024 || strings.ContainsFunc(p.Path, func(r rune) bool { return r < 32 || r == 127 }) || !validApplicationProbe(p) {
			return nil, errors.New("invalid or duplicate application probe")
		}
		ids[p.ID] = true
		paths[p.Path] = true
	}
	return cfg.Applications, nil
}
func collectApplications(config string) []component {
	probes, err := applicationProbes(config)
	if err != nil {
		fmt.Fprintln(os.Stderr, "application probe configuration unavailable:", err, "; previous observations retained")
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	out := []component{}
	for _, p := range probes {
		if ctx.Err() != nil {
			fmt.Fprintln(os.Stderr, "application collection budget exhausted; previous observations retained")
			break
		}
		var c component
		var err error
		if p.Method == "misp-version-json" {
			c, err = mispManifest(p)
		} else {
			c, err = genericApplication(ctx, p)
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "application probe %s (%s): %v; previous observation retained\n", p.ID, p.Method, err)
			continue
		}
		out = append(out, c)
	}
	return out
}

func validApplicationProbe(p applicationProbe) bool {
	if !filepath.IsAbs(p.Path) || filepath.Clean(p.Path) != p.Path || strings.HasPrefix(p.Path, "//") || len(p.Path) > 1024 || strings.ContainsFunc(p.Path, func(r rune) bool { return r < 32 || r == 127 }) {
		return false
	}
	if p.Method == "misp-version-json" {
		return filepath.Base(p.Path) == "VERSION.json" && (p.Name == "" || p.Name == "MISP") && p.Identifier == "" && len(p.Fields) == 0 && p.VersionPattern == ""
	}
	if p.Method != "file-regex" && p.Method != "json-fields" && p.Method != "git-tag" {
		return false
	}
	if !regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9+_. -]{0,127}$`).MatchString(p.Name) || !validApplicationIdentifier(p.Identifier) || len(p.VersionPattern) > 512 {
		return false
	}
	pattern, err := regexp.Compile(p.VersionPattern)
	if err != nil || pattern.NumSubexp() != 1 {
		return false
	}
	if p.Method != "json-fields" {
		return len(p.Fields) == 0
	}
	if len(p.Fields) < 1 || len(p.Fields) > 8 {
		return false
	}
	for _, field := range p.Fields {
		if !regexp.MustCompile(`^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){0,5}$`).MatchString(field) || len(field) > 120 {
			return false
		}
	}
	return true
}

func validApplicationIdentifier(id string) bool {
	if id == "" {
		return true
	}
	if len(id) > 255 || strings.ContainsFunc(id, func(r rune) bool { return r < 32 || r == 127 }) {
		return false
	}
	if strings.HasPrefix(id, "pkg:") {
		return regexp.MustCompile(`^pkg:[a-z][a-z0-9.-]*/[^\s]+$`).MatchString(id)
	}
	parts := strings.Split(id, ":")
	if len(parts) != 13 || parts[0] != "cpe" || parts[1] != "2.3" || (parts[2] != "a" && parts[2] != "o" && parts[2] != "h") {
		return false
	}
	key := regexp.MustCompile(`^[a-z0-9][a-z0-9_.+ -]{0,119}$`)
	return key.MatchString(parts[3]) && key.MatchString(parts[4])
}
