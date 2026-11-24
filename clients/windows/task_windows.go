// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
	"unicode/utf16"

	"golang.org/x/sys/windows"
)

func installForTask() (string, error) {
	dir, err := filepath.Abs(filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "Bearings"))
	if err != nil || os.Getenv("LOCALAPPDATA") == "" || rejectReparse(dir) != nil || os.MkdirAll(dir, 0700) != nil {
		return "", errors.New("could not prepare a private program folder")
	}
	source, err := os.Executable()
	if err != nil {
		return "", errors.New("could not locate the running executable")
	}
	binary, err := readBounded(source, 32*1024*1024)
	if err != nil {
		return "", errors.New("could not read the running executable")
	}
	target := filepath.Join(dir, "bearings-windows.exe")
	if rejectReparse(target) != nil {
		return "", errors.New("the program location must not contain links")
	}
	existing, err := readBounded(target, 32*1024*1024)
	if err == nil && bytes.Equal(existing, binary) {
		return target, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return "", errors.New("a different executable is already installed; follow the client update instructions")
	}
	file, err := os.CreateTemp(dir, ".bearings-client-")
	if err != nil {
		return "", errors.New("could not copy the executable into the program folder")
	}
	defer os.Remove(file.Name())
	_, err = file.Write(binary)
	if err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	from, fromErr := windows.UTF16PtrFromString(file.Name())
	to, toErr := windows.UTF16PtrFromString(target)
	if err != nil || fromErr != nil || toErr != nil || windows.MoveFileEx(from, to, windows.MOVEFILE_WRITE_THROUGH) != nil {
		return "", errors.New("could not install the executable without replacing an existing file")
	}
	return target, nil
}

func scheduleReporter() (string, error) {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil || user.User.Sid == nil {
		return "", errors.New("could not identify the Windows reporting account")
	}
	sid := user.User.Sid.String()
	system, err := windows.GetSystemDirectory()
	if err != nil {
		return "", errors.New("could not locate Windows Task Scheduler")
	}
	program, err := installForTask()
	if err != nil {
		return "", err
	}
	file, err := os.CreateTemp(filepath.Dir(program), ".bearings-task-*.xml")
	if err != nil {
		return "", errors.New("could not prepare the scheduled task")
	}
	defer os.Remove(file.Name())
	xml := taskXML(sid, program, filepath.Dir(program), time.Now().Add(time.Minute))
	task := []byte{0xff, 0xfe}
	for _, unit := range utf16.Encode([]rune(xml)) {
		task = binary.LittleEndian.AppendUint16(task, unit)
	}
	_, err = file.Write(task)
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return "", errors.New("could not prepare the scheduled task")
	}
	name := "Bearings Windows Inventory " + digest([]byte(sid))[:12]
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, filepath.Join(system, "schtasks.exe"), "/Create", "/TN", name, "/XML", file.Name())
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	if err := cmd.Run(); err != nil {
		return "", errors.New("Windows did not create the task. Check Task Scheduler for an existing Bearings task or account restrictions")
	}
	return name, nil
}
