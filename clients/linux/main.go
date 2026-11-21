// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/rand/v2"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"
)

var version = "development"
var uuidPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type grant struct {
	RegisterHost bool   `json:"register_host"`
	Schema       string `json:"schema"`
	URL          string `json:"url"`
	Grant        string `json:"grant"`
	PublicKey    string `json:"public_key"`
	AssetID      string `json:"asset_id"`
	ExpiresAt    string `json:"expires_at"`
}
type enrolled struct {
	AssetID   string `json:"asset_id"`
	Schema    string `json:"schema"`
	DeviceID  string `json:"device_id"`
	ExpiresAt string `json:"expires_at"`
}
type receipt struct {
	Schema     string `json:"schema"`
	ReportID   string `json:"report_id"`
	Sequence   int64  `json:"sequence"`
	Hash       string `json:"body_sha256"`
	Status     string `json:"status"`
	Error      string `json:"error"`
	ReceivedAt string `json:"received_at"`
}
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
func output(value any) error {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(true)
	return encoder.Encode(value)
}
func enroll(s *store, path, ca string, registerHost bool) error {
	if s.config.DeviceID != "" {
		return errors.New("already enrolled; revoke and use a fresh state/key for controlled replacement")
	}
	raw, err := safeRead(path, 8192)
	if err != nil {
		return err
	}
	var g grant
	if err = decode(raw, &g); err != nil {
		return err
	}
	server, err := origin(g.URL)
	if err != nil {
		return err
	}
	parts := strings.Split(g.Grant, ".")
	if g.Schema != "bearings.agent.grant.v1" || g.PublicKey != s.public() || len(parts) != 2 || !uuidPattern.MatchString(parts[0]) || len(parts[1]) < 32 || len(parts[1]) > 64 || (!g.RegisterHost && !uuidPattern.MatchString(g.AssetID)) {
		return errors.New("grant identity or public key does not match this device")
	}
	expiry, err := time.Parse(time.RFC3339Nano, g.ExpiresAt)
	if err != nil || !expiry.After(time.Now()) {
		return errors.New("enrollment grant expired")
	}
	if s.config.EnrollmentID != "" && (s.config.EnrollmentID != parts[0] || s.config.URL != server) {
		return errors.New("a different enrollment is pending; inspect local state instead of replacing it")
	}
	if s.config.EnrollmentRequest == "" {
		s.config.EnrollmentID = parts[0]
		s.config.EnrollmentRequest = newID()
		s.config.URL = server
		s.config.CAFile = ca
		if err = s.save(); err != nil {
			return err
		}
	} else if ca != "" && ca != s.config.CAFile {
		if _, err = transport(ca); err != nil {
			return err
		}
		s.config.CAFile = ca
		if err = s.save(); err != nil {
			return err
		}
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return err
	}

	enrollmentBody := filepath.Join(s.dir, "enrollment.json")
	payload, err := safeRead(enrollmentBody, 16384)
	if os.IsNotExist(err) {
		value := map[string]any{"schema": "bearings.agent.enroll.v1", "request_id": s.config.EnrollmentRequest}
		if g.RegisterHost && !registerHost {
			return errors.New("this grant requests a new host; explicitly consent with --register-host")
		}
		if registerHost {
			host, err := networkClaim()
			if err != nil {
				return err
			}
			value["host"] = host
		}
		payload, err = json.Marshal(value)
		if err != nil {
			return err
		}
		if err = writePrivate(enrollmentBody, payload); err != nil {
			return err
		}
	} else if err != nil {
		return err
	}

	response, _, err := send(client, server, enrollmentPath, "enroll:"+parts[0], s.key, payload, g.Grant)
	if err != nil {
		return err
	}
	var result enrolled
	if err = decode(response, &result); err != nil {
		return err
	}
	if result.Schema != "bearings.agent.enrolled.v1" || !uuidPattern.MatchString(result.DeviceID) || !uuidPattern.MatchString(result.AssetID) || (g.AssetID != "" && result.AssetID != g.AssetID) {
		return errors.New("invalid enrollment receipt")
	}
	if _, err = time.Parse(time.RFC3339Nano, result.ExpiresAt); err != nil {
		return errors.New("invalid credential expiry")
	}
	s.config.DeviceID = result.DeviceID
	s.config.ExpiresAt = result.ExpiresAt
	if err = s.save(); err != nil {
		return err
	}
	return output(map[string]string{"state": "enrolled", "device_id": s.config.DeviceID, "expires_at": s.config.ExpiresAt, "asset_id": result.AssetID})
}
func ready(s *store) error {
	server, err := origin(s.config.URL)
	if err != nil {
		return errors.New("device not enrolled with a trusted HTTPS origin")
	}
	if server != s.config.URL || !uuidPattern.MatchString(s.config.DeviceID) {
		return errors.New("invalid enrollment state")
	}
	expiry, err := time.Parse(time.RFC3339Nano, s.config.ExpiresAt)
	if err != nil || !expiry.After(time.Now()) {
		return errors.New("device credential expired; controlled reenrollment is required")
	}
	return nil
}
func flush(s *store) error {
	if err := ready(s); err != nil {
		return err
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return err
	}
	names, _, err := s.queue()
	if err != nil {
		return err
	}
	for _, name := range names {
		path := filepath.Join(s.dir, "outbox", name)
		raw, err := safeRead(path, maxBody)
		if err != nil {
			return err
		}
		var pending report
		if err = decode(raw, &pending); err != nil {
			return err
		}
		expectedName := fmt.Sprintf("%020d_%s.json", pending.Sequence, pending.ReportID)
		if pending.Schema != tag || !uuidPattern.MatchString(pending.ReportID) || pending.Sequence < 1 || name != expectedName {
			return errors.New("invalid local report identity")
		}
		response, status, err := send(client, s.config.URL, reportPath, "device:"+s.config.DeviceID, s.key, raw, "")
		if err != nil {
			return err
		}
		var ack receipt
		if err = decode(response, &ack); err != nil {
			return err
		}
		if ack.Schema != "bearings.agent.receipt.v1" || ack.ReportID != pending.ReportID || ack.Sequence != pending.Sequence || ack.Hash != digest(raw) || !validStatus(ack.Status) {
			return errors.New("server receipt does not acknowledge the exact local report")
		}
		if status == 202 && ack.Status != "pending" {
			return errors.New("inconsistent server receipt")
		}
		saved, _ := json.Marshal(ack)
		if err = writePrivate(filepath.Join(s.dir, "receipt.json"), saved); err != nil {
			return err
		}
		if err = os.Remove(path); err != nil {
			return err
		}
		if err = syncDir(filepath.Dir(path)); err != nil {
			return err
		}
		if err = output(ack); err != nil {
			return err
		}
		if ack.Status == "rejected" {
			return errors.New("report retained by server but rejected for publication; inspect device status")
		}
	}
	return nil
}
func validStatus(value string) bool {
	return value == "pending" || value == "applied" || value == "rejected" || value == "superseded"
}
func getStatus(s *store, id string) error {
	if err := ready(s); err != nil {
		return err
	}
	if id == "" {
		raw, err := safeRead(filepath.Join(s.dir, "receipt.json"), 65536)
		if err != nil {
			return errors.New("no local receipt; provide --report UUID after a successful delivery")
		}
		var last receipt
		if err = decode(raw, &last); err != nil {
			return err
		}
		id = last.ReportID
	}
	if !uuidPattern.MatchString(id) {
		return errors.New("invalid report identifier")
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return err
	}
	payload, _ := json.Marshal(map[string]string{"schema": "bearings.agent.status.v1", "report_id": id})
	raw, _, err := send(client, s.config.URL, statusPath, "device:"+s.config.DeviceID, s.key, payload, "")
	if err != nil {
		return err
	}
	var ack receipt
	if err = decode(raw, &ack); err != nil {
		return err
	}
	if ack.Schema != "bearings.agent.receipt.v1" || ack.ReportID != id || !validStatus(ack.Status) {
		return errors.New("invalid status receipt")
	}
	return output(ack)
}
func run(args []string) error {
	if len(args) == 0 {
		return errors.New("use init, bootstrap, enroll, collect, report, enqueue, flush, status, watch or version")
	}
	if args[0] == "version" {
		fmt.Println(version)
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
		return watch(dir, *inventory, selected, *serviceName, *binariesFile, *interval)
	default:
		return errors.New("unknown command")
	}
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
			if err == nil {
				err = s.enqueue(r)
				captured = err == nil
			}
		}
		if err == nil && !now.Before(retryAt) && (len(names) > 0 || captured) {
			err = flush(s)
			if err == nil {
				backoff = 15 * time.Second
				retryAt = time.Now()
				if captured {
					nextCapture = time.Now().Add(interval + time.Duration(rand.Int64N(int64(interval/10))))
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

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
