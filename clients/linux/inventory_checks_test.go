// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func TestInventoryCaptureQueuesFullOnlyWhenChanged(t *testing.T) {
	s, err := openStore(t.TempDir()+"/state", true)
	if err != nil {
		t.Fatal(err)
	}
	defer s.close()
	gaps := []string{}
	r := &report{Schema: tag, Scope: "system-packages", Complete: true, Gaps: &gaps, ReportID: newID(), ObservedAt: "2026-11-27T09:00:00Z"}
	r.Components = []component{{Key: "dpkg:example:amd64", Version: "1.0"}}
	queue := func(r *report, failure error) []byte {
		t.Helper()
		if err := s.enqueueInventoryCapture(r, failure); err != nil {
			t.Fatal(err)
		}
		names, _, err := s.queue()
		if err != nil || len(names) != 1 {
			t.Fatalf("expected one queued capture, got %v (%v)", names, err)
		}
		path := filepath.Join(s.dir, "outbox", names[0])
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := removeQueuedReport(path); err != nil {
			t.Fatal(err)
		}
		return raw
	}

	legacy, err := readPendingObservation(queue(r, nil))
	if err != nil || legacy.Extended || legacy.Check {
		t.Fatalf("expected legacy full report, got %+v (%v)", legacy, err)
	}
	baseline := legacy.baselineAfterReceipt(inventoryBaseline{}, true, receipt{Status: "pending"})
	if err := s.writeInventoryBaseline(baseline); err != nil {
		t.Fatal(err)
	}
	r.ReportID, r.Gaps = newID(), &gaps
	full, err := readPendingObservation(queue(r, nil))
	if err != nil || !full.Extended || full.Check || full.Fingerprint == "" {
		t.Fatalf("expected full report with coverage, got %+v (%v)", full, err)
	}
	baseline = full.baselineAfterReceipt(baseline, true, receipt{Status: "pending"})
	if err := s.writeInventoryBaseline(baseline); err != nil {
		t.Fatal(err)
	}
	r.ReportID, r.ObservedAt = newID(), "2026-11-27T09:15:00Z"
	var check inventoryCheck
	raw := queue(r, nil)
	if err := json.Unmarshal(raw, &check); err != nil || check.BaselineID != full.ReportID || check.Schema != inventoryCheckSchema || check.Gaps == nil || len(check.Gaps) != 0 {
		t.Fatalf("expected a compact unchanged receipt request, got %s (%v)", raw, err)
	}
	r.ReportID, r.Components[0].Version = newID(), "1.1"
	changed, err := readPendingObservation(queue(r, nil))
	if err != nil || changed.Check || changed.Fingerprint == full.Fingerprint {
		t.Fatalf("expected changed full report, got %+v (%v)", changed, err)
	}
	check = inventoryCheck{}
	raw = queue(nil, errors.New("test package collection failure"))
	if err := json.Unmarshal(raw, &check); err != nil || check.BaselineID != "" || !slices.Equal(check.Gaps, []string{"packages"}) {
		t.Fatalf("expected coverage failure without a baseline, got %s (%v)", raw, err)
	}
	recovery := pendingObservation{Check: true}.baselineAfterReceipt(baseline, true, receipt{Status: "rejected", Error: fullInventoryRequired})
	if !recovery.Supported || recovery.ReportID != "" {
		t.Fatalf("expected a fresh full report after a baseline miss, got %+v", recovery)
	}
}
