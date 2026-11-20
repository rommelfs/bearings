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
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"
)

type binaryEvidence struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type binaryProbe struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	Executable     string   `json:"executable"`
	Args           []string `json:"args"`
	VersionPattern string   `json:"version_pattern"`
}
type binaryConfiguration struct {
	Schema   string        `json:"schema"`
	Binaries []binaryProbe `json:"binaries"`
}

var probeID = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{0,63}$`)
var binaryVersion = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._+~:()/-]{0,119}$`)

// Only administrator/collector-controlled paths. Root-owned sticky directories
// are safe ancestors of a private owned directory, not probe-file locations.
// Rootless containers may map the system filesystem owner to a nonzero UID.
// That owner can already replace the trusted OS loader/libraries.
func probeSystemOwner(uid uint32) bool {
	root, err := os.Stat("/")
	if err != nil || root.Mode().Perm()&0022 != 0 {
		return false
	}
	owner, ok := root.Sys().(*syscall.Stat_t)
	return uid == 0 || (ok && owner.Uid == uid)
}

func trustedProbePath(path string) error {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || len(path) > 1024 || strings.ContainsFunc(path, func(c rune) bool { return c < 32 || c == 127 }) {
		return errors.New("use a canonical absolute probe path")
	}
	current := path
	for {
		st, err := os.Lstat(current)
		if err != nil {
			return errors.New("probe path is unavailable")
		}
		owner, ok := st.Sys().(*syscall.Stat_t)
		sticky := current != path && st.IsDir() && st.Mode()&os.ModeSticky != 0 && ok && probeSystemOwner(owner.Uid)
		if !ok || (!probeSystemOwner(owner.Uid) && owner.Uid != uint32(os.Geteuid())) || st.Mode()&os.ModeSymlink != 0 || (st.Mode().Perm()&0022 != 0 && !sticky) || st.Mode()&(os.ModeSetuid|os.ModeSetgid) != 0 {
			return errors.New("probe paths must be owned, non-shared-writable and free of symlinks/set-ID bits")
		}
		if current == path {
			if !st.Mode().IsRegular() {
				return errors.New("probe must be a regular file")
			}
		} else if !st.IsDir() {
			return errors.New("probe parent must be a directory")
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return nil
}
func openProbeFile(path string, limit int64) (*os.File, error) {
	if err := trustedProbePath(path); err != nil {
		return nil, err
	}
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, errors.New("cannot open approved probe file")
	}
	f := os.NewFile(uintptr(fd), path)
	st, err := f.Stat()
	if err != nil || !st.Mode().IsRegular() || st.Size() > limit {
		f.Close()
		return nil, errors.New("probe file is not regular or exceeds its limit")
	}
	owner, ok := st.Sys().(*syscall.Stat_t)
	if !ok || (!probeSystemOwner(owner.Uid) && owner.Uid != uint32(os.Geteuid())) || st.Mode().Perm()&0022 != 0 || st.Mode()&(os.ModeSetuid|os.ModeSetgid) != 0 {
		f.Close()
		return nil, errors.New("unsafe approved probe file")
	}
	return f, nil
}
func uniqueProbeJSON(d *json.Decoder, depth int) error {
	if depth > 6 {
		return errors.New("probe configuration too deeply nested")
	}
	token, err := d.Token()
	if err != nil {
		return err
	}
	delimiter, ok := token.(json.Delim)
	if !ok {
		return nil
	}
	switch delimiter {
	case '{':
		seen := map[string]bool{}
		for d.More() {
			key, err := d.Token()
			if err != nil {
				return err
			}
			name, ok := key.(string)
			if !ok || seen[name] {
				return errors.New("duplicate configuration field")
			}
			seen[name] = true
			if err = uniqueProbeJSON(d, depth+1); err != nil {
				return err
			}
		}
	case '[':
		for d.More() {
			if err = uniqueProbeJSON(d, depth+1); err != nil {
				return err
			}
		}
	default:
		return errors.New("invalid configuration structure")
	}
	_, err = d.Token()
	return err
}
func loadBinaryProbes(path string) ([]binaryProbe, error) {
	f, err := openProbeFile(path, 65536)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, 65537))
	if err != nil || len(raw) > 65536 {
		return nil, errors.New("probe configuration exceeds limit")
	}
	if err = uniqueProbeJSON(json.NewDecoder(bytes.NewReader(raw)), 0); err != nil {
		return nil, errors.New("invalid or duplicate probe configuration fields")
	}
	var cfg binaryConfiguration
	if err = decode(raw, &cfg); err != nil || cfg.Schema != "bearings.binary-probes.v1" || len(cfg.Binaries) < 1 || len(cfg.Binaries) > 16 {
		return nil, errors.New("use 1–16 explicit binary probes in bearings.binary-probes.v1")
	}
	seen := map[string]bool{}
	for _, p := range cfg.Binaries {
		if !probeID.MatchString(p.ID) || seen[p.ID] || !packageName.MatchString(p.Name) || len(p.Args) < 1 || len(p.Args) > 16 || len(p.VersionPattern) < 1 || len(p.VersionPattern) > 512 {
			return nil, errors.New("invalid or duplicate binary probe")
		}
		seen[p.ID] = true
		if err = trustedProbePath(p.Executable); err != nil {
			return nil, err
		}
		for _, arg := range p.Args {
			if len(arg) > 256 || strings.ContainsAny(arg, "\x00\r\n") {
				return nil, errors.New("invalid fixed probe argument")
			}
		}
		pattern, err := regexp.Compile(p.VersionPattern)
		if err != nil || pattern.NumSubexp() != 1 {
			return nil, errors.New("version pattern must have exactly one capture group")
		}
	}
	return cfg.Binaries, nil
}

type probeOutput struct {
	sync.Mutex
	data     []byte
	exceeded bool
}

func (b *probeOutput) Write(p []byte) (int, error) {
	b.Lock()
	defer b.Unlock()
	if len(b.data)+len(p) > 16384 {
		b.exceeded = true
		return 0, errors.New("probe output limit")
	}
	b.data = append(b.data, p...)
	return len(p), nil
}
func unchangedProbe(a, b os.FileInfo) bool {
	x, ok := a.Sys().(*syscall.Stat_t)
	y, ok2 := b.Sys().(*syscall.Stat_t)
	return ok && ok2 && os.SameFile(a, b) && x.Size == y.Size && x.Mtim == y.Mtim && x.Ctim == y.Ctim
}
func runBinaryProbe(ctx context.Context, p binaryProbe, architecture string) (component, error) {
	f, err := openProbeFile(p.Executable, 256*1024*1024)
	if err != nil {
		return component{}, err
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil || before.Mode().Perm()&0111 == 0 {
		return component{}, errors.New("probe executable unavailable")
	}
	magic := make([]byte, 4)
	if _, err = io.ReadFull(f, magic); err != nil || !bytes.Equal(magic, []byte{0x7f, 'E', 'L', 'F'}) {
		return component{}, errors.New("version probes support native ELF executables, not scripts")
	}
	if _, err = f.Seek(0, io.SeekStart); err != nil {
		return component{}, err
	}
	h := sha256.New()
	buffer := make([]byte, 65536)
	for {
		if ctx.Err() != nil {
			return component{}, errors.New("binary probe time budget exhausted")
		}
		n, e := f.Read(buffer)
		if n > 0 {
			h.Write(buffer[:n])
		}
		if e == io.EOF {
			break
		}
		if e != nil {
			return component{}, errors.New("cannot fingerprint executable")
		}
	}
	after, err := f.Stat()
	if err != nil || !unchangedProbe(before, after) {
		return component{}, errors.New("executable changed while fingerprinting")
	}
	probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	// Execute the exact descriptor fingerprinted, including during atomic upgrades.
	cmd := exec.CommandContext(probeCtx, "/proc/self/fd/3", p.Args...)
	cmd.Args[0] = p.Executable
	cmd.ExtraFiles = []*os.File{f}
	cmd.Dir = "/"
	cmd.Env = []string{"PATH=/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL=C", "LANG=C"}
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
	cmd.Stderr = out
	// Lock the thread across prctl/fork: prevent set-ID/file-capability elevation.
	runtime.LockOSThread()
	_, _, prctlErr := syscall.RawSyscall6(syscall.SYS_PRCTL, 38, 1, 0, 0, 0, 0)
	if prctlErr == 0 {
		err = cmd.Start()
	} else {
		err = prctlErr
	}
	runtime.UnlockOSThread()
	if err != nil {
		return component{}, errors.New("cannot start non-privileged binary probe")
	}
	defer syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	err = cmd.Wait()
	if err != nil || probeCtx.Err() != nil || out.exceeded {
		return component{}, errors.New("binary version query failed, timed out or exceeded output limit")
	}
	after, err = f.Stat()
	if err != nil || !unchangedProbe(before, after) {
		return component{}, errors.New("executable changed during version query")
	}
	named, pathErr := os.Stat(p.Executable)
	if pathErr != nil || !unchangedProbe(before, named) {
		return component{}, errors.New("executable path changed during version query")
	}
	pattern, _ := regexp.Compile(p.VersionPattern)
	matches := pattern.FindAllStringSubmatch(string(out.data), 2)
	if len(matches) != 1 || !binaryVersion.MatchString(matches[0][1]) {
		return component{}, errors.New("binary version output is absent, ambiguous or unsupported")
	}
	return component{Key: "binary:" + p.ID + ":" + architecture, Manager: "binary", Name: p.Name, Version: matches[0][1], Architecture: architecture, Binary: &binaryEvidence{Path: p.Executable, SHA256: hex.EncodeToString(h.Sum(nil))}}, nil
}
func collectBinaries(path string) (*report, error) {
	if os.Geteuid() == 0 {
		return nil, errors.New("run custom binary probes as a dedicated non-root account")
	}
	probes, err := loadBinaryProbes(path)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	r := &report{Schema: tag, ReportID: newID(), Sequence: 1, Scope: "configured-binaries", Complete: false, OS: operating(), Services: []service{}}
	for _, p := range probes {
		c, err := runBinaryProbe(ctx, p, r.OS.Architecture)
		if err != nil {
			return nil, fmt.Errorf("probe %s failed: %w", p.ID, err)
		}
		r.Components = append(r.Components, c)
	}
	r.ObservedAt = time.Now().UTC().Format(time.RFC3339Nano)
	return r, nil
}
func collectConfigured(inventory bool, selected []string, serviceName, path string) (*report, error) {
	if path == "" {
		return collect(inventory, selected, serviceName)
	}
	if inventory || len(selected) > 0 || serviceName != "" {
		return nil, errors.New("binary probes require their own explicit collection scope")
	}
	return collectBinaries(path)
}
