// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/json"
	"errors"
	"regexp"
	"time"
	"unicode/utf8"
)

const osKey = `SOFTWARE\Microsoft\Windows NT\CurrentVersion`
const uninstallKey = `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`
const maxComponents = 5000

var digits = regexp.MustCompile(`^[0-9]+$`)

type evidence struct {
	Kind      string `json:"kind"`
	Key       string `json:"registry_key"`
	View      string `json:"view"`
	Publisher string `json:"publisher"`
	Edition   string `json:"edition"`
	Release   string `json:"release"`
}

type component struct {
	Key          string   `json:"key"`
	Manager      string   `json:"manager"`
	Name         string   `json:"name"`
	Version      string   `json:"version"`
	Architecture string   `json:"architecture"`
	Windows      evidence `json:"windows"`
}

type operatingSystem struct {
	ID           string `json:"id"`
	Version      string `json:"version"`
	Architecture string `json:"architecture"`
	Kernel       string `json:"kernel"`
	KernelScope  string `json:"kernel_scope"`
	RebootHint   string `json:"reboot_hint"`
}

type report struct {
	Schema     string          `json:"schema"`
	ID         string          `json:"report_id"`
	Sequence   int64           `json:"sequence"`
	ObservedAt time.Time       `json:"observed_at"`
	Scope      string          `json:"scope"`
	Complete   bool            `json:"complete"`
	OS         operatingSystem `json:"os"`
	Components []component     `json:"components"`
	Services   []struct{}      `json:"services"`
}

func clean(value string, limit int, allowEmpty bool) bool {
	if (!allowEmpty && value == "") || !utf8.ValidString(value) || utf8.RuneCountInString(value) > limit {
		return false
	}
	for _, r := range value {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}

func newComponent(key, name, version string, windows evidence) (component, error) {
	if !clean(name, 128, false) || !clean(version, 120, true) || !clean(windows.Key, 1024, false) ||
		!clean(windows.Publisher, 255, true) || !clean(windows.Edition, 120, true) || !clean(windows.Release, 120, true) {
		return component{}, errors.New("inventory field is malformed or exceeds the report bounds")
	}
	return component{Key: key, Manager: "win-reg", Name: name, Version: version, Architecture: "all", Windows: windows}, nil
}

func reportBytes(value *report) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil || len(raw) > maxBody {
		return nil, errors.New("inventory exceeds the report size limit")
	}
	return raw, nil
}
