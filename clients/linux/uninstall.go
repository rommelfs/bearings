// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"errors"
	"net/http"
)

func uninstallRequest(s *store, action string) (string, error) {
	const schema = "bearings.agent.uninstall.v1"
	server, err := origin(s.config.URL)
	if err != nil || server != s.config.URL || !uuidPattern.MatchString(s.config.DeviceID) {
		return "", errors.New("device has no enrollment for uninstall")
	}
	client, err := transport(s.config.CAFile)
	if err != nil {
		return "", err
	}
	defer client.CloseIdleConnections()
	raw, code, err := send(client, server, "/api/v1/agent/uninstall/", "device:"+s.config.DeviceID, s.key,
		[]byte(`{"schema":"`+schema+`","action":"`+action+`"}`), "")
	if action == "check" && (code == http.StatusNotFound || code == http.StatusForbidden) {
		return "none", nil
	}
	if err != nil {
		return "", err
	}
	var result struct {
		Schema string `json:"schema"`
		Action string `json:"action"`
		Device string `json:"device_id"`
	}
	if decode(raw, &result) != nil || result.Schema != schema || result.Device != s.config.DeviceID ||
		(result.Action != "uninstall" && (action != "check" || result.Action != "none")) {
		return "", errors.New("invalid uninstall response")
	}
	return result.Action, nil
}
