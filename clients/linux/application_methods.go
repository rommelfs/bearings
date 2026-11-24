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
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"syscall"
	"time"
)

func applicationFile(path string) ([]byte, error) {
	f, err := openManifestFile(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil {
		return nil, errors.New("manifest unavailable")
	}
	raw, err := io.ReadAll(io.LimitReader(f, 65537))
	if err != nil || len(raw) > 65536 {
		return nil, errors.New("manifest exceeds limit")
	}
	after, err := f.Stat()
	if err != nil || !unchangedProbe(before, after) {
		return nil, errors.New("manifest changed while reading")
	}
	again, err := openManifestFile(path)
	if err != nil {
		return nil, err
	}
	defer again.Close()
	named, err := again.Stat()
	if err != nil || !unchangedProbe(before, named) {
		return nil, errors.New("manifest path changed while reading")
	}
	return raw, nil
}
func jsonVersion(raw []byte, fields []string) (string, error) {
	if uniqueProbeJSON(json.NewDecoder(bytes.NewReader(raw)), 0) != nil {
		return "", errors.New("ambiguous JSON manifest")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var root any
	if decoder.Decode(&root) != nil {
		return "", errors.New("invalid JSON manifest")
	}
	if decoder.Decode(new(any)) != io.EOF {
		return "", errors.New("trailing JSON input")
	}
	parts := []string{}
	for _, field := range fields {
		value := root
		for _, key := range strings.Split(field, ".") {
			object, ok := value.(map[string]any)
			if !ok {
				return "", errors.New("missing JSON version field")
			}
			value = object[key]
		}
		switch v := value.(type) {
		case string:
			parts = append(parts, v)
		case json.Number:
			parts = append(parts, string(v))
		default:
			return "", errors.New("version field must be scalar")
		}
	}
	return strings.Join(parts, "."), nil
}

// Fixed read-only Git commands: no pager, hooks, fsmonitor, submodule execution,
// lazy fetching, inherited credentials or optional index writes. Never a shell.
func gitOutput(parent context.Context, path string, args ...string) ([]byte, error) {
	if os.Geteuid() == 0 {
		return nil, errors.New("run Git probes as the dedicated non-root collector")
	}
	f, err := openProbeFile("/usr/bin/git", 256*1024*1024)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	ctx, cancel := context.WithTimeout(parent, 4*time.Second)
	defer cancel()
	prefix := []string{"--no-pager", "--no-optional-locks", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.untrackedCache=false", "-c", "diff.external=", "-c", "core.pager=cat", "-c", "safe.directory=" + path, "-C", path}
	cmd := exec.CommandContext(ctx, "/proc/self/fd/3", append(prefix, args...)...)
	cmd.ExtraFiles = []*os.File{f}
	cmd.Dir = "/"
	cmd.Env = []string{"PATH=/usr/bin:/bin", "LC_ALL=C", "LANG=C", "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_SYSTEM=/dev/null", "GIT_CONFIG_GLOBAL=/dev/null", "GIT_ATTR_NOSYSTEM=1", "GIT_ALLOW_PROTOCOL=", "GIT_NO_LAZY_FETCH=1", "GIT_TERMINAL_PROMPT=0", "GIT_NO_REPLACE_OBJECTS=1"}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGKILL}
	cmd.Cancel = func() error {
		err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		if err == syscall.ESRCH {
			return os.ErrProcessDone
		}
		return err
	}
	cmd.WaitDelay = 250 * time.Millisecond
	out := &probeOutput{}
	cmd.Stdout = out
	cmd.Stderr = &probeOutput{}
	runtime.LockOSThread()
	_, _, e := syscall.RawSyscall6(syscall.SYS_PRCTL, 38, 1, 0, 0, 0, 0)
	if e == 0 {
		err = cmd.Start()
	} else {
		err = e
	}
	runtime.UnlockOSThread()
	if err != nil {
		return nil, errors.New("cannot start approved Git reader")
	}
	defer syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	if cmd.Wait() != nil || ctx.Err() != nil || out.exceeded {
		return nil, errors.New("Git metadata unavailable, oversized or timed out")
	}
	return out.data, nil
}
func genericApplication(ctx context.Context, p applicationProbe) (component, error) {
	if !validApplicationProbe(p) {
		return component{}, errors.New("invalid application profile")
	}
	var raw []byte
	var text, commit string
	var clean *bool
	var err error
	if p.Method == "git-tag" {
		if err = noSymlinkDirectory(p.Path); err != nil {
			return component{}, err
		}
		if err = noSymlinkDirectory(filepath.Join(p.Path, ".git")); err != nil {
			return component{}, errors.New("use a repository with a local .git directory; worktree redirects are not supported")
		}
		before, e := gitOutput(ctx, p.Path, "rev-parse", "--verify", "HEAD")
		if e != nil {
			return component{}, e
		}
		dirty, e := gitOutput(ctx, p.Path, "status", "--porcelain=v1", "--untracked-files=no", "--ignore-submodules=all")
		if e != nil {
			return component{}, e
		}
		if len(dirty) != 0 {
			return component{}, errors.New("tracked Git files are modified; no release version asserted")
		}
		tag, e := gitOutput(ctx, p.Path, "tag", "--points-at", "HEAD")
		if e != nil {
			return component{}, errors.New("Git checkout has no exact release tag")
		}
		after, e := gitOutput(ctx, p.Path, "rev-parse", "--verify", "HEAD")
		if e != nil || !bytes.Equal(before, after) {
			return component{}, errors.New("Git checkout changed while reading")
		}
		finalStatus, e := gitOutput(ctx, p.Path, "status", "--porcelain=v1", "--untracked-files=no", "--ignore-submodules=all")
		if e != nil || len(finalStatus) != 0 {
			return component{}, errors.New("tracked Git files changed while observing")
		}
		commit = strings.TrimSpace(string(after))
		if !regexp.MustCompile(`^[0-9a-f]{40}(?:[0-9a-f]{24})?$`).MatchString(commit) {
			return component{}, errors.New("invalid Git commit identity")
		}
		text = strings.TrimSpace(string(tag))
		raw = append(append([]byte{}, tag...), after...)
		value := false
		clean = &value
	} else {
		raw, err = applicationFile(p.Path)
		if err != nil {
			return component{}, err
		}
		text = string(raw)
		if p.Method == "json-fields" {
			text, err = jsonVersion(raw, p.Fields)
			if err != nil {
				return component{}, err
			}
		}
	}
	pattern, _ := regexp.Compile(p.VersionPattern)
	matches := pattern.FindAllStringSubmatch(text, 2)
	if len(matches) != 1 || !binaryVersion.MatchString(matches[0][1]) {
		return component{}, errors.New("version is absent, ambiguous or unsupported")
	}
	profileRaw, _ := json.Marshal(p)
	profileSHA := sha256.Sum256(profileRaw)
	sum := sha256.Sum256(raw)
	return component{Key: "manifest:" + p.ID + ":all", Manager: "manifest", Name: p.Name, Version: matches[0][1], Architecture: "all", Manifest: &manifestEvidence{ProfileSHA256: hex.EncodeToString(profileSHA[:]), Method: p.Method, Path: p.Path, SHA256: hex.EncodeToString(sum[:]), Identifier: p.Identifier, Commit: commit, Dirty: clean}}, nil
}
func noSymlinkDirectory(path string) error {
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	fd, err := syscall.Open("/", syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_CLOEXEC, 0)
	if err != nil {
		return errors.New("repository root unavailable")
	}
	for _, part := range parts {
		next, e := syscall.Openat(fd, part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		syscall.Close(fd)
		if e != nil {
			return errors.New("repository path unavailable or contains a symlink")
		}
		fd = next
	}
	syscall.Close(fd)
	return nil
}
