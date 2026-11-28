// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/rand/v2"
	"os"
	"os/signal"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"time"
)

type repeated []string

func (p *repeated) String() string     { return strings.Join(*p, ",") }
func (p *repeated) Set(v string) error { *p = append(*p, v); return nil }
func defaultState() string {
	base := os.Getenv("XDG_STATE_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return ""
		}
		base = filepath.Join(home, ".local", "state")
	}
	return filepath.Join(base, "bearings-linux")
}
func run(args []string) error {
	if len(args) == 0 {
		return errors.New("use init, bootstrap, archive-bootstrap, enroll, collect, report, enqueue, flush, status, watch, retirement or version")
	}
	if args[0] == "version" {
		fmt.Println(version)
		return nil
	}
	if args[0] == "validate-applications" {
		flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
		flags.SetOutput(io.Discard)
		config := flags.String("config", "", "local profile document to validate without collecting")
		if flags.Parse(args[1:]) != nil || flags.NArg() != 0 || *config == "" {
			return errors.New("use validate-applications --config FILE")
		}
		profiles, err := loadApplicationConfiguration(*config)
		if err != nil {
			return err
		}
		return output(map[string]any{"schema": "bearings.application-probes.v1", "profiles": len(profiles)})
	}
	if args[0] == "retirement" {
		if len(args) != 3 || (args[1] != "check" && args[1] != "acknowledge" && args[1] != "local") {
			return errors.New("use retirement check|acknowledge|local STATE_DIRECTORY")
		}
		s, err := openStore(args[2], false)
		if err != nil {
			return err
		}
		defer s.close()
		result, err := uninstallRequest(s, args[1])
		if err != nil {
			return err
		}
		fmt.Println(result)
		return nil
	}
	flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	server := flags.String("server", "", "trusted HTTPS origin for automatic registration")
	state := flags.String("state-dir", defaultState(), "private local state directory")
	grantFile := flags.String("grant-file", "", "one-use enrollment file (0600)")
	ca := flags.String("ca-file", "", "additional explicitly trusted PEM CA")
	registerHost := flags.Bool("register-host", false, "explicitly include local hostname and configured interface addresses during enrollment")
	binariesFile := flags.String("binaries-file", "", "local administrator-approved binary probe configuration")
	inventory := flags.Bool("inventory", false, "observe the complete supported package database")
	serviceName := flags.String("service", "", "supported nginx runtime/package profile")
	id := flags.String("report", "", "receipt identifier")
	interval := flags.Duration("interval", 6*time.Hour, "local observation interval, at least 15m")
	var selected repeated
	flags.Var(&selected, "package", "exact package name; repeat for multiple names")
	if err := flags.Parse(args[1:]); err != nil || flags.NArg() != 0 {
		return errors.New("invalid arguments; use --state-dir, --inventory, --service nginx or --package NAME / --binaries-file FILE as documented")
	}
	if args[0] == "collect" {
		r, err := collectConfigured(*inventory, selected, *serviceName, *binariesFile)
		if err != nil {
			return err
		}
		r.Gaps = nil
		return output(r)
	}
	s, err := openStore(*state, args[0] == "init")
	if err != nil {
		return err
	}
	defer s.close()
	switch args[0] {
	case "init":
		sum := sha256.Sum256(s.key[32:])
		return output(map[string]string{"public_key": s.public(), "fingerprint_sha256": hex.EncodeToString(sum[:])})
	case "bootstrap":
		return bootstrap(s, *server, *ca, os.Stdin)
	case "archive-bootstrap":
		name, err := archiveBootstrap(s)
		if err != nil {
			return err
		}
		if name == "" {
			fmt.Println("No pending bootstrap to archive.")
		} else {
			fmt.Println("Bootstrap archived as " + name + ". Device key retained.")
		}
		return nil
	case "enroll":
		if *grantFile == "" {
			return errors.New("supply --grant-file; bearer secrets are not accepted on the command line")
		}
		return enroll(s, *grantFile, *ca, *registerHost)
	case "flush":
		return flush(s)
	case "status":
		return getStatus(s, *id)
	case "report", "enqueue":
		if err = ready(s); err != nil {
			return err
		}
		r, err := collectConfigured(*inventory, selected, *serviceName, *binariesFile)
		if err != nil {
			return err
		}
		r.Gaps = nil
		if err = s.enqueue(r); err != nil {
			return err
		}
		if args[0] == "enqueue" {
			return output(map[string]string{"state": "queued_locally", "report_id": r.ReportID})
		}
		if err = flush(s); err != nil {
			return fmt.Errorf("queued locally; %w", err)
		}
		return nil
	case "watch":
		if *interval < 15*time.Minute || *interval > 7*24*time.Hour {
			return errors.New("observation interval must be 15m–168h")
		}
		if err = ready(s); err != nil {
			return err
		}
		dir := s.dir
		s.close()
		s.lock = nil
		return watch(dir, *inventory, selected, *serviceName, *binariesFile, inventoryWatchInterval(args, *interval, os.Getenv("INVOCATION_ID") != ""))
	default:
		return errors.New("unknown command")
	}
}

// Keep the shipped unit byte-for-byte compatible with the installed updater.
// Only the exact stock systemd invocation opts into the negotiated cadence.
func inventoryWatchInterval(args []string, interval time.Duration, systemd bool) time.Duration {
	stock := []string{"watch", "--state-dir", "/var/lib/bearings-linux", "--inventory", "--interval", "6h"}
	if systemd && slices.Equal(args, stock) {
		return 15 * time.Minute
	}
	return interval
}

// watch releases the state lock between operations so CLI update hooks can coexist.
// Failed delivery uses bounded exponential backoff and jitter; no queued input is evicted.
func watch(dir string, inventory bool, selected []string, serviceName string, binariesFile string, interval time.Duration) error {
	if binariesFile != "" && (inventory || len(selected) > 0 || serviceName != "") {
		return errors.New("binary probes require their own explicit collection scope")
	}
	if binariesFile == "" && ((!inventory && len(selected) == 0 && serviceName == "") || (inventory && (len(selected) > 0 || serviceName != "")) || (len(selected) > 0 && serviceName != "") || (serviceName != "" && serviceName != "nginx")) {
		return errors.New("choose one supported explicit collection scope")
	}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, os.Interrupt)
	defer signal.Stop(stop)
	nextCapture := time.Now().Add(time.Duration(rand.Int64N(int64(2 * time.Minute))))
	retryAt := time.Now()
	backoff := 15 * time.Second
	delay := time.Duration(0)
	for {
		timer := time.NewTimer(delay)
		select {
		case <-stop:
			timer.Stop()
			return nil
		case <-timer.C:
		}
		delay = 30*time.Second + time.Duration(rand.Int64N(int64(5*time.Second)))
		s, err := openStore(dir, false)
		if err != nil {
			fmt.Fprintln(os.Stderr, "state busy or unavailable; retry deferred")
			continue
		}
		names, _, err := s.queue()
		captured := false
		now := time.Now()
		if err == nil && len(names) == 0 && !now.Before(nextCapture) && !now.Before(retryAt) {
			var r *report
			r, err = collectConfigured(inventory, selected, serviceName, binariesFile)
			if inventory {
				err = s.enqueueInventoryCapture(r, err)
			} else if err == nil {
				err = s.enqueue(r)
			}
			captured = err == nil
		}
		if err == nil && !now.Before(retryAt) && (len(names) > 0 || captured) {
			err = flush(s)
			if err == nil {
				backoff = 15 * time.Second
				retryAt = time.Now()
				if captured {
					cadence := interval
					if inventory && cadence < 6*time.Hour {
						baseline, err := s.readInventoryBaseline()
						if err != nil || !baseline.Supported {
							cadence = 6 * time.Hour
						}
					}
					nextCapture = time.Now().Add(cadence + time.Duration(rand.Int64N(int64(cadence/10))))
				} else {
					nextCapture = time.Now().Add(15 * time.Second)
				}
			}
		}
		s.close()
		if err != nil {
			fmt.Fprintln(os.Stderr, "observation/delivery deferred; retained local queue; check credentials, coverage or connectivity")
			retryAt = time.Now().Add(backoff + time.Duration(rand.Int64N(int64(backoff/2+1))))
			if backoff < 15*time.Minute {
				backoff *= 2
				if backoff > 15*time.Minute {
					backoff = 15 * time.Minute
				}
			}
		}
	}
}
