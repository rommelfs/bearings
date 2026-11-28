// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"
)

const inventoryCheckSchema = "bearings.agent.inventory-check.v1"
const fullInventoryRequired = "Full inventory required"

type inventoryCheck struct {
	Schema     string   `json:"schema"`
	ReportID   string   `json:"report_id"`
	Sequence   int64    `json:"sequence"`
	ObservedAt string   `json:"observed_at"`
	BaselineID string   `json:"baseline_id,omitempty"`
	Gaps       []string `json:"gaps"`
}

type inventoryBaseline struct {
	Supported   bool   `json:"supported"`
	ReportID    string `json:"report_id"`
	Fingerprint string `json:"fingerprint"`
}

// The cache is separate from enrollment and counter state and is safe to lose.
func (s *store) readInventoryBaseline() (inventoryBaseline, error) {
	var baseline inventoryBaseline
	raw, err := safeRead(filepath.Join(s.dir, "inventory-baseline.json"), 1024)
	if os.IsNotExist(err) {
		return baseline, nil
	}
	if err != nil {
		return baseline, err
	}
	if err = decode(raw, &baseline); err != nil {
		return inventoryBaseline{}, errors.New("invalid local inventory baseline")
	}
	return baseline, nil
}

func (s *store) writeInventoryBaseline(baseline inventoryBaseline) error {
	raw, err := json.Marshal(baseline)
	if err != nil {
		return err
	}
	return writePrivate(filepath.Join(s.dir, "inventory-baseline.json"), raw)
}

func (r report) inventoryFingerprint() (string, error) {
	r.ReportID, r.ObservedAt, r.Sequence = "", "", 0
	r.Applications = slices.Clone(r.Applications)
	slices.SortFunc(r.Applications, func(a, b component) int { return strings.Compare(a.Key, b.Key) })
	raw, err := json.Marshal(r)
	return digest(raw), err
}

func (s *store) enqueueInventoryCapture(r *report, captureErr error) error {
	baseline, err := s.readInventoryBaseline()
	if err != nil {
		return err
	}
	if !baseline.Supported {
		if captureErr != nil {
			return captureErr
		}
		r.Gaps = nil
		return s.enqueue(r)
	}
	check := inventoryCheck{Schema: inventoryCheckSchema, ReportID: newID(), Gaps: []string{}}
	if captureErr != nil {
		fmt.Fprintln(os.Stderr, "inventory collection incomplete:", captureErr)
		check.ObservedAt = time.Now().UTC().Format(time.RFC3339Nano)
		check.Gaps = []string{"packages"}
	} else {
		fingerprint, err := r.inventoryFingerprint()
		if err != nil {
			return err
		}
		if baseline.ReportID == "" || baseline.Fingerprint != fingerprint {
			return s.enqueue(r)
		}
		check.ReportID, check.ObservedAt, check.BaselineID = r.ReportID, r.ObservedAt, baseline.ReportID
		if r.Gaps != nil {
			check.Gaps = *r.Gaps
		}
	}
	return s.enqueueObservation(check.ReportID, &check.Sequence, &check)
}

type pendingObservation struct {
	ReportID    string
	Sequence    int64
	Check       bool
	Extended    bool
	Fingerprint string
}

func readPendingObservation(raw []byte) (pendingObservation, error) {
	var envelope struct {
		Schema string `json:"schema"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return pendingObservation{}, err
	}
	switch envelope.Schema {
	case inventoryCheckSchema:
		var check inventoryCheck
		err := decode(raw, &check)
		return pendingObservation{ReportID: check.ReportID, Sequence: check.Sequence, Check: true}, err
	case tag:
		var r report
		if err := decode(raw, &r); err != nil {
			return pendingObservation{}, err
		}
		item := pendingObservation{ReportID: r.ReportID, Sequence: r.Sequence, Extended: r.Gaps != nil}
		if item.Extended && r.Complete && (r.Scope == "system-packages" || r.Scope == "macos-machine") {
			var err error
			item.Fingerprint, err = r.inventoryFingerprint()
			return item, err
		}
		return item, nil
	default:
		return pendingObservation{}, errors.New("invalid local report schema")
	}
}

func (p pendingObservation) baselineAfterReceipt(current inventoryBaseline, supported bool, ack receipt) inventoryBaseline {
	if !supported {
		return inventoryBaseline{}
	}
	if p.Check {
		if ack.Status == "rejected" && ack.Error == fullInventoryRequired {
			return inventoryBaseline{Supported: true}
		}
		return current
	}
	if p.Fingerprint != "" && (ack.Status == "pending" || ack.Status == "applied") {
		return inventoryBaseline{Supported: true, ReportID: p.ReportID, Fingerprint: p.Fingerprint}
	}
	return inventoryBaseline{Supported: true}
}
