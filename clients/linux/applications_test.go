// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestMISPManifestVersionAndFingerprint(t *testing.T) {
	path := filepath.Join(t.TempDir(), "VERSION.json")
	p := applicationProbe{ID: "misp-main", Method: "misp-version-json", Path: path}
	for _, raw := range []string{`{"major":2,"minor":5,"hotfix":51}`, `{"major":2,"minor":5,"hotfix":52}`} {
		if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		c, err := mispManifest(p)
		if err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256([]byte(raw))
		if c.Manager != "manifest" || c.Name != "MISP" || c.Manifest.Method != "misp-version-json" || c.Manifest.SHA256 != hex.EncodeToString(sum[:]) || c.Manifest.Path != path || !strings.HasPrefix(c.Version, "2.5.") {
			t.Fatalf("bad application evidence: %+v", c)
		}
	}
}
func TestMISPManifestRejectsAmbiguousUnboundedOrNonVersionContent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "VERSION.json")
	p := applicationProbe{ID: "misp", Method: "misp-version-json", Path: path}
	for _, raw := range []string{`{"major":2,"major":3,"minor":5,"hotfix":1}`, `{"major":2,"minor":5,"hotfix":null}`, `{"major":2,"minor":5,"hotfix":"execute-me"}`, `{"major":2,"minor":5,"hotfix":-1}`, `{"major":2,"minor":5,"hotfix":1.5}`, `{"major":2,"minor":5,"hotfix":9999999}`, `{"major":2,"minor":5,"hotfix":1,"password":"never-report"}`, strings.Repeat(" ", 4097)} {
		os.WriteFile(path, []byte(raw), 0600)
		if _, err := mispManifest(p); err == nil {
			t.Fatalf("accepted unsupported manifest: %q", raw[:min(len(raw), 80)])
		}
	}
}
func TestMISPManifestNeverFollowsSymlinksOrBlocksOnSpecialFiles(t *testing.T) {
	dir := t.TempDir()
	real := filepath.Join(dir, "real")
	os.Mkdir(real, 0700)
	os.WriteFile(filepath.Join(real, "VERSION.json"), []byte(`{"major":2,"minor":5,"hotfix":1}`), 0600)
	link := filepath.Join(dir, "link")
	os.Symlink(real, link)
	for _, path := range []string{filepath.Join(link, "VERSION.json"), real + "/../real/VERSION.json"} {
		if _, err := openManifestFile(path); err == nil {
			t.Fatal("accepted redirected path")
		}
	}
	file := filepath.Join(dir, "VERSION.json")
	os.Symlink(filepath.Join(real, "VERSION.json"), file)
	if _, err := openManifestFile(file); err == nil {
		t.Fatal("accepted manifest symlink")
	}
	os.Remove(file)
	syscall.Mkfifo(file, 0600)
	if _, err := openManifestFile(file); err == nil {
		t.Fatal("accepted fifo")
	}
}
func TestApplicationProbeConfigurationIsExplicitAndReadOnly(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "VERSION.json")
	config := filepath.Join(dir, "probes.json")
	os.WriteFile(path, []byte(`{"major":2,"minor":5,"hotfix":52}`), 0600)
	raw := `{"schema":"bearings.application-probes.v1","applications":[{"id":"misp-main","method":"misp-version-json","path":"` + path + `"}]}`
	os.WriteFile(config, []byte(raw), 0600)
	got, _ := collectApplications(config)
	if len(got) != 1 || got[0].Version != "2.5.52" {
		t.Fatalf("bad configured collection: %+v", got)
	}
	os.WriteFile(config, []byte(strings.Replace(raw, "misp-version-json", "shell-command", 1)), 0600)
	if _, err := applicationProbes(config); err == nil {
		t.Fatal("accepted an executable method")
	}
	os.WriteFile(config, []byte(raw), 0666)
	os.Chmod(config, 0666)
	if _, err := applicationProbes(config); err == nil {
		t.Fatal("accepted shared-writable configuration")
	}
}

func TestGenericVersionFileAndJSONProfiles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "release.txt")
	p := applicationProbe{ID: "app-one", Method: "file-regex", Name: "Example App", Identifier: "cpe:2.3:a:example:app:*:*:*:*:*:*:*:*", Path: path, VersionPattern: `(?m)^Version: ([0-9]+\.[0-9]+\.[0-9]+)$`}
	os.WriteFile(path, []byte("Version: 3.2.1\nnon-version data stays local\n"), 0600)
	c, err := genericApplication(context.Background(), p)
	if err != nil || c.Version != "3.2.1" {
		t.Fatalf("generic file: %+v %v", c, err)
	}
	os.WriteFile(path, []byte("Version: 3.2.1\nVersion: 3.2.2\n"), 0600)
	if _, err = genericApplication(context.Background(), p); err == nil {
		t.Fatal("accepted ambiguous file versions")
	}
	p.Method = "json-fields"
	p.Fields = []string{"release.major", "release.minor", "release.patch"}
	p.VersionPattern = `^([0-9]+\.[0-9]+\.[0-9]+)$`
	os.WriteFile(path, []byte(`{"release":{"major":3,"minor":2,"patch":4},"not_reported":"private"}`), 0600)
	c, err = genericApplication(context.Background(), p)
	if err != nil || c.Version != "3.2.4" {
		t.Fatalf("generic JSON: %+v %v", c, err)
	}
	os.WriteFile(path, []byte(`{"release":{"major":3,"minor":2,"patch":4,"patch":5}}`), 0600)
	if _, err = genericApplication(context.Background(), p); err == nil {
		t.Fatal("accepted duplicate JSON metadata")
	}
	p.VersionPattern = `(.*)(.*)`
	if validApplicationProbe(p) {
		t.Fatal("accepted ambiguous pattern captures")
	}
	p.VersionPattern = `^([0-9.]+)$`
	p.Identifier = "https://private-endpoint.invalid"
	if validApplicationProbe(p) {
		t.Fatal("accepted endpoint as product identity")
	}
}

func TestGitApplicationChild(t *testing.T) {
	path := os.Getenv("BEARINGS_TEST_GIT_PATH")
	if path == "" {
		return
	}
	p := applicationProbe{ID: "git-app", Method: "git-tag", Name: "Git App", Path: path, VersionPattern: `(?m)^v([0-9]+\.[0-9]+\.[0-9]+)$`}
	c, err := genericApplication(context.Background(), p)
	if os.Getenv("BEARINGS_TEST_GIT_DIRTY") == "1" {
		if err == nil {
			t.Fatal("asserted a release from a dirty tree")
		}
		return
	}
	if err != nil || c.Version != "1.2.3" || len(c.Manifest.Commit) != 40 || c.Manifest.Dirty == nil || *c.Manifest.Dirty {
		t.Fatalf("Git profile failed: %+v %v", c, err)
	}
}
func TestGitProfileReportsExactTagAndDisablesRepositoryHelpers(t *testing.T) {
	dir := t.TempDir()
	os.Chmod(filepath.Dir(dir), 0755)
	os.Chmod(dir, 0755)
	repo := filepath.Join(dir, "repo")
	os.Mkdir(repo, 0755)
	git := func(args ...string) {
		cmd := exec.Command("/usr/bin/git", append([]string{"-C", repo}, args...)...)
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("fixture Git: %v %s", err, out)
		}
	}
	git("init")
	os.WriteFile(filepath.Join(repo, "tracked"), []byte("release"), 0644)
	git("add", "tracked")
	git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
	git("tag", "v1.2.3")
	markerDir := filepath.Join(dir, "markers")
	os.Mkdir(markerDir, 0777)
	os.Chmod(markerDir, 0777)
	sentinel := filepath.Join(markerDir, "must-not-exist")
	helper := filepath.Join(dir, "helper.sh")
	os.WriteFile(helper, []byte("#!/bin/sh\ntouch "+sentinel+"\n"), 0755)
	git("config", "core.fsmonitor", helper)
	exe, _ := os.Executable()
	raw, _ := os.ReadFile(exe)
	child := filepath.Join(dir, "probe-test")
	os.WriteFile(child, raw, 0755)
	for _, dirty := range []bool{false, true} {
		if dirty {
			os.WriteFile(filepath.Join(repo, "tracked"), []byte("modified"), 0644)
		}
		cmd := exec.Command(child, "-test.run=^TestGitApplicationChild$")
		cmd.Env = []string{"BEARINGS_TEST_GIT_PATH=" + repo}
		if dirty {
			cmd.Env = append(cmd.Env, "BEARINGS_TEST_GIT_DIRTY=1")
		}
		if os.Geteuid() == 0 {
			cmd.SysProcAttr = &syscall.SysProcAttr{Credential: &syscall.Credential{Uid: 65534, Gid: 65534}}
		}
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("unprivileged Git probe: %v %s", err, out)
		}
	}
	if _, err := os.Stat(sentinel); err == nil {
		t.Fatal("Git executed a repository-configured helper")
	}
}

func TestBundledApplicationProfileExampleHasValidMethodsAndNormalizers(t *testing.T) {
	raw, err := os.ReadFile("examples/applications.json")
	if err != nil {
		t.Fatal(err)
	}
	var cfg applicationConfiguration
	if decode(raw, &cfg) != nil || cfg.Schema != "bearings.application-probes.v1" {
		t.Fatal("invalid example profile document")
	}
	for _, p := range cfg.Applications {
		if !validApplicationProbe(p) {
			t.Fatalf("invalid example profile %s", p.ID)
		}
	}
}

func TestContributedApplicationProfilesValidateAsDataOnly(t *testing.T) {
	paths, err := filepath.Glob("profiles/*.json")
	if err != nil || len(paths) == 0 {
		t.Fatal("profile library missing")
	}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var doc struct {
			Schema      string           `json:"schema"`
			Title       string           `json:"title"`
			Description string           `json:"description,omitempty"`
			License     string           `json:"license"`
			References  []string         `json:"references"`
			Profile     applicationProbe `json:"profile"`
		}
		if decode(raw, &doc) != nil || doc.Schema != "bearings.application-profile.v1" || doc.Title == "" || doc.License != "AGPL-3.0-or-later" || !validApplicationProbe(doc.Profile) {
			t.Fatalf("invalid contributed profile %s", path)
		}
	}
}

func TestValidateApplicationsRequiresAnExplicitConfiguration(t *testing.T) {
	if err := run([]string{"validate-applications", "--config", filepath.Join(t.TempDir(), "missing.json")}); err == nil {
		t.Fatal("validator fell back to local application discovery")
	}
}
