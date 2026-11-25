// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"unicode/utf16"

	"golang.org/x/sys/windows"
)

// Only the standard per-user installation is eligible. The script is fixed in
// the executable and receives local paths, never strings from the server.
const removeWindowsClient = `
$ErrorActionPreference = 'Stop'
$program = $env:BEARINGS_REMOVE_EXE
$state = $env:BEARINGS_REMOVE_STATE
$name = $env:BEARINGS_REMOVE_TASK
function Assert-LocalPath([string]$path) {
    while ($path) {
        if ([IO.File]::Exists($path) -or [IO.Directory]::Exists($path)) {
            if (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Removal path has a reparse point'
            }
        }
        $path = [IO.Path]::GetDirectoryName($path)
    }
}
try {
    if ([int]$env:BEARINGS_REMOVE_PARENT -gt 0) {
        $parent = Get-Process -Id ([int]$env:BEARINGS_REMOVE_PARENT) -ErrorAction SilentlyContinue
        if ($parent -and -not $parent.WaitForExit(30000)) { throw 'Close Bearings and retry removal' }
    }
    Assert-LocalPath $program
    Assert-LocalPath $state
    $scheduler = New-Object -ComObject 'Schedule.Service'
    $scheduler.Connect()
    $folder = $scheduler.GetFolder('\')
    $task = $null
    try {
        $task = $folder.GetTask($name)
    } catch {
        $failure = $_.Exception
        while ($failure.InnerException) { $failure = $failure.InnerException }
        if ($failure.HResult -notin @(-2147024894, -2147024893)) { throw }
    }
    if ($task) {
        $definition = $task.Definition
        $user = $definition.Principal.UserId
        if ($user -notlike 'S-1-*') {
            $user = ([Security.Principal.NTAccount]::new($user)).Translate([Security.Principal.SecurityIdentifier]).Value
        }
        if ($user -ne $env:BEARINGS_REMOVE_SID -or $definition.Actions.Count -ne 1) {
            throw 'Review the existing task in Windows Task Scheduler before removing Bearings'
        }
        $action = $definition.Actions.Item(1)
        if ($action.Type -ne 0 -or $action.Path -ne $program -or $action.Arguments -ne 'report') {
            throw 'Review the existing task in Windows Task Scheduler before removing Bearings'
        }
    }
    $lock = $null
    if ([IO.Directory]::Exists($state)) {
        $lockPath = [IO.Path]::Combine($state, 'lock')
        Assert-LocalPath $lockPath
        $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    }
    try {
        $protected = [IO.Path]::Combine($state, 'state.dpapi')
        Assert-LocalPath $protected
        $actual = 'missing'
        if ([IO.File]::Exists($protected)) {
            $stream = [IO.File]::OpenRead($protected)
            $algorithm = [Security.Cryptography.SHA256]::Create()
            try { $actual = [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
            finally { $algorithm.Dispose(); $stream.Dispose() }
        }
        if ($actual -ne $env:BEARINGS_REMOVE_STATE_HASH) {
            throw 'Bearings state changed before removal. Retry from the current installation.'
        }
        if ([IO.File]::Exists($program)) { [IO.File]::Delete($program) }
        if ($task) { $folder.DeleteTask($name, 0) }
        if ([IO.File]::Exists($protected)) { [IO.File]::Delete($protected) }
        if ($lock) {
            foreach ($temporary in [IO.Directory]::EnumerateFiles($state, '.bearings-*')) {
                Assert-LocalPath $temporary
                [IO.File]::Delete($temporary)
            }
        }
    } finally {
        if ($lock) { $lock.Dispose() }
    }
    if ($lock) { [IO.File]::Delete($lockPath) }
    foreach ($path in @($state, [IO.Path]::GetDirectoryName($program))) {
        if ([IO.Directory]::Exists($path) -and -not [IO.Directory]::EnumerateFileSystemEntries($path).GetEnumerator().MoveNext()) {
            [IO.Directory]::Delete($path)
        }
    }
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
`

func standardRemoval(dir string) (reporterTask, error) {
	expected, err := defaultStateDir()
	if err != nil {
		return reporterTask{}, err
	}
	if !filepath.IsAbs(dir) || !strings.EqualFold(filepath.Clean(dir), filepath.Clean(expected)) || rejectReparse(dir) != nil {
		return reporterTask{}, errors.New("automatic uninstall requires the standard local Bearings profile")
	}
	t, err := currentReporterTask()
	if err != nil {
		return reporterTask{}, err
	}
	if rejectReparse(t.program) != nil {
		return reporterTask{}, errors.New("the installed executable path could not be verified")
	}
	return t, nil
}

func removalStateDigest(dir string) (string, error) {
	path := filepath.Join(dir, "state.dpapi")
	if rejectReparse(path) != nil {
		return "", errors.New("the state file path could not be verified")
	}
	raw, err := readBounded(path, maxState)
	if errors.Is(err, os.ErrNotExist) {
		return "missing", nil
	}
	if err != nil {
		return "", errors.New("the state file could not be verified")
	}
	return digest(raw), nil
}

func removeWindowsInstallation(t reporterTask, dir, stateHash string, parent int, quiet bool) error {
	system := filepath.Dir(t.scheduler)
	shell := filepath.Join(system, "WindowsPowerShell", "v1.0")
	var raw []byte
	for _, unit := range utf16.Encode([]rune(removeWindowsClient)) {
		raw = binary.LittleEndian.AppendUint16(raw, unit)
	}
	cmd := exec.Command(filepath.Join(shell, "powershell.exe"), "-NoLogo", "-NoProfile", "-NonInteractive",
		"-EncodedCommand", base64.StdEncoding.EncodeToString(raw))
	cmd.Dir = shell
	cmd.Env = append(os.Environ(), "PSModulePath="+filepath.Join(shell, "Modules"),
		"BEARINGS_REMOVE_EXE="+t.program, "BEARINGS_REMOVE_STATE="+dir, "BEARINGS_REMOVE_TASK="+t.name,
		"BEARINGS_REMOVE_SID="+t.sid, "BEARINGS_REMOVE_PARENT="+strconv.Itoa(parent),
		"BEARINGS_REMOVE_STATE_HASH="+stateHash)
	if quiet {
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	} else {
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	}
	if parent == 0 {
		if err := cmd.Run(); err != nil {
			return errors.New("Windows removal failed; review the local helper error and retry")
		}
		return nil
	}
	if err := cmd.Start(); err != nil {
		return errors.New("could not start the Windows removal helper")
	}
	return cmd.Process.Release()
}

func remoteUninstall(s *store) (bool, error) {
	t, err := standardRemoval(s.dir)
	if err != nil || s.state.DeviceID == "" {
		return false, nil
	}
	action, err := uninstallRequest(&s.state, "check")
	if err != nil || action != "uninstall" {
		return false, nil // The normal report independently checks connectivity and authorization.
	}
	stateHash, err := removalStateDigest(s.dir)
	if err != nil {
		return false, err
	}
	if _, err := uninstallRequest(&s.state, "acknowledge"); err != nil {
		return false, err
	}
	return true, removeWindowsInstallation(t, s.dir, stateHash, os.Getpid(), true)
}

func localUninstall() error {
	dir, err := defaultStateDir()
	if err != nil {
		return err
	}
	t, err := standardRemoval(dir)
	if err != nil {
		return err
	}
	if _, err := os.Stat(filepath.Join(dir, "state.dpapi")); err == nil {
		s, openErr := openStore(dir, false)
		if openErr == nil {
			if s.state.DeviceID != "" {
				_, openErr = uninstallRequest(&s.state, "local")
			}
			s.close()
		}
		if openErr != nil {
			fmt.Fprintln(os.Stderr, "Server deregistration could not be confirmed. Check the device in Bearings.")
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	stateHash, err := removalStateDigest(dir)
	if err != nil {
		return err
	}
	parent := os.Getpid()
	if program, err := os.Executable(); err == nil && !strings.EqualFold(program, t.program) {
		parent = 0 // An extracted copy can wait for cleanup without locking the installed image.
	}
	if err := removeWindowsInstallation(t, dir, stateHash, parent, false); err != nil {
		return err
	}
	if parent == 0 {
		fmt.Println("Bearings Windows client and local state removed.")
	} else {
		fmt.Println("Windows removal started. Wait for the local helper to finish.")
	}
	return nil
}
