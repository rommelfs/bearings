// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

type configuration struct {
	URL               string `json:"url"`
	DeviceID          string `json:"device_id"`
	Counter           int64  `json:"counter"`
	CAFile            string `json:"ca_file"`
	EnrollmentID      string `json:"enrollment_id"`
	EnrollmentRequest string `json:"enrollment_request"`
	ExpiresAt         string `json:"expires_at"`
}
type store struct {
	dir    string
	lock   *os.File
	key    ed25519.PrivateKey
	config configuration
}

func safeRead(path string, limit int64) ([]byte, error) {
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	stat, ok := st.Sys().(*syscall.Stat_t)
	if !st.Mode().IsRegular() || !ok || stat.Uid != uint32(os.Geteuid()) || st.Mode().Perm()&0077 != 0 {
		return nil, errors.New("private files must be owned by this user and have mode 0600")
	}
	raw, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil || int64(len(raw)) > limit {
		return nil, errors.New("private file exceeds its size limit")
	}
	return raw, nil
}
func syncDir(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}
func writePrivate(path string, raw []byte) error {
	f, err := os.CreateTemp(filepath.Dir(path), ".bearings-*")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(raw)
	}
	if err == nil {
		err = f.Sync()
	}
	cerr := f.Close()
	if err == nil {
		err = cerr
	}
	if err != nil {
		return err
	}
	if err = os.Rename(name, path); err != nil {
		return err
	}
	return syncDir(filepath.Dir(path))
}
func openStore(dir string, initialize bool) (*store, error) {
	abs, err := filepath.Abs(dir)
	if err != nil {
		return nil, err
	}
	if initialize {
		if err = os.MkdirAll(abs, 0700); err != nil {
			return nil, err
		}
	}
	st, err := os.Lstat(abs)
	if err != nil {
		return nil, err
	}
	stat, ok := st.Sys().(*syscall.Stat_t)
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || !ok || stat.Uid != uint32(os.Geteuid()) || st.Mode().Perm()&0077 != 0 {
		return nil, errors.New("state directory must be a private, owned directory (0700), not a symlink")
	}
	fd, err := syscall.Open(filepath.Join(abs, "lock"), syscall.O_CREAT|syscall.O_RDWR|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
	if err != nil {
		return nil, err
	}
	lock := os.NewFile(uintptr(fd), "lock")
	if err = syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		lock.Close()
		return nil, errors.New("another client operation holds the state lock")
	}
	s := &store{dir: abs, lock: lock}
	success := false
	defer func() {
		if !success {
			s.close()
		}
	}()
	keyPath := filepath.Join(abs, "key")
	if _, err = os.Lstat(keyPath); os.IsNotExist(err) && initialize {
		_, key, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			return nil, err
		}
		if err = writePrivate(keyPath, key.Seed()); err != nil {
			return nil, err
		}
	}
	seed, err := safeRead(keyPath, 32)
	if err != nil || len(seed) != 32 {
		return nil, errors.New("missing or unsafe device key; run init in a fresh private state directory")
	}
	s.key = ed25519.NewKeyFromSeed(seed)
	configPath := filepath.Join(abs, "config.json")
	if _, err = os.Lstat(configPath); err == nil {
		raw, err := safeRead(configPath, 8192)
		if err != nil {
			return nil, err
		}
		if err = decode(raw, &s.config); err != nil {
			return nil, err
		}
	} else if !os.IsNotExist(err) {
		return nil, err
	}
	queue := filepath.Join(abs, "outbox")
	if err = os.Mkdir(queue, 0700); err != nil && !os.IsExist(err) {
		return nil, err
	}
	q, err := os.Lstat(queue)
	if err != nil || !q.IsDir() || q.Mode().Perm()&0077 != 0 {
		return nil, errors.New("unsafe outbox directory")
	}
	success = true
	return s, nil
}
func (s *store) close() {
	if s.lock != nil {
		syscall.Flock(int(s.lock.Fd()), syscall.LOCK_UN)
		s.lock.Close()
	}
}
func (s *store) save() error {
	raw, err := json.Marshal(s.config)
	if err != nil {
		return err
	}
	return writePrivate(filepath.Join(s.dir, "config.json"), raw)
}
func (s *store) public() string {
	return base64.StdEncoding.EncodeToString(s.key.Public().(ed25519.PublicKey))
}
func (s *store) queue() ([]string, int64, error) {
	entries, err := os.ReadDir(filepath.Join(s.dir, "outbox"))
	if err != nil {
		return nil, 0, err
	}
	var names []string
	var size int64
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".bearings-") {
			continue
		}
		if entry.IsDir() || entry.Type()&os.ModeSymlink != 0 || !strings.HasSuffix(entry.Name(), ".json") {
			return nil, 0, errors.New("unexpected outbox entry; inspect local state")
		}
		st, err := entry.Info()
		if err != nil {
			return nil, 0, err
		}
		size += st.Size()
		names = append(names, entry.Name())
	}
	sort.Strings(names)
	return names, size, nil
}
func (s *store) enqueue(r *report) error {
	names, size, err := s.queue()
	if err != nil {
		return err
	}
	if len(names) >= 64 || size >= 64*maxBody {
		return errors.New("outbox full; no observations silently discarded")
	}
	if s.config.Counter >= 1<<63-2 {
		return errors.New("sequence exhausted; explicit reenrollment required")
	}
	s.config.Counter++
	r.Sequence = s.config.Counter
	raw, err := json.Marshal(r)
	if err != nil {
		return err
	}
	if len(raw) > maxBody {
		return errors.New("report exceeds one-megabyte contract; narrow the explicit package scope")
	}
	if err = s.save(); err != nil {
		return err
	}
	return writePrivate(filepath.Join(s.dir, "outbox", fmt.Sprintf("%020d_%s.json", r.Sequence, r.ReportID)), raw)
}
