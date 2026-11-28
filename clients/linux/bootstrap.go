// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux || darwin

package main

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

type bootstrapRequest struct {
	Schema    string `json:"schema"`
	PublicKey string `json:"public_key"`
	RequestID string `json:"request_id"`
}
type bootstrapState struct {
	Server  string           `json:"server"`
	Fleet   string           `json:"fleet"`
	Request bootstrapRequest `json:"request"`
}

// Only the public retry context and a private one-use grant survive a failed request.
// The shared rollout bearer is never written to state or accepted through argv/env.
func bootstrap(s *store, server, ca string, input io.Reader) error {
	server, err := origin(server)
	if err != nil {
		return err
	}
	if s.config.DeviceID != "" {
		if s.config.URL != server {
			return errors.New("already enrolled at another origin")
		}
		if err = ready(s); err != nil {
			return err
		}
		// A crash after saving the receipt must not leave an unused-looking cached grant.
		if err = os.Remove(filepath.Join(s.dir, "bootstrap-grant.json")); err != nil && !os.IsNotExist(err) {
			return err
		}
		return output(map[string]string{"state": "already_enrolled", "device_id": s.config.DeviceID})
	}
	raw, err := io.ReadAll(io.LimitReader(input, 151))
	if err != nil || len(raw) > 150 {
		return errors.New("invalid rollout credential on stdin")
	}
	token := strings.TrimSpace(string(raw))
	parts := strings.Split(token, ".")
	if len(parts) != 2 || !uuidPattern.MatchString(parts[0]) || len(parts[1]) < 32 || len(parts[1]) > 64 {
		return errors.New("invalid rollout credential on stdin")
	}
	contextPath := filepath.Join(s.dir, "bootstrap.json")
	context := bootstrapState{Server: server, Fleet: parts[0], Request: bootstrapRequest{Schema: "bearings.agent.bootstrap.v1", PublicKey: s.public(), RequestID: newID()}}
	previous, err := safeRead(contextPath, 4096)
	if err == nil {
		if err = decode(previous, &context); err != nil {
			return err
		}
		if context.Server != server || context.Fleet != parts[0] || context.Request.PublicKey != s.public() || context.Request.Schema != "bearings.agent.bootstrap.v1" || !uuidPattern.MatchString(context.Request.RequestID) {
			return errors.New("another rollout is pending; use its original key or archive the abandoned bootstrap")
		}
	} else if os.IsNotExist(err) {
		if s.config.EnrollmentID != "" {
			return errors.New("manual enrollment already pending")
		}
		value, _ := json.Marshal(context)
		if err = writePrivate(contextPath, value); err != nil {
			return err
		}
	} else {
		return err
	}
	grantPath := filepath.Join(s.dir, "bootstrap-grant.json")
	response, err := safeRead(grantPath, 8192)
	if os.IsNotExist(err) {
		client, e := transport(ca)
		if e != nil {
			return e
		}
		payload, _ := json.Marshal(context.Request)
		defer client.CloseIdleConnections()
		var status int
		response, status, err = send(client, server, "/api/v1/agent/bootstrap/", "fleet:"+parts[0], s.key, payload, token)
		if err != nil && status == http.StatusForbidden {
			return errors.New("rollout key rejected; check whether it is invalid or expired and verify the rollout settings")
		}
	}
	if err != nil {
		return err
	}
	var g grant
	if err = decode(response, &g); err != nil {
		return err
	}
	returnedServer, err := origin(g.URL)
	if err != nil || returnedServer != server || g.PublicKey != s.public() || !g.RegisterHost || g.AssetID != "" {
		return errors.New("rollout grant has an unexpected origin or identity")
	}
	if err = writePrivate(grantPath, response); err != nil {
		return err
	}
	if err = enroll(s, grantPath, ca, true); err != nil {
		return err
	}
	if err = os.Remove(grantPath); err != nil {
		return err
	}
	return syncDir(s.dir)
}

func archiveBootstrap(s *store) (string, error) {
	if s.config.DeviceID != "" || s.config.EnrollmentID != "" || s.config.EnrollmentRequest != "" {
		return "", errors.New("device registration or enrollment exists; bootstrap state retained")
	}
	for _, name := range []string{"bootstrap-grant.json", "enrollment.json"} {
		if _, err := os.Lstat(filepath.Join(s.dir, name)); !os.IsNotExist(err) {
			return "", errors.New("grant or enrollment request exists or cannot be checked; bootstrap state retained")
		}
	}
	path := filepath.Join(s.dir, "bootstrap.json")
	raw, err := safeRead(path, 4096)
	if os.IsNotExist(err) {
		return "", nil
	}
	if err != nil {
		return "", errors.New("cannot read the pending bootstrap; state retained")
	}
	var attempt bootstrapState
	if decode(raw, &attempt) != nil || attempt.Request.Schema != "bearings.agent.bootstrap.v1" ||
		!uuidPattern.MatchString(attempt.Request.RequestID) || !uuidPattern.MatchString(attempt.Fleet) ||
		attempt.Request.PublicKey != s.public() {
		return "", errors.New("pending bootstrap identity is invalid; state retained")
	}
	name := "bootstrap-" + attempt.Request.RequestID + ".archived.json"
	target := filepath.Join(s.dir, name)
	if _, err := os.Lstat(target); !os.IsNotExist(err) {
		return "", errors.New("bootstrap archive already exists or cannot be checked; state retained")
	}
	if err := os.Rename(path, target); err != nil {
		return "", errors.New("could not archive the bootstrap; state retained")
	}
	return name, syncDir(s.dir)
}
