// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
)

const maxState = 2*maxBody*maxQueue + maxBody

var writeState = errors.New("could not save protected state; prior pending input retained")
var invalidState = errors.New("protected state is unreadable or invalid; existing key was retained")

func protect(raw []byte, decrypt bool) ([]byte, error) {
	if len(raw) == 0 || len(raw) > maxState {
		return nil, invalidState
	}
	input := windows.DataBlob{Size: uint32(len(raw)), Data: &raw[0]}
	var output windows.DataBlob
	var err error
	if decrypt {
		err = windows.CryptUnprotectData(&input, nil, nil, 0, nil, windows.CRYPTPROTECT_UI_FORBIDDEN, &output)
	} else {
		err = windows.CryptProtectData(&input, nil, nil, 0, nil, windows.CRYPTPROTECT_UI_FORBIDDEN, &output)
	}
	if err != nil {
		return nil, invalidState
	}
	defer windows.LocalFree(windows.Handle(uintptr(unsafe.Pointer(output.Data))))
	if output.Size == 0 || output.Size > maxState || output.Data == nil {
		return nil, invalidState
	}
	return append([]byte(nil), unsafe.Slice(output.Data, output.Size)...), nil
}

func rejectReparse(path string) error {
	for {
		name, err := windows.UTF16PtrFromString(path)
		if err != nil {
			return err
		}
		attr, err := windows.GetFileAttributes(name)
		if err != nil && !errors.Is(err, windows.ERROR_FILE_NOT_FOUND) && !errors.Is(err, windows.ERROR_PATH_NOT_FOUND) {
			return err
		}
		if err == nil && attr&windows.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
			return errors.New("state path contains a reparse point")
		}
		parent := filepath.Dir(path)
		if parent == path {
			return nil
		}
		path = parent
	}
}

type store struct {
	updated bool
	dir     string
	lock    *os.File
	state   state
}

func openStore(dir string, initialize bool) (*store, error) {
	dir, err := filepath.Abs(dir)
	if err != nil || rejectReparse(dir) != nil {
		return nil, errors.New("use a private local state directory without links or junctions")
	}
	if initialize {
		if err := os.MkdirAll(dir, 0700); err != nil {
			return nil, writeState
		}
	}
	lockPath, statePath := filepath.Join(dir, "lock"), filepath.Join(dir, "state.dpapi")
	if rejectReparse(lockPath) != nil || rejectReparse(statePath) != nil {
		return nil, errors.New("state files must be accessible and free of links")
	}
	lock, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, errors.New("could not open private state; run init first and check permissions")
	}
	var offset windows.Overlapped
	if err := windows.LockFileEx(windows.Handle(lock.Fd()), windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset); err != nil {
		lock.Close()
		return nil, errors.New("state is already in use or cannot be locked")
	}
	s := &store{dir: dir, lock: lock}
	if err := s.load(statePath, initialize); err != nil {
		s.close()
		return nil, err
	}
	return s, nil
}

func (s *store) close() { s.lock.Close() }

func (s *store) load(path string, initialize bool) error {
	raw, err := readBounded(path, maxState)
	if errors.Is(err, os.ErrNotExist) && initialize {
		s.state = initialState()
		return s.save()
	}
	if errors.Is(err, os.ErrNotExist) {
		return errors.New("missing state; run init first")
	}
	if err != nil {
		return invalidState
	}
	plain, err := protect(raw, true)
	if err != nil || json.Unmarshal(plain, &s.state) != nil || !s.state.valid() {
		return invalidState
	}
	return nil
}

func (s *store) save() error {
	plain, err := json.Marshal(&s.state)
	if err != nil {
		return writeState
	}
	raw, err := protect(plain, false)
	if err != nil {
		return writeState
	}
	file, err := os.CreateTemp(s.dir, ".bearings-")
	if err != nil {
		return writeState
	}
	defer os.Remove(file.Name())
	_, err = file.Write(raw)
	if err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return writeState
	}
	from, err := windows.UTF16PtrFromString(file.Name())
	if err != nil {
		return writeState
	}
	to, err := windows.UTF16PtrFromString(filepath.Join(s.dir, "state.dpapi"))
	if err != nil || windows.MoveFileEx(from, to, windows.MOVEFILE_REPLACE_EXISTING|windows.MOVEFILE_WRITE_THROUGH) != nil {
		return writeState
	}
	return nil
}

func (s *store) saveBootstrapArchive(attempt rolloutState) error {
	path := filepath.Join(s.dir, ".bearings-bootstrap-"+attempt.RequestID+".dpapi")
	if rejectReparse(path) != nil {
		return errors.New("Cannot verify the bootstrap archive path. Device state retained.")
	}
	plain, err := json.Marshal(attempt)
	if err != nil {
		return writeState
	}
	previous, err := readBounded(path, 8192)
	if err == nil {
		existing, err := protect(previous, true)
		if err != nil || !bytes.Equal(existing, plain) {
			return errors.New("Bootstrap archive already exists with different or unreadable data. Device state retained.")
		}
		return nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return errors.New("Cannot read the bootstrap archive. Device state retained.")
	}
	raw, err := protect(plain, false)
	if err != nil {
		return writeState
	}
	if err := atomicControlFile(path, raw); err != nil {
		return errors.New("Could not write the bootstrap archive. Device state retained.")
	}
	return nil
}

func (s *store) archiveBootstrap() (string, error) {
	archived, err := archiveBootstrap(&s.state, s.save, s.saveBootstrapArchive)
	if err != nil {
		return "", err
	}
	return bootstrapArchiveMessage(archived), nil
}
