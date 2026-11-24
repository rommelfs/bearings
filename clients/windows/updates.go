// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"regexp"
	"strconv"
	"time"
)

//go:embed updates.ps1
var updateScript string

const maxUpdateOutput = 700000
const maxUpdates = 250

var updateIDPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var kbPattern = regexp.MustCompile(`^KB[0-9]{4,9}$`)

type updateEntry struct {
	Hidden   bool     `json:"hidden"`
	ID       string   `json:"id"`
	Revision int      `json:"revision"`
	Title    string   `json:"title"`
	KBs      []string `json:"kbs"`
}
type updateGroup struct {
	Status    string        `json:"status"`
	Total     *int          `json:"total"`
	Truncated bool          `json:"truncated"`
	Updates   []updateEntry `json:"updates"`
}
type updateObservation struct {
	Source          string      `json:"source"`
	CacheLastSearch string      `json:"cache_last_search_at"`
	Reboot          string      `json:"reboot"`
	Installed       updateGroup `json:"installed"`
	Pending         updateGroup `json:"pending"`
}

func unavailableUpdates(status string) *updateObservation {
	group := updateGroup{Status: status, Updates: []updateEntry{}}
	return &updateObservation{Source: "windows-update-agent-cache", Reboot: "unknown", Installed: group, Pending: group}
}

// A bounded writer prevents a broken helper from consuming unbounded memory.
type updateOutput struct{ bytes.Buffer }

func (w *updateOutput) Write(p []byte) (int, error) {
	if w.Len()+len(p) > maxUpdateOutput {
		return 0, errors.New("update observation exceeds limit")
	}
	return w.Buffer.Write(p)
}

func decodeUpdates(raw []byte) (*updateObservation, error) {
	if len(raw) > maxUpdateOutput {
		return nil, errors.New("update observation exceeds limit")
	}
	var result updateObservation
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&result); err != nil {
		return nil, err
	}
	if decoder.Decode(new(any)) != io.EOF {
		return nil, errors.New("trailing update observation")
	}
	if result.Source != "windows-update-agent-cache" || (result.Reboot != "present" && result.Reboot != "not_observed" && result.Reboot != "unknown") {
		return nil, errors.New("unsupported update observation")
	}
	if result.CacheLastSearch != "" {
		date, err := time.Parse(time.RFC3339, result.CacheLastSearch)
		if err != nil || date.After(time.Now().Add(5*time.Minute)) {
			return nil, errors.New("invalid update cache time")
		}
	}
	for _, group := range []updateGroup{result.Installed, result.Pending} {
		if len(group.Updates) > maxUpdates || group.Updates == nil {
			return nil, errors.New("invalid update bounds")
		}
		switch group.Status {
		case "ok", "partial":
			if group.Total == nil || *group.Total < len(group.Updates) || *group.Total > 100000 || group.Truncated != (*group.Total > len(group.Updates)) || (group.Status == "ok" && group.Truncated) {
				return nil, errors.New("invalid update coverage")
			}
		case "error":
			if group.Total != nil || len(group.Updates) != 0 || group.Truncated {
				return nil, errors.New("invalid failed update observation")
			}
		default:
			return nil, errors.New("invalid update status")
		}
		seen := map[string]bool{}
		for _, entry := range group.Updates {
			if !clean(entry.Title, 240, true) || !updateIDPattern.MatchString(entry.ID) || entry.Revision < 1 || entry.Revision > 2147483647 || len(entry.KBs) > 16 || entry.KBs == nil {
				return nil, errors.New("invalid update entry")
			}
			key := entry.ID + ":" + strconv.Itoa(entry.Revision)
			if seen[key] {
				return nil, errors.New("duplicate update identity")
			}
			seen[key] = true
			kbs := map[string]bool{}
			for _, kb := range entry.KBs {
				if !kbPattern.MatchString(kb) || kbs[kb] {
					return nil, errors.New("invalid KB identity")
				}
				kbs[kb] = true
			}
		}
	}
	return &result, nil
}

// Optional update metadata must not block a valid registry inventory report.
func fitWindowsUpdates(value *report) error {
	raw, err := reportBytes(value)
	if value.OS.WindowsUpdate != nil && (err != nil || len(raw) > maxBody-1024) {
		value.OS.WindowsUpdate = unavailableUpdates("unavailable")
		value.OS.RebootHint = "unknown"
		_, err = reportBytes(value)
	}
	return err
}
