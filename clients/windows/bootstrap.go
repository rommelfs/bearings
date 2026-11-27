// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"net/http"
	"regexp"
	"strings"
	"time"
)

const bootstrapPath = "/api/v1/agent/bootstrap/"
const pendingRolloutMessage = "Another rollout is pending. Use its original key or archive the abandoned attempt after checking the server reservation."

var hostName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,179}$`)

type rolloutState struct {
	Server    string `json:"server"`
	Fleet     string `json:"fleet"`
	RequestID string `json:"request_id"`
	Grant     *grant `json:"grant,omitempty"`
}

func bootstrap(s *state, save func() error, code, ca, hostname string) (enrolled, error) {
	var result enrolled
	server, err := origin(defaultServer)
	if err != nil {
		return result, errors.New("download the Windows client built by your Bearings server")
	}
	if s.DeviceID != "" {
		return result, errors.New("this Windows account is already registered")
	}
	token := strings.TrimSpace(code)
	fleet, secret, _ := strings.Cut(token, ".")
	if !uuid.MatchString(fleet) || !grantToken.MatchString(secret) {
		return result, errors.New("Invalid rollout key format. Paste the complete key from Bearings.")
	}
	if !hostName.MatchString(hostname) {
		return result, errors.New("this Windows computer name cannot be registered in Bearings")
	}
	if s.Rollout == nil {
		if s.Pending != nil {
			return result, errors.New("another registration is pending; local identity retained")
		}
		s.Rollout = &rolloutState{Server: server, Fleet: fleet, RequestID: identifier()}
		if err := save(); err != nil {
			return result, err
		}
	}
	context := s.Rollout
	if context.Server != server || context.Fleet != fleet || !uuid.MatchString(context.RequestID) {
		return result, errors.New(pendingRolloutMessage)
	}
	if context.Grant == nil {
		client, err := transport(ca)
		if err != nil {
			return result, err
		}
		defer client.CloseIdleConnections()
		body := []byte(`{"schema":"bearings.agent.bootstrap.v1","public_key":"` + s.publicKey() + `","request_id":"` + context.RequestID + `"}`)
		var g grant
		if err = post(client, server, bootstrapPath, "fleet:"+fleet, s.key(), body, token, &g); err != nil {
			if err == serverRefusal(http.StatusForbidden) {
				return result, errors.New("Rollout key rejected (HTTP 403). Check whether the key is invalid or expired and confirm the rollout settings. To switch keys, check the server reservation before archiving.")
			}
			return result, err
		}
		returned, err := origin(g.URL)
		if err != nil || returned != server || !g.RegisterHost || g.PublicKey != s.publicKey() || g.AssetID != "" {
			return result, errors.New("rollout grant differs from the configured server or device")
		}
		context.Grant = &g
		if err := save(); err != nil {
			return result, err
		}
	}
	if !context.Grant.ExpiresAt.After(time.Now()) {
		return result, errors.New("The saved rollout grant has expired. Ask your Bearings administrator to reconcile the reservation. Device state retained.")
	}
	return enrollGrant(s, save, *context.Grant, ca, hostname)
}

// The archive is written before clearing the active attempt. A retry after a
// failed save must be able to reuse the identical archive.
func archiveBootstrap(s *state, save func() error, archive func(rolloutState) error) (bool, error) {
	if s.DeviceID != "" || s.Pending != nil || (s.Rollout != nil && s.Rollout.Grant != nil) {
		return false, errors.New("A device registration, enrollment request or grant exists. Ask your Bearings administrator to review it. Device state retained.")
	}
	attempt := s.Rollout
	if attempt == nil {
		return false, nil
	}
	if _, err := origin(attempt.Server); err != nil || !uuid.MatchString(attempt.Fleet) || !uuid.MatchString(attempt.RequestID) {
		return false, errors.New("Pending bootstrap identity could not be verified. Device state retained.")
	}
	if err := archive(*attempt); err != nil {
		return false, err
	}
	s.Rollout = nil
	if err := save(); err != nil {
		s.Rollout = attempt
		return false, err
	}
	return true, nil
}

func bootstrapArchiveMessage(archived bool) string {
	if archived {
		return "Bootstrap archived. Device key retained. Paste a new rollout key to register."
	}
	return "No pending bootstrap to archive."
}

func enrollCode(s *state, save func() error, code, ca, hostname string) (enrolled, error) {
	prefix, _, _ := strings.Cut(strings.TrimSpace(code), ".")
	if prefix == "bearings-windows-v1" || prefix == "bearings-enroll-v1" {
		g, err := readGrant(code)
		if err != nil {
			return enrolled{}, err
		}
		return enroll(s, save, g, ca)
	}
	return bootstrap(s, save, code, ca, hostname)
}

// Check compatibility input shape without placing a bearer on the command line.
func rolloutInput(code string) bool {
	fleet, secret, _ := strings.Cut(strings.TrimSpace(code), ".")
	return uuid.MatchString(fleet) && grantToken.MatchString(secret)
}
