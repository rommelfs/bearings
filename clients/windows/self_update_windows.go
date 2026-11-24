// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	"golang.org/x/sys/windows"
)

var versionedName = regexp.MustCompile(`^bearings-windows-release-[1-9][0-9]{0,18}-[0-9a-f]{64}\.exe$`)

const activationName = ".bearings-windows-current.json"

func atomicControlFile(name string, raw []byte) error {
	if rejectReparse(name) != nil {
		return errors.New("client activation path contains a link")
	}
	file, err := os.CreateTemp(filepath.Dir(name), ".bearings-activation-")
	if err != nil {
		return err
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
		return err
	}
	from, err := windows.UTF16PtrFromString(file.Name())
	if err != nil {
		return err
	}
	to, err := windows.UTF16PtrFromString(name)
	if err != nil {
		return err
	}
	deadline := time.Now().Add(3 * time.Second)
	for {
		err = windows.MoveFileEx(from, to, windows.MOVEFILE_REPLACE_EXISTING|windows.MOVEFILE_WRITE_THROUGH)
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) || (!errors.Is(err, windows.ERROR_SHARING_VIOLATION) && !errors.Is(err, windows.ERROR_ACCESS_DENIED) && !errors.Is(err, windows.ERROR_LOCK_VIOLATION)) {
			return err
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func versionedProgram(dir string, release clientRelease, architecture string) string {
	return filepath.Join(dir, "bearings-windows-release-"+strconv.FormatInt(release.Sequence, 10)+"-"+release.Assets[architecture].EXESHA256+".exe")
}

func readActivation(dir string, info clientBuildInfo) (clientRelease, error) {
	var empty clientRelease
	name := filepath.Join(dir, activationName)
	if rejectReparse(name) != nil {
		return empty, errors.New("invalid client activation path")
	}
	raw, err := readBounded(name, maxRelease)
	if err != nil {
		return empty, err
	}
	key, err := base64.StdEncoding.Strict().DecodeString(info.Key)
	if err != nil {
		return empty, errors.New("invalid embedded publisher key")
	}
	return verifyRelease(raw, key, info.Origin, info.Architecture)
}

func activeProgram(dir string, info clientBuildInfo) (string, error) {
	release, err := readActivation(dir, info)
	if err != nil {
		return "", err
	}
	if release.Sequence <= info.Sequence {
		return "", nil
	}
	program := versionedProgram(dir, release, info.Architecture)
	if rejectReparse(program) != nil {
		return "", errors.New("active client executable contains a link")
	}
	asset := release.Assets[info.Architecture]
	raw, err := readBounded(program, asset.EXESize)
	if err != nil || int64(len(raw)) != asset.EXESize || digest(raw) != asset.EXESHA256 {
		return "", errors.New("active client executable is missing or has an invalid digest")
	}
	return program, nil
}

func forwardClient(args []string) (bool, int, error) {
	if len(args) > 0 && args[0] == "--update-info" {
		return false, 0, nil
	}
	executable, err := os.Executable()
	if err != nil {
		return false, 0, err
	}
	if buildInfo().Key == "" {
		return false, 0, nil
	}
	program, err := activeProgram(filepath.Dir(executable), buildInfo())
	if errors.Is(err, os.ErrNotExist) {
		return false, 0, nil
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "Client activation: "+err.Error()+". Using bundled client.")
		return false, 0, nil
	}
	if program == "" {
		return false, 0, nil
	}
	if len(args) == 0 || (len(args) == 1 && args[0] == "setup") {
		hidePrivateConsole()
	}
	command := exec.Command(program, args...)
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	if err := command.Run(); err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			return true, exit.ExitCode(), nil
		}
		return true, 1, errors.New("could not start the activated Windows client")
	}
	return true, 0, nil
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

// Executables are immutable versioned files. Only a small signed activation
// record is replaced atomically; a running Windows image is never overwritten.
func installRelease(target string, executable []byte, release clientRelease, expected clientBuildInfo, save func() error) error {
	if rejectReparse(target) != nil {
		return errors.New("client program path must be free of links and junctions")
	}
	key, keyErr := base64.StdEncoding.Strict().DecodeString(expected.Key)
	verified, verifyErr := verifyRelease(release.envelope, key, expected.Origin, expected.Architecture)
	if keyErr != nil || verifyErr != nil || verified.Sequence != expected.Sequence || verified.Version != expected.Version || verified.Assets[expected.Architecture].EXESHA256 != digest(executable) || verified.Assets[expected.Architecture].EXESize != int64(len(executable)) {
		return errors.New("release activation is not bound to the verified executable")
	}
	release = verified
	dir := filepath.Dir(target)
	activation := filepath.Join(dir, activationName)
	if rejectReparse(activation) != nil {
		return errors.New("invalid activation path")
	}
	previous, err := readBounded(activation, maxRelease)
	existed := err == nil
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return errors.New("could not retain previous client activation")
	}
	program := versionedProgram(dir, release, expected.Architecture)
	if rejectReparse(program) != nil {
		return errors.New("invalid versioned executable path")
	}
	existing, err := readBounded(program, maxUpdateArchive)
	if err == nil {
		if !bytes.Equal(existing, executable) {
			return errors.New("an immutable release file has different contents")
		}
	} else if errors.Is(err, os.ErrNotExist) {
		staged, err := stagedExecutable(dir, executable)
		if err != nil {
			return err
		}
		defer os.Remove(staged)
		if err := probeExecutable(staged, expected); err != nil {
			return err
		}
		from, err := windows.UTF16PtrFromString(staged)
		if err != nil {
			return err
		}
		to, err := windows.UTF16PtrFromString(program)
		if err != nil {
			return err
		}
		if err := windows.MoveFileEx(from, to, windows.MOVEFILE_WRITE_THROUGH); err != nil {
			return errors.New("could not retain the verified immutable client release")
		}
	} else {
		return errors.New("versioned client file is not accessible")
	}
	if err := probeExecutable(program, expected); err != nil {
		return err
	}
	if len(release.envelope) == 0 {
		return errors.New("signed activation metadata is missing")
	}
	backup := activation + ".previous"
	if existed {
		if err := atomicControlFile(backup, previous); err != nil {
			return errors.New("could not retain previous signed activation")
		}
	}
	if err := atomicControlFile(activation, release.envelope); err != nil {
		return errors.New("could not activate the verified client; prior activation retained")
	}
	if err := save(); err != nil {
		var rollbackErr error
		if existed {
			from, fromErr := windows.UTF16PtrFromString(backup)
			to, toErr := windows.UTF16PtrFromString(activation)
			if fromErr != nil || toErr != nil {
				rollbackErr = errors.New("invalid activation backup path")
			} else {
				rollbackErr = windows.MoveFileEx(from, to, windows.MOVEFILE_REPLACE_EXISTING|windows.MOVEFILE_WRITE_THROUGH)
			}
		} else {
			rollbackErr = os.Remove(activation)
		}
		if rollbackErr != nil {
			return errors.New("client state save failed; activation rollback failed; verified release retained for recovery")
		}
		return errors.New("client state save failed; previous activation restored")
	}
	cleanupReleases(dir, program, previous, expected)
	return nil
}

func cleanupReleases(dir, current string, previous []byte, info clientBuildInfo) {
	keep := map[string]bool{filepath.Base(current): true}
	key, err := base64.StdEncoding.Strict().DecodeString(info.Key)
	if err == nil {
		if release, err := verifyRelease(previous, key, info.Origin, info.Architecture); err == nil {
			keep[filepath.Base(versionedProgram(dir, release, info.Architecture))] = true
		}
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, entry := range entries {
		name := entry.Name()
		if !keep[name] && versionedName.MatchString(name) && entry.Type().IsRegular() {
			path := filepath.Join(dir, name)
			if rejectReparse(path) == nil {
				os.Remove(path)
			} // Windows retains an image still in use.
		}
	}
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
	lockPath := filepath.Join(filepath.Dir(target), ".bearings-update.lock")
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
	if active, err := readActivation(filepath.Dir(target), info); err == nil && active.Sequence > update.Sequence {
		// A crash may commit activation before the protected metadata save. Its signed
		// sequence remains the rollback floor even in an older still-open GUI process.
		update.Sequence = active.Sequence
		update.Version = active.Version
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
	err = installRelease(target, executable, release, expected, func() error {
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
	if active, err := activeProgram(filepath.Dir(executable), buildInfo()); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	} else if active != "" {
		executable = active
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
