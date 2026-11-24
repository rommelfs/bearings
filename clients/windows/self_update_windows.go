// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"golang.org/x/sys/windows"
)

// Directory-relative POSIX rename atomically replaces an executing destination on supported
// Windows/NTFS. Never fall back to removing or moving the old task target first.
func replaceExecutable(from, to string) error {
	// Image teardown and endpoint scanners can briefly retain incompatible handles
	// after a successful startup probe. Retry only transient sharing/access errors;
	// every attempt remains one atomic rename and never removes the task target.
	deadline := time.Now().Add(3 * time.Second)
	for {
		err := renameExecutable(from, to)
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) || (!errors.Is(err, windows.ERROR_SHARING_VIOLATION) && !errors.Is(err, windows.ERROR_ACCESS_DENIED) && !errors.Is(err, windows.ERROR_LOCK_VIOLATION)) {
			return err
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func renameExecutable(from, to string) error {
	if !strings.EqualFold(filepath.Dir(from), filepath.Dir(to)) {
		return errors.New("client replacement must stay in its program directory")
	}
	// Go's directory-relative Windows implementation uses NtSetInformationFile
	// with FileRenameInformationEx/POSIX flags. Binding the directory avoids the
	// Win32 full-path conversion (including short-name aliases of the running EXE).
	root, err := os.OpenRoot(filepath.Dir(to))
	if err != nil {
		return err
	}
	defer root.Close()
	return root.Rename(filepath.Base(from), filepath.Base(to))
}

func stagedExecutable(dir string, data []byte) (string, error) {
	file, err := os.CreateTemp(dir, ".bearings-update-*.exe")
	if err != nil {
		return "", errors.New("client program directory is not writable")
	}
	name := file.Name()
	_, err = file.Write(data)
	if err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		os.Remove(name)
		return "", errors.New("could not stage client executable")
	}
	return name, nil
}

type boundedOutput struct {
	data     []byte
	limit    int
	exceeded bool
}

func (w *boundedOutput) Write(p []byte) (int, error) {
	if len(w.data)+len(p) > w.limit {
		w.exceeded = true
		return 0, errors.New("probe output exceeds limit")
	}
	w.data = append(w.data, p...)
	return len(p), nil
}

func probeExecutable(name string, expected clientBuildInfo) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, name, "--update-info")
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	command.WaitDelay = 2 * time.Second
	var out boundedOutput
	out.limit = 16384
	command.Stdout = &out
	command.Stderr = &out
	var actual clientBuildInfo
	if command.Run() != nil || out.exceeded || decodeStrict(out.data, &actual) != nil || actual != expected {
		return errors.New("new client failed its offline startup probe")
	}
	return nil
}

// Run the rename outside the process whose executable is being replaced. Some
// Windows image/resource handles reject self-replacement even with POSIX flags.
func workerReplace(worker, from, to string, expectedHash string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, worker, "--replace-client", from, to)
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
	command.WaitDelay = 2 * time.Second
	var output boundedOutput
	output.limit = 16384
	command.Stdout = &output
	command.Stderr = &output
	err := command.Run()
	installed, readErr := readBounded(to, maxUpdateArchive)
	if readErr == nil && digest(installed) == expectedHash {
		return nil
	}
	if err != nil {
		return fmt.Errorf("Windows replacement worker failed: %s", strings.TrimSpace(string(output.data)))
	}
	return errors.New("Windows replacement did not install the expected executable")
}

func runReplacementWorker(args []string) error {
	if len(args) != 2 {
		return errors.New("invalid replacement worker arguments")
	}
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	for _, name := range args {
		if !filepath.IsAbs(name) || !strings.EqualFold(filepath.Dir(name), filepath.Dir(executable)) || rejectReparse(name) != nil {
			return errors.New("replacement worker paths must stay in its program directory without links")
		}
	}
	return replaceExecutable(args[0], args[1])
}

func installRelease(target string, executable []byte, expected clientBuildInfo, save func() error) error {
	if rejectReparse(target) != nil {
		return errors.New("client program path must be free of links and junctions")
	}
	dir := filepath.Dir(target)
	previous, err := readBounded(target, maxUpdateArchive)
	if err != nil {
		return errors.New("could not retain the previous executable")
	}
	candidate, err := stagedExecutable(dir, executable)
	if err != nil {
		return err
	}
	defer os.Remove(candidate)
	if err := probeExecutable(candidate, expected); err != nil {
		return err
	}
	backup, err := stagedExecutable(dir, previous)
	if err != nil {
		return err
	}
	// Keep a backup on unsuccessful rollback; remove it only after confirmed recovery.
	removeBackup := true
	defer func() {
		if removeBackup {
			os.Remove(backup)
		}
	}()
	worker, err := stagedExecutable(dir, executable)
	if err != nil {
		return err
	}
	defer os.Remove(worker)
	err = workerReplace(worker, candidate, target, digest(executable))
	if err == nil {
		err = probeExecutable(target, expected)
	}
	if err == nil {
		err = save()
	}
	if err != nil {
		if rollbackErr := workerReplace(worker, backup, target, digest(previous)); rollbackErr != nil {
			removeBackup = false
			return fmt.Errorf("client update failed; rollback failed; retained executable backup: %s", backup)
		}
		return fmt.Errorf("client update failed; previous executable restored: %w", err)
	}
	return nil
}

func (s *store) checkAutoUpdate(force bool) error {
	info := buildInfo()
	if s.state.Update == nil {
		s.state.Update = &clientUpdateState{}
	}
	update := s.state.Update
	if !force && (update.Disabled || (!update.CheckedAt.IsZero() && time.Since(update.CheckedAt) >= 0 && time.Since(update.CheckedAt) < time.Hour)) {
		return nil
	}
	if !force && info.Key == "" {
		return nil
	} // Explicitly unconfigured developer builds.
	fail := func(err error) error {
		update.CheckedAt = time.Now().UTC()
		update.Status = "error"
		update.Error = err.Error()
		if saveErr := s.save(); saveErr != nil {
			return fmt.Errorf("%v; update status could not be saved", err)
		}
		return err
	}
	target, err := os.Executable()
	if err != nil {
		return fail(errors.New("could not locate the installed client"))
	}
	target, err = filepath.Abs(target)
	if err != nil || rejectReparse(target) != nil {
		return fail(errors.New("invalid client executable path"))
	}
	lockPath := target + ".update.lock"
	if rejectReparse(lockPath) != nil {
		return fail(errors.New("invalid client update lock path"))
	}
	lock, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return fail(errors.New("client program directory is not writable"))
	}
	defer lock.Close()
	var offset windows.Overlapped
	if windows.LockFileEx(windows.Handle(lock.Fd()), windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset) != nil {
		return fail(errors.New("another client update is already running"))
	}
	if probeExecutable(target, info) != nil {
		return fail(errors.New("client executable changed; restart the installed client before updating again"))
	}
	client, err := transport(s.state.CAFile)
	if err != nil {
		return fail(err)
	}
	defer client.CloseIdleConnections()
	release, executable, err := obtainUpdate(&s.state, info, client)
	if err != nil {
		return fail(err)
	}
	update.CheckedAt = time.Now().UTC()
	update.Error = ""
	if executable == nil {
		update.Status = "current"
		floor := info.Sequence
		if update.Sequence > floor {
			floor = update.Sequence
		}
		if release.Sequence < floor {
			update.Status = "server_older"
		}
		return s.save()
	}
	expected := info
	expected.Version = release.Version
	expected.Sequence = release.Sequence
	previous := *update
	err = installRelease(target, executable, expected, func() error {
		update.Status = "updated"
		update.Version = release.Version
		update.Sequence = release.Sequence
		return s.save()
	})
	if err != nil {
		*update = previous
		return fail(err)
	}
	s.updated = true
	return nil
}

func (s *store) automaticUpdate() {
	if err := s.checkAutoUpdate(false); err != nil {
		fmt.Fprintln(os.Stderr, "Client update: "+err.Error())
	}
}

func (s *store) updateStatus() map[string]any {
	return map[string]any{"client_build": buildInfo(), "client_update": s.state.Update}
}

func restartWatcher() error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	command := exec.Command(executable, os.Args[1:]...)
	command.Env = append(os.Environ(), "BEARINGS_UPDATE_PARENT_PID="+strconv.Itoa(os.Getpid()))
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	command.Stdin = os.Stdin
	if err := command.Start(); err != nil {
		return err
	}
	return command.Process.Release()
}

func waitUpdateParent() (bool, error) {
	value := os.Getenv("BEARINGS_UPDATE_PARENT_PID")
	if value == "" {
		return false, nil
	}
	os.Unsetenv("BEARINGS_UPDATE_PARENT_PID")
	pid, err := strconv.ParseUint(value, 10, 32)
	if err != nil || pid == 0 || uint32(pid) == uint32(os.Getpid()) {
		return false, errors.New("invalid client update parent")
	}
	handle, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if errors.Is(err, windows.ERROR_INVALID_PARAMETER) {
		return true, nil
	} // Parent has already exited.
	if err != nil {
		return false, errors.New("cannot wait for previous client process")
	}
	defer windows.CloseHandle(handle)
	result, err := windows.WaitForSingleObject(handle, 30000)
	if err != nil || result != windows.WAIT_OBJECT_0 {
		return false, errors.New("previous client process did not exit")
	}
	return true, nil
}

func updatePreference(s *store, value string) error {
	if s.state.Update == nil {
		s.state.Update = &clientUpdateState{}
	}
	switch strings.ToLower(value) {
	case "enable":
		s.state.Update.Disabled = false
	case "disable":
		s.state.Update.Disabled = true
	case "status":
		return output(s.updateStatus())
	case "":
		if err := s.checkAutoUpdate(true); err != nil {
			return err
		}
		return output(s.updateStatus())
	default:
		return errors.New("use --auto-update=enable, disable or status")
	}
	if err := s.save(); err != nil {
		return err
	}
	return output(s.updateStatus())
}

// Keep build probes offline: no state/DPAPI, registry, WUA or network access.
func outputBuildInfo() error { return json.NewEncoder(os.Stdout).Encode(buildInfo()) }
