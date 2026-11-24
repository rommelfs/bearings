// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"io"
	"os/exec"
	"path/filepath"
	"runtime"
	"syscall"
	"time"
	"unicode/utf16"

	"golang.org/x/sys/windows"
)

func collectUpdates() *updateObservation {
	system, err := windows.GetSystemDirectory()
	if err != nil {
		return unavailableUpdates("unavailable")
	}
	// On a 32-bit client on a 64-bit OS, use the native helper via Sysnative.
	if native, err := nativeArchitecture(); err == nil && native != "x86" {
		if runtime.GOARCH == "386" {
			system = filepath.Join(filepath.Dir(system), "Sysnative")
		}
	}
	units := utf16.Encode([]rune(updateScript))
	raw := make([]byte, len(units)*2)
	for i, u := range units {
		binary.LittleEndian.PutUint16(raw[i*2:], u)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, filepath.Join(system, "WindowsPowerShell", "v1.0", "powershell.exe"),
		"-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.StdEncoding.EncodeToString(raw))
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	command.WaitDelay = 2 * time.Second
	var output updateOutput
	command.Stdout = &output
	command.Stderr = io.Discard
	if err := command.Run(); err != nil {
		if ctx.Err() != nil {
			return unavailableUpdates("timeout")
		}
		return unavailableUpdates("unavailable")
	}
	result, err := decodeUpdates(output.Bytes())
	if err != nil {
		return unavailableUpdates("unavailable")
	}
	return result
}
