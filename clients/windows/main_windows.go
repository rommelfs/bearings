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

func output(value any) error { return json.NewEncoder(os.Stdout).Encode(value) }

func reportNow(s *store) (*receipt, error) {
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

func watch(dir string, seconds int) {
	for {
		err := func() error {
			s, err := openStore(dir, false)
			if err != nil {
				return err
			}
			defer s.close()
			result, err := reportNow(s)
			if err != nil {
				return err
			}
			return output(result)
		}()
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error()+". Retry next interval.")
		}
		time.Sleep(time.Duration(seconds) * time.Second)
	}
}

func consoleGrant() (grant, error) {
	fd := int(os.Stdin.Fd())
	if !term.IsTerminal(fd) {
		return grant{}, errors.New("enrollment requires an interactive console with hidden input")
	}
	fmt.Fprint(os.Stderr, "Registration code: ")
	raw, err := term.ReadPassword(fd)
	fmt.Fprintln(os.Stderr)
	if err != nil {
		return grant{}, errors.New("could not read the hidden registration code")
	}
	return readGrant(string(raw))
}

func run(args []string) error {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Println("Bearings Windows " + version + "\nUsage: bearings-windows.exe <init|enroll|collect|report|flush|status|watch> [options]\nUse <command> --help to list options.")
		return nil
	}
	if args[0] == "--version" {
		fmt.Println("Bearings Windows " + version)
		return nil
	}
	command := args[0]
	switch command {
	case "init", "enroll", "collect", "report", "flush", "status", "watch":
	default:
		return errors.New("unknown command; use --help")
	}
	options := flag.NewFlagSet(command, flag.ContinueOnError)
	// Keep arguments (which might contain a mistakenly pasted code) out of diagnostics.
	options.SetOutput(os.Stdout)
	dir := options.String("state-dir", "", "Private Windows state directory")
	ca := options.String("ca-file", "", "Approved CA in PEM format (enroll only)")
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
	if options.NArg() != 0 || (command != "enroll" && (*code || *ca != "")) || *interval < 600 || *interval > 86400 {
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
		base := os.Getenv("LOCALAPPDATA")
		if base == "" {
			return errors.New("load your Windows user profile or specify a private --state-dir")
		}
		*dir = filepath.Join(base, "Bearings", "Windows")
	}
	if command == "watch" {
		watch(*dir, *interval)
		return nil
	}
	s, err := openStore(*dir, command == "init")
	if err != nil {
		return err
	}
	defer s.close()
	switch command {
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
		value, err := consoleGrant()
		if err != nil {
			return err
		}
		result, err := enroll(&s.state, s.save, value, *ca)
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
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
