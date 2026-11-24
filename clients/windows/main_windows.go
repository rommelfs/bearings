// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"golang.org/x/term"
)

var version = "development"

func defaultStateDir() (string, error) {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		return "", errors.New("load your Windows user profile or specify a private --state-dir")
	}
	return filepath.Join(base, "Bearings", "Windows"), nil
}

func output(value any) error { return json.NewEncoder(os.Stdout).Encode(value) }

func reportNow(s *store) (*receipt, error) {
	defer s.automaticUpdate()
	if err := s.state.ready(); err != nil {
		return nil, err
	}
	if len(s.state.Queue) >= maxQueue {
		if _, err := flush(&s.state, s.save); err != nil {
			return nil, err
		}
		time.Sleep(11 * time.Second)
	}
	value, err := collect()
	if err != nil {
		if _, deliveryErr := flush(&s.state, s.save); deliveryErr != nil {
			return nil, deliveryErr
		}
		return nil, err
	}
	if err := enqueue(&s.state, s.save, value); err != nil {
		return nil, err
	}
	return flush(&s.state, s.save)
}

func watch(dir string, seconds int) error {
	resumed, err := waitUpdateParent()
	if err != nil {
		return err
	}
	if resumed {
		time.Sleep(time.Duration(seconds) * time.Second)
	}
	for {
		updated := false
		err := func() error {
			s, err := openStore(dir, false)
			if err != nil {
				return err
			}
			defer s.close()
			result, err := reportNow(s)
			updated = s.updated
			if err != nil {
				return err
			}
			return output(result)
		}()
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error()+". Retry next interval.")
		}
		if updated {
			return restartWatcher()
		}
		time.Sleep(time.Duration(seconds) * time.Second)
	}
}

func consoleCode() (string, error) {
	fd := int(os.Stdin.Fd())
	if !term.IsTerminal(fd) {
		return "", errors.New("enrollment requires an interactive console with hidden input")
	}
	fmt.Fprint(os.Stderr, "Registration code: ")
	raw, err := term.ReadPassword(fd)
	fmt.Fprintln(os.Stderr)
	if err != nil {
		return "", errors.New("could not read the hidden registration code")
	}
	return string(raw), nil
}

func run(args []string) error {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Println("Bearings Windows " + version + "\nUsage: bearings-windows.exe <setup|init|enroll|collect|report|flush|status|watch|update> [options]\nUse <command> --help to list options.")
		return nil
	}
	if args[0] == "--version" {
		fmt.Println("Bearings Windows " + version)
		return nil
	}
	if args[0] == "--replace-client" {
		return runReplacementWorker(args[1:])
	}
	if args[0] == "--update-info" {
		return outputBuildInfo()
	}
	command := args[0]
	switch command {
	case "init", "enroll", "collect", "report", "flush", "status", "watch", "update":
	default:
		return errors.New("unknown command; use --help")
	}
	options := flag.NewFlagSet(command, flag.ContinueOnError)
	// Keep arguments (which might contain a mistakenly pasted code) out of diagnostics.
	options.SetOutput(os.Stdout)
	dir := options.String("state-dir", "", "Private Windows state directory")
	ca := options.String("ca-file", "", "Approved CA in PEM format (enroll only)")
	autoUpdate := options.String("auto-update", "", "update only: enable, disable or status (empty checks now)")
	code := options.Bool("code", false, "Read an enrollment code from the hidden prompt")
	interval := options.Int("interval", 21600, "Seconds between watch reports (600–86400)")
	for _, arg := range args[1:] {
		if arg == "--help" || arg == "-h" {
			options.PrintDefaults()
			return nil
		}
	}
	if err := parseOptions(options, args[1:]); err != nil {
		return err
	}
	if (command != "update" && *autoUpdate != "") || options.NArg() != 0 || (command != "enroll" && (*code || *ca != "")) || *interval < 600 || *interval > 86400 {
		return errors.New("invalid command options; use <command> --help")
	}
	if command == "collect" {
		value, err := collect()
		if err != nil {
			return err
		}
		return output(value)
	}
	if *dir == "" {
		path, err := defaultStateDir()
		if err != nil {
			return err
		}
		*dir = path
	}
	if command == "watch" {
		return watch(*dir, *interval)
	}
	s, err := openStore(*dir, command == "init" || command == "enroll")
	if err != nil {
		return err
	}
	defer s.close()
	switch command {
	case "update":
		return updatePreference(s, *autoUpdate)
	case "init":
		return output(map[string]any{"public_key": s.state.publicKey(), "enrolled": s.state.DeviceID != ""})
	case "enroll":
		if !*code {
			return errors.New("use enroll --code and paste the code at the hidden prompt")
		}
		if *ca != "" {
			*ca, err = filepath.Abs(*ca)
			if err != nil {
				return errors.New("use a valid path for the approved CA")
			}
		}
		value, err := consoleCode()
		if err != nil {
			return err
		}
		hostname, err := os.Hostname()
		if err != nil && rolloutInput(value) {
			return errors.New("cannot read the Windows computer name")
		}
		result, err := enrollCode(&s.state, s.save, value, *ca, hostname)
		if err != nil {
			return err
		}
		return output(result)
	case "report", "flush":
		var result *receipt
		if command == "report" {
			result, err = reportNow(s)
		} else {
			result, err = flush(&s.state, s.save)
		}
		if err != nil {
			return err
		}
		if result == nil {
			return output(map[string]string{"state": "outbox_empty"})
		}
		return output(result)
	case "status":
		result, err := status(&s.state)
		if err != nil {
			return err
		}
		return output(result)
	}
	return nil
}

func parseOptions(options *flag.FlagSet, args []string) error {
	options.SetOutput(io.Discard)
	if err := options.Parse(args); err != nil {
		return errors.New("invalid command options; use <command> --help")
	}
	return nil
}

func main() {
	if len(os.Args) == 1 || (len(os.Args) == 2 && os.Args[1] == "setup") {
		if err := setupGUI(); err != nil {
			uiError(0, err.Error())
			os.Exit(1)
		}
		return
	}
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
