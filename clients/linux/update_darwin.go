// SPDX-License-Identifier: AGPL-3.0-or-later

package main

import (
	"bytes"
	"crypto/ed25519"
	"debug/macho"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
)

const macDownloads = "/downloads/macos/"

var macReleaseKey, macSequence string

func fetchMac(client *http.Client, server, name string, limit int) ([]byte, error) {
	response, err := client.Get(server + macDownloads + name)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("client download returned HTTP %d", response.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, int64(limit)+1))
	if err != nil || len(raw) > limit {
		return nil, errors.New("client download exceeds its size limit or failed")
	}
	return raw, nil
}

func (m macInstall) update(s *store) error {
	if err := ready(s); err != nil {
		return err
	}
	key, err := base64.StdEncoding.Strict().DecodeString(macReleaseKey)
	if err != nil || len(key) != ed25519.PublicKeySize || s.config.URL != macServer {
		return errors.New("this client has no matching pinned macOS update publisher")
	}
	compiled, err := strconv.ParseInt(macSequence, 10, 64)
	if err != nil || compiled < 1 {
		return errors.New("invalid embedded macOS release sequence")
	}
	counter := filepath.Join(s.dir, "update-sequence")
	minimum := compiled
	if previous, err := safeRead(counter, 32); err == nil {
		n, err := strconv.ParseInt(string(previous), 10, 64)
		if err != nil || n < 1 {
			return errors.New("invalid local update sequence")
		}
		minimum = max(minimum, n)
	} else if !os.IsNotExist(err) {
		return err
	}
	if _, err := os.Lstat(m.binary); err != nil {
		return errors.New("install the app before checking for client updates")
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return err
	}
	defer client.CloseIdleConnections()
	raw, err := fetchMac(client, macServer, "update.json", 65536)
	if err != nil {
		return err
	}
	release, err := verifyMacRelease(raw, macServer, key)
	if err != nil {
		return err
	}
	if release.Sequence < minimum {
		return errors.New("older macOS client release refused")
	}
	if release.Sequence == compiled {
		return nil
	}
	asset := release.Assets[runtime.GOARCH]
	binary, err := fetchMac(client, macServer, "bearings-macos-"+runtime.GOARCH, asset.Size)
	if err != nil {
		return err
	}
	if len(binary) != asset.Size || digest(binary) != asset.Hash {
		return errors.New("macOS client download differs from the signed manifest")
	}
	image, err := macho.NewFile(bytes.NewReader(binary))
	if err != nil {
		return errors.New("invalid macOS executable")
	}
	defer image.Close()
	expected := macho.CpuAmd64
	if runtime.GOARCH == "arm64" {
		expected = macho.CpuArm64
	}
	if image.Cpu != expected || image.Type != macho.TypeExec {
		return errors.New("macOS executable has the wrong architecture or image type")
	}
	// Remember the signed sequence before replacing the executable. If replacement
	// fails, the existing binary can still retry the same release.
	if err := writePrivate(counter, []byte(strconv.FormatInt(release.Sequence, 10))); err != nil {
		return err
	}
	return replaceBinary(m.binary, bytes.NewReader(binary), maxMacBinary)
}

func replaceBinary(path string, source io.Reader, maxBytes int64) error {
	f, err := os.CreateTemp(filepath.Dir(path), ".bearings-macos-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	n, err := io.Copy(f, io.LimitReader(source, maxBytes+1))
	if err == nil && (n == 0 || n > maxBytes) {
		err = errors.New("invalid macOS executable size")
	}
	if err == nil {
		err = f.Chmod(0700)
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err = errors.Join(err, closeErr); err != nil {
		return err
	}
	if err := os.Rename(f.Name(), path); err != nil {
		return err
	}
	return syncDir(filepath.Dir(path))
}
