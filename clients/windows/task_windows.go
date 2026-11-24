// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"

	"golang.org/x/sys/windows"
)

func reporterProgram() (string, error) {
	local := os.Getenv("LOCALAPPDATA")
	if !filepath.IsAbs(local) {
		return "", errors.New("could not locate a private program folder")
	}
	return filepath.Join(local, "Programs", "Bearings", "bearings-windows.exe"), nil
}

func installForTask(target string) error {
	dir := filepath.Dir(target)
	if rejectReparse(dir) != nil || os.MkdirAll(dir, 0700) != nil {
		return errors.New("could not prepare a private program folder")
	}
	source, err := os.Executable()
	if err != nil {
		return errors.New("could not locate the running executable")
	}
	binary, err := readBounded(source, 32*1024*1024)
	if err != nil {
		return errors.New("could not read the running executable")
	}
	if rejectReparse(target) != nil {
		return errors.New("the program location must not contain links")
	}
	existing, err := readBounded(target, 32*1024*1024)
	if err == nil && bytes.Equal(existing, binary) {
		return nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return errors.New("a different executable is already installed; follow the client update instructions")
	}
	file, err := os.CreateTemp(dir, ".bearings-client-")
	if err != nil {
		return errors.New("could not copy the executable into the program folder")
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
		return errors.New("could not install the executable without replacing an existing file")
	}
	return nil
}

type reporterTask struct {
	sid, name, program, scheduler string
}

func currentReporterTask() (reporterTask, error) {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil || user.User.Sid == nil {
		return reporterTask{}, errors.New("could not identify the Windows reporting account")
	}
	system, err := windows.GetSystemDirectory()
	if err != nil {
		return reporterTask{}, errors.New("could not locate Windows Task Scheduler")
	}
	program, err := reporterProgram()
	if err != nil {
		return reporterTask{}, err
	}
	sid := user.User.Sid.String()
	return reporterTask{sid: sid, name: "Bearings Windows Inventory " + digest([]byte(sid))[:12],
		program: program, scheduler: filepath.Join(system, "schtasks.exe")}, nil
}

func (t reporterTask) command(ctx context.Context, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, t.scheduler, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	return cmd
}

func (t reporterTask) query() (bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	raw, err := t.command(ctx, "/Query", "/TN", t.name, "/XML").Output()
	if err != nil {
		return false, err
	}
	return matchesReporterTask(taskOutput(raw), t.sid, t.program), nil
}

func (t reporterTask) status() string {
	matches, err := t.query()
	if err != nil {
		return "Automatic reports: Windows task could not be verified."
	}
	if !matches {
		return "Automatic reports: the Windows task is disabled or uses a different configuration."
	}
	if info, err := os.Stat(t.program); err != nil || !info.Mode().IsRegular() || rejectReparse(t.program) != nil {
		return "Automatic reports: the installed executable could not be verified."
	}
	return "Automatic reports: Windows task verified, every six hours while signed in."
}

func scheduleReporter() (string, error) {
	t, err := currentReporterTask()
	if err != nil {
		return "", err
	}
	if err := installForTask(t.program); err != nil {
		return "", err
	}
	matches, queryErr := t.query()
	if queryErr == nil {
		if matches {
			return t.name, nil
		}
		return "", fmt.Errorf("task %q already exists with different settings or is disabled. Review it in Task Scheduler", t.name)
	}
	file, err := os.CreateTemp(filepath.Dir(t.program), ".bearings-task-*.xml")
	if err != nil {
		return "", errors.New("could not prepare the scheduled task")
	}
	defer os.Remove(file.Name())
	xml := taskXML(t.sid, t.program, filepath.Dir(t.program), time.Now().Add(time.Minute))
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
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	raw, createErr := t.command(ctx, "/Create", "/TN", t.name, "/XML", file.Name()).CombinedOutput()
	// Verify the stored task, including when another setup window created it first.
	if matches, err := t.query(); err == nil && matches {
		return t.name, nil
	}
	if ctx.Err() == context.DeadlineExceeded && createErr != nil {
		return "", errors.New("Windows Task Scheduler did not respond in time")
	}
	if createErr != nil {
		detail := []rune(strings.Join(strings.Fields(taskOutput(raw)), " "))
		if len(detail) > 200 {
			detail = append(detail[:197], '.', '.', '.')
		}
		if exit, ok := createErr.(*exec.ExitError); ok {
			return "", fmt.Errorf("Windows could not create the task (exit %d). %s", exit.ExitCode(), string(detail))
		}
		return "", errors.New("Windows Task Scheduler could not be started")
	}
	return "", errors.New("Windows reported task creation, but the saved task could not be verified")
}
