// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"net/http"
	"strconv"
)

type serverRefusal int

func (e serverRefusal) Error() string {
	return "server refused request (HTTP " + strconv.Itoa(int(e)) + "); local input retained"
}

func uninstallRequest(s *state, action string) (string, error) {
	const schema = "bearings.agent.uninstall.v1"
	server, err := origin(s.URL)
	if err != nil || server != s.URL || !uuid.MatchString(s.DeviceID) {
		return "", errors.New("device has no enrollment for uninstall")
	}
	client, err := transport(s.CAFile)
	if err != nil {
		return "", err
	}
	defer client.CloseIdleConnections()
	var result struct {
		Schema string `json:"schema"`
		Action string `json:"action"`
		Device string `json:"device_id"`
	}
	err = post(client, server, "/api/v1/agent/uninstall/", "device:"+s.DeviceID, s.key(),
		[]byte(`{"schema":"`+schema+`","action":"`+action+`"}`), "", &result)
	if action == "check" && (err == serverRefusal(http.StatusNotFound) || err == serverRefusal(http.StatusForbidden)) {
		return "none", nil
	}
	if err != nil {
		return "", err
	}
	if result.Schema != schema || result.Device != s.DeviceID ||
		(result.Action != "uninstall" && (action != "check" || result.Action != "none")) {
		return "", errors.New("invalid uninstall response")
	}
	return result.Action, nil
}
