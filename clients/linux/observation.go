// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"os/exec"
	"time"
)

type operatingSystem struct {
	ID           string `json:"id"`
	Version      string `json:"version"`
	Architecture string `json:"architecture"`
	Kernel       string `json:"kernel"`
	Build        string `json:"build,omitempty"`
	KernelScope  string `json:"kernel_scope,omitempty"`
	RebootHint   string `json:"reboot_hint"`
}
type packageSource struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}
type component struct {
	Manifest     *manifestEvidence `json:"manifest,omitempty"`
	Source       *packageSource    `json:"source,omitempty"`
	Binary       *binaryEvidence   `json:"binary,omitempty"`
	Key          string            `json:"key"`
	Manager      string            `json:"manager"`
	Name         string            `json:"name"`
	Version      string            `json:"version"`
	Architecture string            `json:"architecture"`
}
type service struct {
	Name     string `json:"name"`
	State    string `json:"state"`
	Coverage string `json:"coverage"`
}
type report struct {
	Applications []component     `json:"applications,omitempty"`
	Host         *declaredHost   `json:"host,omitempty"`
	Schema       string          `json:"schema"`
	ReportID     string          `json:"report_id"`
	Sequence     int64           `json:"sequence"`
	ObservedAt   string          `json:"observed_at"`
	Scope        string          `json:"scope"`
	Complete     bool            `json:"complete"`
	OS           operatingSystem `json:"os"`
	Components   []component     `json:"components"`
	Services     []service       `json:"services"`
	Gaps         *[]string       `json:"gaps,omitempty"`
}
type cappedBuffer struct {
	bytes.Buffer
	limit int
}

func (b *cappedBuffer) Write(p []byte) (int, error) {
	if b.Len()+len(p) > b.limit {
		return 0, errors.New("collector output exceeded its safety limit")
	}
	return b.Buffer.Write(p)
}
func command(path string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, args...)
	cmd.Env = []string{"PATH=/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL=C", "LANG=C"}
	output := &cappedBuffer{limit: 4 * 1024 * 1024}
	stderr := &cappedBuffer{limit: 8192}
	cmd.Stdout = output
	cmd.Stderr = stderr
	if err := cmd.Run(); err != nil {
		return nil, errors.New("read-only collector failed or timed out; no complete snapshot produced")
	}
	return output.Bytes(), nil
}

type manifestEvidence struct {
	ProfileSHA256 string `json:"profile_sha256,omitempty"`
	Identifier    string `json:"identifier,omitempty"`
	Commit        string `json:"commit,omitempty"`
	Dirty         *bool  `json:"dirty,omitempty"`
	Method        string `json:"method"`
	Path          string `json:"path"`
	SHA256        string `json:"sha256"`
}
type binaryEvidence struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

func readBounded(path string, max int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, max+1))
	if err != nil || int64(len(raw)) > max {
		return nil, errors.New("collector input exceeds safety limit")
	}
	return raw, nil
}
