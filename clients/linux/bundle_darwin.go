// SPDX-License-Identifier: AGPL-3.0-or-later

package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const macIdentifier = "lu.circl.bearings"

var macAppleTeam string

func appleTool(path string, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, args...)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s could not validate or copy the Bearings app: %w", filepath.Base(path), err)
	}
	return nil
}

func macBundleIdentity(app string) error {
	for _, dir := range []string{app, filepath.Join(app, "Contents"), filepath.Join(app, "Contents", "MacOS")} {
		info, err := os.Lstat(dir)
		if err != nil {
			return err
		}
		if !info.IsDir() {
			return errors.New("unexpected app bundle directory")
		}
	}
	root, err := os.OpenRoot(app)
	if err != nil {
		return err
	}
	defer root.Close()
	info, err := readPlist(root, "Contents/Info.plist")
	if err != nil || info["CFBundleIdentifier"] != macIdentifier || info["CFBundleExecutable"] != "bearings-macos" {
		return errors.New("unexpected Bearings app identity")
	}
	binary, err := root.Lstat("Contents/MacOS/bearings-macos")
	if err != nil || !binary.Mode().IsRegular() || binary.Mode().Perm()&0100 == 0 {
		return errors.New("missing or invalid Bearings executable")
	}
	return nil
}

func macResourceSeal(app string) string {
	return filepath.Join(app, "Contents", "_CodeSignature")
}

func verifyAdHocMacSeal(app string) error {
	seal, err := os.Lstat(macResourceSeal(app))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if !seal.IsDir() || strings.ContainsAny(app, "\r\n") {
		return errors.New("invalid Bearings app signature directory or path")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	details, err := exec.CommandContext(ctx, "/usr/bin/codesign", "--display", "--verbose=4", app).CombinedOutput()
	if err != nil || !bytes.Contains(append(details, '\n'), []byte("\nSignature=adhoc\n")) {
		return errors.New("use the Apple-signed client to manage a Developer ID bundle")
	}
	return appleTool("/usr/bin/codesign", "--verify", "--strict", app)
}

func verifyMacBundle(app string) error {
	if err := macBundleIdentity(app); err != nil {
		return err
	}
	if macAppleTeam == "" {
		icon, err := os.Lstat(filepath.Join(app, "Contents", "Resources", "Bearings.icns"))
		if err != nil || !icon.Mode().IsRegular() {
			return errors.New("the Bearings app bundle is missing its resources")
		}
		return verifyAdHocMacSeal(app)
	}
	if !appleTeamPattern.MatchString(macAppleTeam) {
		return errors.New("this build does not pin an Apple Developer ID team")
	}
	requirement := "anchor apple generic and identifier \"" + macIdentifier + "\"" +
		" and certificate leaf[subject.OU] = \"" + macAppleTeam + "\"" +
		" and certificate leaf[field.1.2.840.113635.100.6.1.13] exists"
	if err := appleTool("/usr/bin/codesign", "--verify", "--strict", "-R", requirement, app); err != nil {
		return err
	}
	return appleTool("/usr/sbin/spctl", "--assess", "--type", "execute", app)
}

func (m macInstall) installApp() error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	executable, err = filepath.EvalSymlinks(executable)
	if err != nil {
		return err
	}
	app := filepath.Dir(filepath.Dir(filepath.Dir(executable)))
	if err := verifyMacBundle(app); err != nil {
		return err
	}

	replace := false
	if _, err := os.Lstat(m.app); err == nil {
		if err := macBundleIdentity(m.app); err != nil {
			return err
		}
		if verifyMacBundle(m.app) == nil {
			_, installedSeal := os.Lstat(macResourceSeal(m.app))
			_, sourceSeal := os.Lstat(macResourceSeal(app))
			if macAppleTeam != "" || !os.IsNotExist(installedSeal) || sourceSeal != nil {
				return nil
			}
			// Keep the locally approved seal when repairing an earlier unsealed installation.
		} else if macAppleTeam == "" {
			if _, err := os.Lstat(macResourceSeal(m.app)); !os.IsNotExist(err) {
				return errors.New("the existing Bearings app requires its original approval or a Developer ID build")
			}
		}
		replace = true
	} else if !os.IsNotExist(err) {
		return err
	}
	parent := filepath.Dir(m.app)
	if err := os.MkdirAll(parent, 0700); err != nil {
		return err
	}
	stage, err := os.MkdirTemp(parent, ".bearings-app-*")
	if err != nil {
		return err
	}
	defer func() {
		if _, err := os.Stat(filepath.Join(stage, "Previous.app")); os.IsNotExist(err) {
			_ = os.RemoveAll(stage)
		}
	}()
	candidate := filepath.Join(stage, "Bearings.app")
	if err := appleTool("/usr/bin/ditto", app, candidate); err != nil {
		return err
	}
	if err := verifyMacBundle(candidate); err != nil {
		return err
	}
	if replace {
		if err := m.activateBundle(candidate, stage); err != nil {
			return err
		}
		return os.RemoveAll(filepath.Join(stage, "Previous.app"))
	}
	return os.Rename(candidate, m.app)
}

func (m macInstall) activateBundle(candidate, stage string) error {
	backup := filepath.Join(stage, "Previous.app")
	if err := os.Rename(m.app, backup); err != nil {
		return err
	}
	if err := os.Rename(candidate, m.app); err != nil {
		return errors.Join(err, os.Rename(backup, m.app))
	}
	return nil
}
