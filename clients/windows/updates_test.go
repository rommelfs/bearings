// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func sampleUpdates() *updateObservation {
	count := 1
	return &updateObservation{Source: "windows-update-agent-cache", Reboot: "present",
		Installed: updateGroup{Status: "ok", Total: &count, Updates: []updateEntry{{ID: "11111111-1111-4111-8111-111111111111", Revision: 2, Title: "Synthetic security update", KBs: []string{"KB5000001"}}}},
		Pending:   updateGroup{Status: "ok", Total: new(int), Updates: []updateEntry{}}}
}
func TestUpdateEvidenceBoundsAndUncertainty(t *testing.T) {
	data, _ := json.Marshal(sampleUpdates())
	decoded, err := decodeUpdates(data)
	if err != nil || decoded.Reboot != "present" || *decoded.Installed.Total != 1 || *decoded.Pending.Total != 0 {
		t.Fatal("valid update evidence refused", err)
	}
	for _, change := range []func(*updateObservation){
		func(o *updateObservation) { o.Installed.Status = "ok"; o.Installed.Truncated = true },
		func(o *updateObservation) { o.Pending.Status = "error" },
		func(o *updateObservation) { o.Pending.Updates = nil },
		func(o *updateObservation) {
			o.Installed.Updates = append(o.Installed.Updates, o.Installed.Updates[0])
			*o.Installed.Total = 2
		},
		func(o *updateObservation) { o.Installed.Updates[0].KBs = []string{"KB5000001<script>"} },
		func(o *updateObservation) { o.CacheLastSearch = "2099-01-01T00:00:00Z" },
		func(o *updateObservation) { o.Reboot = "false" },
		func(o *updateObservation) { o.Installed.Updates[0].ID = "unknown" },
	} {
		value := sampleUpdates()
		change(value)
		raw, _ := json.Marshal(value)
		if _, err := decodeUpdates(raw); err == nil {
			t.Fatal("invalid update evidence accepted")
		}
	}
	value := sampleUpdates()
	value.Installed.Status = "partial"
	*value.Installed.Total = 1000
	value.Installed.Truncated = true
	raw, _ := json.Marshal(value)
	if _, err := decodeUpdates(raw); err != nil {
		t.Fatal("explicit partial result refused", err)
	}
	for _, raw := range [][]byte{append(data, []byte(" {}")...), []byte(strings.Repeat("x", maxUpdateOutput+1))} {
		if _, err := decodeUpdates(raw); err == nil {
			t.Fatal("unbounded/trailing data accepted")
		}
	}
}
func TestUpdateTransportFailureNeverClaimsEmptySuccess(t *testing.T) {
	for _, state := range []string{"timeout", "unavailable"} {
		value := unavailableUpdates(state)
		if value.Reboot != "unknown" || value.Pending.Total != nil || value.Installed.Total != nil || value.Pending.Status != state {
			t.Fatal("failure looks like zero updates")
		}
	}
	var out updateOutput
	if _, err := out.Write(make([]byte, maxUpdateOutput)); err != nil {
		t.Fatal(err)
	}
	if _, err := out.Write([]byte("x")); err == nil || out.Len() != maxUpdateOutput {
		t.Fatal("output not bounded")
	}
}
func TestOversizedOptionalUpdatesPreserveRegistryReport(t *testing.T) {
	value := &report{Components: []component{{Name: strings.Repeat("x", maxBody-700)}}, OS: operatingSystem{WindowsUpdate: sampleUpdates(), RebootHint: "present"}}
	if err := fitWindowsUpdates(value); err != nil {
		t.Fatal("registry inventory blocked", err)
	}
	if value.OS.WindowsUpdate.Pending.Status != "unavailable" || value.OS.RebootHint != "unknown" {
		t.Fatal("oversized optional evidence not made explicit")
	}
	value.Components[0].Name = strings.Repeat("x", maxBody+1)
	if fitWindowsUpdates(value) == nil {
		t.Fatal("oversized registry inventory incorrectly accepted")
	}
}
