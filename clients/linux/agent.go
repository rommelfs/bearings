// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
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
	baseline, err := s.readInventoryBaseline()
	if err != nil {
		return err
	}
	for _, name := range names {
		path := filepath.Join(s.dir, "outbox", name)
		raw, err := safeRead(path, maxBody)
		if err != nil {
			return err
		}
		pending, err := readPendingObservation(raw)
		if err != nil {
			return err
		}
		expectedName := fmt.Sprintf("%020d_%s.json", pending.Sequence, pending.ReportID)
		if !uuidPattern.MatchString(pending.ReportID) || pending.Sequence < 1 || name != expectedName {
			return errors.New("invalid local report identity")
		}
		var headers http.Header
		response, status, err := sendWithHeaders(client, s.config.URL, reportPath, "device:"+s.config.DeviceID, s.key, raw, "", &headers)
		supportsChecks := headers.Get("Bearings-Inventory-Check") == "1"
		if err != nil {
			// A legacy receiver cannot admit the new format. Only automatic observations use it.
			if status == http.StatusForbidden && !supportsChecks && (pending.Check || pending.Extended) {
				if err = s.writeInventoryBaseline(inventoryBaseline{}); err != nil {
					return err
				}
				if err = removeQueuedReport(path); err != nil {
					return err
				}
				return errors.New("receiver requires legacy full inventory; a new capture is needed")
			}
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
		nextBaseline := pending.baselineAfterReceipt(baseline, supportsChecks, ack)
		if nextBaseline != baseline {
			if err = s.writeInventoryBaseline(nextBaseline); err != nil {
				return err
			}
			baseline = nextBaseline
		}
		saved, _ := json.Marshal(ack)
		if err = writePrivate(filepath.Join(s.dir, "receipt.json"), saved); err != nil {
			return err
		}
		if err = removeQueuedReport(path); err != nil {
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
func removeQueuedReport(path string) error {
	if err := os.Remove(path); err != nil {
		return err
	}
	return syncDir(filepath.Dir(path))
}

func validStatus(value string) bool {
	return value == "pending" || value == "applied" || value == "rejected" || value == "superseded"
}
func getStatus(s *store, id string) error {
	ack, err := reportStatus(s, id)
	if err != nil {
		return err
	}
	return output(ack)
}
func reportStatus(s *store, id string) (receipt, error) {
	if err := ready(s); err != nil {
		return receipt{}, err
	}
	if id == "" {
		raw, err := safeRead(filepath.Join(s.dir, "receipt.json"), 65536)
		if err != nil {
			return receipt{}, errors.New("no local receipt; provide --report UUID after a successful delivery")
		}
		var last receipt
		if err = decode(raw, &last); err != nil {
			return receipt{}, err
		}
		id = last.ReportID
	}
	if !uuidPattern.MatchString(id) {
		return receipt{}, errors.New("invalid report identifier")
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return receipt{}, err
	}
	payload, _ := json.Marshal(map[string]string{"schema": "bearings.agent.status.v1", "report_id": id})
	raw, _, err := send(client, s.config.URL, statusPath, "device:"+s.config.DeviceID, s.key, payload, "")
	if err != nil {
		return receipt{}, err
	}
	var ack receipt
	if err = decode(raw, &ack); err != nil {
		return receipt{}, err
	}
	if ack.Schema != "bearings.agent.receipt.v1" || ack.ReportID != id || !validStatus(ack.Status) {
		return receipt{}, errors.New("invalid status receipt")
	}
	return ack, nil
}
func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
