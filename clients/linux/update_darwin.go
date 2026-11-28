// SPDX-License-Identifier: AGPL-3.0-or-later

package main

import (
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
	if err := verifyMacBundle(m.app); err != nil {
		return err
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
	release, err := verifyMacRelease(raw, macServer, key, macAppleTeam != "")
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
	raw, err = fetchMac(client, macServer, "bearings-macos-"+runtime.GOARCH+".zip", asset.Size)
	if err != nil {
		return err
	}
	if len(raw) != asset.Size || digest(raw) != asset.Hash {
		return errors.New("macOS app download differs from the signed manifest")
	}
	if err := validateMacArchive(raw, macAppleTeam != ""); err != nil {
		return err
	}
	stage, err := os.MkdirTemp(filepath.Dir(m.app), ".bearings-update-*")
	if err != nil {
		return err
	}
	// Keep the previous bundle if rollback cannot restore its original path.
	defer func() {
		if _, err := os.Lstat(m.app); err == nil {
			_ = os.RemoveAll(stage)
		}
	}()
	archive := filepath.Join(stage, "update.zip")
	if err := os.WriteFile(archive, raw, 0600); err != nil {
		return err
	}
	if err := appleTool("/usr/bin/ditto", "-x", "-k", archive, stage); err != nil {
		return err
	}
	candidate := filepath.Join(stage, "Bearings.app")
	if err := verifyMacBundle(candidate); err != nil {
		return err
	}
	image, err := macho.Open(filepath.Join(candidate, "Contents", "MacOS", "bearings-macos"))
	if err != nil {
		return err
	}
	defer image.Close()
	expected := macho.CpuAmd64
	if runtime.GOARCH == "arm64" {
		expected = macho.CpuArm64
	}
	if image.Cpu != expected || image.Type != macho.TypeExec {
		return errors.New("macOS update executable has the wrong architecture or image type")
	}
	// Preserve an existing local ad-hoc seal on an update authenticated by
	// the configured Bearings publisher. macOS still applies its launch policy.
	if macAppleTeam == "" {
		if _, err := os.Lstat(macResourceSeal(m.app)); err == nil {
			if err := appleTool("/usr/bin/codesign", "--force", "--sign", "-", candidate); err != nil {
				return err
			}
			if err := verifyAdHocMacSeal(candidate); err != nil {
				return err
			}
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	if err := writePrivate(counter, []byte(strconv.FormatInt(release.Sequence, 10))); err != nil {
		return err
	}
	return m.activateBundle(candidate, stage)
}
