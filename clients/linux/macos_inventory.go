// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"bytes"
	"context"
	"encoding/xml"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"slices"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"
)

const macScope = "macos-machine"
const maxPlist = 1024 * 1024

var bundleID = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`)
var formulaName = regexp.MustCompile(`^[a-z0-9][a-z0-9+._@-]{0,127}$`)
var macVersion = regexp.MustCompile(`^[0-9]+\.[0-9]+(\.[0-9]+)?$`)
var macBuild = regexp.MustCompile(`^[0-9]{1,4}[A-Z][0-9]{1,10}[a-z]?$`)
var plistKeys = map[string]bool{
	"CFBundleIdentifier": true, "CFBundleName": true,
	"CFBundleShortVersionString": true, "CFBundleVersion": true,
	"CFBundleExecutable": true, "PackageIdentifier": true, "PackageVersion": true,
}

func plistInfo(raw []byte) (map[string]string, error) {
	// Apple also accepts UTF-16 plists. Normalize those with the same bounded
	// system parser used for binary plists.
	utf16 := len(raw) >= 2 && ((raw[0] == 0xff && raw[1] == 0xfe) ||
		(raw[0] == 0xfe && raw[1] == 0xff) || raw[0] == 0 || raw[1] == 0)
	if bytes.HasPrefix(raw, []byte("bplist00")) || utf16 {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "/usr/bin/plutil", "-convert", "xml1", "-o", "-", "-")
		cmd.Stdin = bytes.NewReader(raw)
		out := &cappedBuffer{limit: maxPlist}
		cmd.Stdout = out
		if err := cmd.Run(); err != nil {
			return nil, errors.New("cannot normalize property list")
		}
		raw = out.Bytes()
	}
	d := xml.NewDecoder(bytes.NewReader(raw))
	result := map[string]string{}
	conflicted := map[string]bool{}
	depth := 0
	key := ""
	for {
		token, err := d.Token()
		if err != nil {
			if err == io.EOF && depth == 0 {
				return result, nil
			}
			return nil, errors.New("invalid property list")
		}
		switch item := token.(type) {
		case xml.StartElement:
			if depth == 2 && (item.Name.Local == "key" || item.Name.Local == "string") {
				var value string
				if err := d.DecodeElement(&value, &item); err != nil {
					return nil, err
				}
				if item.Name.Local == "key" {
					key = value
				} else {
					if plistKeys[key] && !conflicted[key] {
						value = strings.TrimSpace(value)
						if previous, repeated := result[key]; repeated && previous != value {
							delete(result, key)
							conflicted[key] = true
						} else {
							result[key] = value
						}
					}
					key = ""
				}
				continue
			}
			if depth == 2 {
				key = ""
			}
			depth++
		case xml.EndElement:
			depth--
		}
	}
}

func readPlist(root *os.Root, name string) (map[string]string, error) {
	return readMacPlist(root, name, false)
}

func readMacPlist(root *os.Root, name string, containedLinks bool) (map[string]string, error) {
	stat, flags := root.Lstat, os.O_RDONLY|syscall.O_NONBLOCK|syscall.O_NOFOLLOW
	if containedLinks {
		stat, flags = root.Stat, os.O_RDONLY|syscall.O_NONBLOCK
	}
	info, err := stat(name)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > maxPlist {
		return nil, errors.New("property list must be a bounded regular file")
	}
	f, err := root.OpenFile(name, flags, 0)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	opened, err := f.Stat()
	if err != nil || !os.SameFile(info, opened) {
		return nil, errors.New("property list changed during capture")
	}
	raw, err := io.ReadAll(io.LimitReader(f, maxPlist+1))
	if err != nil || len(raw) > maxPlist {
		return nil, errors.New("property list could not be read within its size limit")
	}
	return plistInfo(raw)
}

func readMacBundleInfo(root *os.Root, name string) (map[string]string, string, error) {
	const conventional = "Contents/Info.plist"
	display := filepath.Join(name, conventional)
	app, err := root.OpenRoot(name)
	if err != nil {
		return nil, display, err
	}
	defer app.Close()
	// The app root confines metadata links even when a wrapper links its plist
	// or WrappedBundle to another directory inside the app.
	var missing error
	for _, relative := range []string{conventional, "Info.plist", "WrappedBundle/Info.plist", "WrappedBundle/Contents/Info.plist"} {
		info, err := readMacPlist(app, relative, true)
		if !os.IsNotExist(err) {
			return info, filepath.Join(name, relative), err
		}
		if missing == nil {
			missing = err
		}
	}
	entries, err := readMacDirectory(app, "Wrapper")
	if os.IsNotExist(err) {
		return nil, display, missing
	}
	if err != nil {
		return nil, filepath.Join(name, "Wrapper"), err
	}
	var wrapped string
	for _, entry := range entries {
		if entry.IsDir() && strings.HasSuffix(strings.ToLower(entry.Name()), ".app") {
			if wrapped != "" {
				return nil, filepath.Join(name, "Wrapper"), errors.New("multiple wrapped application bundles")
			}
			wrapped = filepath.Join("Wrapper", entry.Name())
		}
	}
	if wrapped == "" {
		return nil, display, missing
	}
	for _, leaf := range []string{"Info.plist", conventional} {
		relative := filepath.Join(wrapped, leaf)
		info, err := readMacPlist(app, relative, true)
		if !os.IsNotExist(err) {
			return info, filepath.Join(name, relative), err
		}
	}
	return nil, display, missing
}

func observationText(value string, length int) bool {
	return value != "" && utf8.ValidString(value) && utf8.RuneCountInString(value) <= length &&
		!strings.ContainsFunc(value, func(r rune) bool { return r < 32 || r == 127 })
}

func macComponent(key, name, version string) component {
	if !observationText(version, 120) {
		version = ""
	}
	return component{Key: "mac-app:" + key, Manager: "mac-app", Name: name, Version: version, Architecture: "all"}
}

type macCoverageIssue struct {
	Source string `json:"source"`
	Path   string `json:"path"`
	Reason string `json:"reason"`
}

func scanMacRoot(path string, receipt bool, seen map[string]component, issue func(string, error)) (bool, error) {
	root, err := os.OpenRoot(path)
	if err != nil {
		return false, err
	}
	defer root.Close()
	complete := true
	incomplete := func(name string, err error) {
		complete = false
		if issue != nil {
			issue(filepath.Join(path, name), err)
		}
	}
	var visit func(string, int) error
	visit = func(dir string, depth int) error {
		entries, err := readMacDirectory(root, dir)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			name := filepath.Join(dir, entry.Name())
			switch {
			case receipt && strings.HasSuffix(entry.Name(), ".plist") && entry.Type().IsRegular():
				id := strings.TrimSuffix(entry.Name(), ".plist")
				if !bundleID.MatchString(id) {
					continue
				}
				info, err := readPlist(root, name)
				if err == nil && info["PackageIdentifier"] != id {
					err = errors.New("PackageIdentifier does not match the installer receipt")
				}
				if err != nil {
					incomplete(name, err)
					continue
				}
				key := "receipt:" + id
				seen[key] = macComponent(key, id, info["PackageVersion"])
			case !receipt && entry.IsDir() && strings.HasSuffix(strings.ToLower(entry.Name()), ".app"):
				info, plist, err := readMacBundleInfo(root, name)
				id := info["CFBundleIdentifier"]
				if err == nil && !bundleID.MatchString(id) {
					err = errors.New("CFBundleIdentifier is missing, unsupported or conflicting")
				}
				if err != nil {
					incomplete(plist, err)
					continue
				}
				display := info["CFBundleName"]
				if !observationText(display, 128) {
					display = id
				}
				version := info["CFBundleShortVersionString"]
				if !observationText(version, 120) {
					version = info["CFBundleVersion"]
				}
				key := "bundle:" + id + ":" + digest([]byte(filepath.Join(path, name)))
				seen[key] = macComponent(key, display, version)
			case !receipt && entry.IsDir() && depth < 2 &&
				!strings.HasPrefix(entry.Name(), ".") && !strings.Contains(entry.Name(), "."):
				if err := visit(name, depth+1); err != nil {
					incomplete(name, err)
				}
			}
			if len(seen) > 5000 {
				return errors.New("macOS inventory exceeds the server observation limit")
			}
		}
		return nil
	}
	err = visit(".", 0)
	return complete, err
}

func scanHomebrew(path string, seen map[string]component) error {
	root, err := os.OpenRoot(path)
	if err != nil {
		return err
	}
	defer root.Close()
	formulas, err := readMacDirectory(root, ".")
	if err != nil {
		return err
	}
	for _, formula := range formulas {
		name := formula.Name()
		if !formula.IsDir() || !formulaName.MatchString(name) {
			continue
		}
		versions, err := readMacDirectory(root, name)
		if err != nil {
			return err
		}
		for _, version := range versions {
			if !version.IsDir() || !observationText(version.Name(), 120) ||
				strings.HasPrefix(version.Name(), ".") {
				continue
			}
			dir := filepath.Join(name, version.Name())
			receipt, err := root.Lstat(filepath.Join(dir, "INSTALL_RECEIPT.json"))
			if os.IsNotExist(err) {
				continue
			}
			if err != nil || !receipt.Mode().IsRegular() {
				return errors.New("cannot verify the Homebrew installation receipt")
			}
			key := "brew:" + name + ":" + digest([]byte(filepath.Join(path, dir)))
			seen[key] = macComponent(key, name, version.Name())
			if len(seen) > 5000 {
				return errors.New("macOS inventory exceeds the server observation limit")
			}
		}
	}
	return nil
}

func readMacDirectory(root *os.Root, dir string) ([]os.DirEntry, error) {
	f, err := root.Open(dir)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	entries, err := f.ReadDir(8193)
	if err != nil && err != io.EOF {
		return nil, err
	}
	if len(entries) > 8192 {
		return nil, errors.New("macOS inventory directory exceeds its read limit")
	}
	return entries, nil
}

func collectMac() (*report, error) {
	return collectMacWithCoverage(nil)
}

func collectMacWithCoverage(issue func(macCoverageIssue)) (*report, error) {
	operating := operatingSystem{ID: "macos", Architecture: "arm64", KernelScope: "host", RebootHint: "unknown"}
	if runtime.GOARCH == "amd64" {
		operating.Architecture = "x86_64"
		// Report the hardware even when the Intel download runs under Rosetta.
		if raw, err := command("/usr/sbin/sysctl", "-n", "hw.optional.arm64"); err == nil && strings.TrimSpace(string(raw)) == "1" {
			operating.Architecture = "arm64"
		}
	}
	for _, probe := range []struct {
		command, option string
		result          *string
	}{
		{"/usr/bin/sw_vers", "-productVersion", &operating.Version},
		{"/usr/bin/sw_vers", "-buildVersion", &operating.Build},
		{"/usr/bin/uname", "-r", &operating.Kernel},
	} {
		raw, err := command(probe.command, probe.option)
		if err != nil {
			return nil, err
		}
		*probe.result = strings.TrimSpace(string(raw))
	}
	if !macVersion.MatchString(operating.Version) || !macBuild.MatchString(operating.Build) ||
		!macVersion.MatchString(operating.Kernel) {
		return nil, errors.New("unexpected macOS release, build or Darwin kernel format")
	}
	seen := map[string]component{"os": macComponent("os", "macOS", operating.Version)}
	gaps := macInventoryGaps(seen,
		"/Applications", "/System/Applications", "/private/var/db/receipts",
		[]string{"/opt/homebrew/Cellar", "/usr/local/Cellar"}, issue,
	)
	if len(seen) > 5000 {
		return nil, errors.New("macOS inventory exceeds the server observation limit")
	}
	components := make([]component, 0, len(seen))
	for _, item := range seen {
		components = append(components, item)
	}
	slices.SortFunc(components, func(a, b component) int { return strings.Compare(a.Key, b.Key) })
	return &report{Schema: tag, ReportID: newID(), ObservedAt: time.Now().UTC().Format(time.RFC3339Nano), Scope: macScope, OS: operating, Complete: len(gaps) == 0, Components: components, Services: []service{}, Gaps: &gaps}, nil
}

func macInventoryGaps(seen map[string]component, apps, systemApps, receipts string, cellars []string, issue func(macCoverageIssue)) []string {
	gaps := []string{}
	for _, source := range []struct {
		path, gap string
		receipts  bool
	}{
		{apps, "macos-applications", false},
		{systemApps, "macos-system-applications", false},
		{receipts, "macos-installer-receipts", true},
	} {
		record := func(path string, err error) {
			if issue != nil {
				issue(macCoverageIssue{Source: source.gap, Path: path, Reason: err.Error()})
			}
		}
		ok, err := scanMacRoot(source.path, source.receipts, seen, record)
		if err != nil {
			record(source.path, err)
		}
		if err != nil || !ok {
			gaps = append(gaps, source.gap)
		}
	}
	for _, path := range cellars {
		if err := scanHomebrew(path, seen); err != nil && !os.IsNotExist(err) {
			if issue != nil {
				issue(macCoverageIssue{Source: "macos-homebrew", Path: path, Reason: err.Error()})
			}
			if !slices.Contains(gaps, "macos-homebrew") {
				gaps = append(gaps, "macos-homebrew")
			}
		}
	}
	return gaps
}
