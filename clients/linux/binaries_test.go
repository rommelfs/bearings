// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestBinaryProbeChild(t *testing.T) {
	mode := os.Args[len(os.Args)-1]
	if !strings.HasPrefix(mode, "probe-") {
		return
	}
	status, _ := os.ReadFile("/proc/self/status")
	if !strings.Contains(string(status), "NoNewPrivs:\t1") || os.Getenv("HOME") != "" || os.Getenv("BEARINGS_PROBE_TEST_SECRET") != "" {
		os.Exit(12)
	}
	switch mode {
	case "probe-replace":
		raw, err := os.ReadFile("/proc/self/exe")
		if err != nil {
			os.Exit(13)
		}
		if err = os.WriteFile(os.Args[0]+".new", raw, 0700); err != nil {
			os.Exit(14)
		}
		if err = os.Rename(os.Args[0]+".new", os.Args[0]); err != nil {
			os.Exit(15)
		}
		fmt.Println("SYNTHETIC version 1.2.3")
	case "probe-normal":
		fmt.Println("SYNTHETIC version 1.2.3")
	case "probe-stderr":
		fmt.Fprintln(os.Stderr, "SYNTHETIC version 2.0.0-build7")
	case "probe-ambiguous":
		fmt.Println("SYNTHETIC version 1.2.3\nSYNTHETIC version 4.5.6")
	case "probe-output":
		fmt.Print(strings.Repeat("x", 20000))
	case "probe-sleep":
		time.Sleep(10 * time.Second)
	case "probe-failed":
		fmt.Println("SYNTHETIC version 1.2.3")
		os.Exit(7)
	}
	os.Exit(0)
}
func testProbe(t *testing.T, mode string) binaryProbe {
	t.Helper()
	path, err := filepath.EvalSymlinks(os.Args[0])
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	path = filepath.Join(t.TempDir(), "synthetic-tool")
	if err = os.WriteFile(path, raw, 0700); err != nil {
		t.Fatal(err)
	}
	return binaryProbe{ID: "custom-tool", Name: "synthetic-tool", Executable: path, Args: []string{"-test.run=TestBinaryProbeChild", "--", mode}, VersionPattern: `(?m)^SYNTHETIC version ([A-Za-z0-9.+-]+)$`}
}
func TestConfiguredBinaryExecutionAndEvidence(t *testing.T) {
	t.Setenv("BEARINGS_PROBE_TEST_SECRET", "must-not-be-inherited")
	for _, mode := range []string{"probe-normal", "probe-stderr"} {
		p := testProbe(t, mode)
		c, err := runBinaryProbe(context.Background(), p, "x86_64")
		if err != nil {
			t.Fatal(mode, err)
		}
		data, _ := os.ReadFile(p.Executable)
		sum := sha256.Sum256(data)
		if c.Key != "binary:custom-tool:x86_64" || c.Binary.SHA256 != hex.EncodeToString(sum[:]) || c.Binary.Path != p.Executable || c.Manager != "binary" {
			t.Fatal("incorrect fingerprint or slot", c)
		}
		if (mode == "probe-normal" && c.Version != "1.2.3") || (mode == "probe-stderr" && c.Version != "2.0.0-build7") {
			t.Fatal(c.Version)
		}
	}
	for _, mode := range []string{"probe-ambiguous", "probe-failed", "probe-output", "probe-sleep"} {
		ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
		started := time.Now()
		_, err := runBinaryProbe(ctx, testProbe(t, mode), "x86_64")
		cancel()
		if err == nil || time.Since(started) > 3*time.Second {
			t.Fatal("failed/ambiguous/unbounded probe accepted", mode, err)
		}
	}
}
func TestBinaryConfigurationAndScopeRefusal(t *testing.T) {
	p := testProbe(t, "probe-normal")
	cfg := binaryConfiguration{Schema: "bearings.binary-probes.v1", Binaries: []binaryProbe{p}}
	path := filepath.Join(t.TempDir(), "probes.json")
	save := func(v binaryConfiguration) {
		raw, _ := json.Marshal(v)
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	save(cfg)
	if _, err := loadBinaryProbes(path); err != nil {
		t.Fatal(err)
	}
	if os.Geteuid() != 0 {
		r, err := collectConfigured(false, nil, "", path)
		if err != nil || r.Scope != "configured-binaries" || r.Complete || len(r.Components) != 1 {
			t.Fatal(r, err)
		}
	} else {
		if _, err := collectBinaries(path); err == nil {
			t.Fatal("root probe execution accepted")
		}
	}
	if _, err := collectConfigured(true, nil, "", path); err == nil {
		t.Fatal("mixed scopes accepted")
	}
	for _, bad := range []string{
		`{"schema":"bearings.binary-probes.v1","schema":"bearings.binary-probes.v1","binaries":[]}`,
		`{"schema":"bearings.binary-probes.v1","binaries":[],"command":"arbitrary"}`,
	} {
		os.WriteFile(path, []byte(bad), 0600)
		if _, err := loadBinaryProbes(path); err == nil {
			t.Fatal("invalid configuration accepted")
		}
	}
	for _, mutate := range []func(*binaryConfiguration){
		func(c *binaryConfiguration) { c.Binaries = append(c.Binaries, c.Binaries[0]) },
		func(c *binaryConfiguration) { c.Binaries[0].VersionPattern = "(one)(two)" },
		func(c *binaryConfiguration) { c.Binaries[0].Executable = "relative" },
		func(c *binaryConfiguration) { c.Binaries[0].Args = []string{"bad\narg"} },
		func(c *binaryConfiguration) { c.Binaries[0].Args = nil },
	} {
		copy := binaryConfiguration{Schema: cfg.Schema, Binaries: append([]binaryProbe{}, cfg.Binaries...)}
		mutate(&copy)
		save(copy)
		if _, err := loadBinaryProbes(path); err == nil {
			t.Fatal("unsafe configuration accepted")
		}
	}
	save(cfg)
	os.Chmod(path, 0666)
	if _, err := loadBinaryProbes(path); err == nil {
		t.Fatal("shared-writable configuration accepted")
	}
}
func TestBinaryPathAndScriptRefusal(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "tool")
	os.WriteFile(path, []byte("#!/bin/sh\necho 1.2.3\n"), 0700)
	p := testProbe(t, "probe-normal")
	p.Executable = path
	if _, err := runBinaryProbe(context.Background(), p, "x86_64"); err == nil {
		t.Fatal("script executed")
	}
	link := filepath.Join(dir, "link")
	os.Symlink(p.Executable, link)
	if _, err := openProbeFile(link, 65536); err == nil {
		t.Fatal("symlink accepted")
	}
	os.Chmod(dir, 0777)
	if _, err := openProbeFile(path, 65536); err == nil {
		t.Fatal("shared-writable parent accepted")
	}
}

func TestBinaryChangedWhileProbingIsRejected(t *testing.T) {
	_, err := runBinaryProbe(context.Background(), testProbe(t, "probe-replace"), "x86_64")
	if err == nil || !strings.Contains(err.Error(), "changed") {
		t.Fatal("replaced executable was not detected", err)
	}
}
