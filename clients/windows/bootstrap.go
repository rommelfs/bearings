// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"regexp"
	"strings"
)

const bootstrapPath = "/api/v1/agent/bootstrap/"

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
		return result, errors.New("paste a Bearings rollout key")
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
		return result, errors.New("another rollout is pending; use its original key")
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
	return enrollGrant(s, save, *context.Grant, ca, hostname)
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
