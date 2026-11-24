// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"strings"
	"time"
)

const maxQueue = 64
const windowsGrant = "bearings.agent.grant.windows.v1"

var defaultServer string // Set when the publisher builds an executable for its HTTPS origin.

type grant struct {
	Schema       string    `json:"schema"`
	URL          string    `json:"url"`
	Token        string    `json:"grant"`
	PublicKey    string    `json:"public_key"`
	AssetID      string    `json:"asset_id"`
	RegisterHost bool      `json:"register_host"`
	ExpiresAt    time.Time `json:"expires_at"`
}
type enrolled struct {
	Schema    string    `json:"schema"`
	DeviceID  string    `json:"device_id"`
	AssetID   string    `json:"asset_id"`
	ExpiresAt time.Time `json:"expires_at"`
}
type receipt struct {
	Schema   string `json:"schema"`
	ID       string `json:"report_id"`
	Sequence int64  `json:"sequence"`
	Hash     string `json:"body_sha256"`
	Status   string `json:"status"`
}
type pendingEnrollment struct {
	Identity string          `json:"identity"`
	Body     json.RawMessage `json:"body"`
}

// State retains the Python reference's DPAPI JSON format and exact outbox bytes.
type state struct {
	Seed      []byte             `json:"seed"`
	Counter   int64              `json:"counter"`
	Queue     []string           `json:"queue"`
	CAFile    string             `json:"ca_file,omitempty"`
	URL       string             `json:"url,omitempty"`
	Pending   *pendingEnrollment `json:"pending,omitempty"`
	Rollout   *rolloutState      `json:"rollout,omitempty"`
	DeviceID  string             `json:"device_id,omitempty"`
	ExpiresAt *time.Time         `json:"expires_at,omitempty"`
	Receipt   *receipt           `json:"receipt,omitempty"`
}

func initialState() state {
	seed := make([]byte, ed25519.SeedSize)
	_, _ = rand.Read(seed)
	return state{Seed: seed, Queue: []string{}}
}

func (s *state) valid() bool {
	return len(s.Seed) == ed25519.SeedSize && s.Queue != nil && len(s.Queue) <= maxQueue && s.Counter >= 0 &&
		(s.DeviceID == "" || (uuid.MatchString(s.DeviceID) && s.ExpiresAt != nil))
}

func (s *state) key() ed25519.PrivateKey { return ed25519.NewKeyFromSeed(s.Seed) }

func (s *state) publicKey() string {
	return base64.StdEncoding.EncodeToString(s.key().Public().(ed25519.PublicKey))
}

func (s *state) ready() error {
	if !uuid.MatchString(s.DeviceID) || s.ExpiresAt == nil || !s.ExpiresAt.After(time.Now()) {
		return errors.New("device not enrolled or credential expired; state retained")
	}
	return nil
}

func readGrant(code string) (grant, error) {
	var g grant
	value, ok := strings.CutPrefix(strings.TrimSpace(code), "bearings-enroll-v1.")
	expected := "bearings.agent.grant.v1"
	if !ok {
		value, ok = strings.CutPrefix(strings.TrimSpace(code), "bearings-windows-v1.")
		expected = windowsGrant
	}
	if !ok || len(value) > 16_000 {
		return g, errors.New("invalid registration code")
	}
	data, err := base64.RawURLEncoding.Strict().DecodeString(value)
	if err != nil || json.Unmarshal(data, &g) != nil || g.Schema != expected {
		return g, errors.New("invalid registration code")
	}
	return g, nil
}

func enroll(s *state, save func() error, g grant, ca string) (enrolled, error) {
	return enrollGrant(s, save, g, ca, "")
}

func enrollGrant(s *state, save func() error, g grant, ca, hostname string) (enrolled, error) {
	var result enrolled
	if s.DeviceID != "" {
		return result, errors.New("already enrolled; use reviewed replacement procedure")
	}
	tokenID, secret, _ := strings.Cut(g.Token, ".")
	claim := g.Schema == windowsGrant
	newHost := hostname != ""
	if !newHost && s.Rollout != nil {
		return result, errors.New("another rollout is pending; use its original key")
	}
	if (claim && g.PublicKey != "") || (!claim && (g.Schema != "bearings.agent.grant.v1" || g.PublicKey != s.publicKey())) ||
		g.RegisterHost != newHost || (newHost && (claim || g.AssetID != "" || s.Rollout == nil)) ||
		(!newHost && !uuid.MatchString(g.AssetID)) || !g.ExpiresAt.After(time.Now()) ||
		!uuid.MatchString(tokenID) || !grantToken.MatchString(secret) {
		return result, errors.New("use an unexpired registration code bound to this key and an existing asset")
	}
	server, err := origin(g.URL)
	if err != nil {
		return result, err
	}
	if claim || defaultServer != "" {
		configured, err := origin(defaultServer)
		if err != nil {
			return result, errors.New("download the Windows client built by your Bearings server")
		}
		if configured != server {
			return result, errors.New("this registration code belongs to a different Bearings server")
		}
		server = configured
	}
	identity := "enroll:" + tokenID
	if s.Pending != nil {
		previous, err := origin(s.URL)
		if err != nil || previous != server || s.Pending.Identity != identity {
			return result, errors.New("another enrollment is pending; local state retained")
		}
	} else {
		body := `{"schema":"bearings.agent.enroll.v1","request_id":"` + identifier() + `"}`
		if claim {
			body = `{"schema":"bearings.agent.enroll.windows.v1","request_id":"` + identifier() +
				`","public_key":"` + s.publicKey() + `"}`
		}
		if newHost {
			// bootstrap validates the hostname before saving the exact signed request.
			body = `{"schema":"bearings.agent.enroll.v1","request_id":"` + identifier() +
				`","host":{"hostname":"` + hostname + `","addresses":[]}}`
		}
		s.Pending = &pendingEnrollment{Identity: identity, Body: json.RawMessage(body)}
	}
	if claim {
		s.CAFile = ""
	} else if ca != "" {
		s.CAFile = ca
	}
	s.URL = server
	if err := save(); err != nil {
		return result, err
	}
	client, err := transport(s.CAFile)
	if err != nil {
		return result, err
	}
	defer client.CloseIdleConnections()
	if err := post(client, s.URL, enrollPath, identity, s.key(), s.Pending.Body, g.Token, &result); err != nil {
		return result, err
	}
	if result.Schema != "bearings.agent.enrolled.v1" || !uuid.MatchString(result.DeviceID) ||
		!uuid.MatchString(result.AssetID) || (!newHost && result.AssetID != g.AssetID) || !result.ExpiresAt.After(time.Now()) {
		return result, errors.New("invalid enrollment receipt; pending state retained")
	}
	s.DeviceID, s.ExpiresAt, s.Pending = result.DeviceID, &result.ExpiresAt, nil
	if newHost {
		s.Rollout = nil
	}
	return result, save()
}

func enqueue(s *state, save func() error, value *report) error {
	if len(s.Queue) >= maxQueue || s.Counter >= math.MaxInt64-1 {
		return errors.New("outbox full or sequence exhausted; retained input requires review")
	}
	value.Sequence = s.Counter + 1
	raw, err := reportBytes(value)
	if err != nil {
		return err
	}
	s.Counter = value.Sequence
	s.Queue = append(s.Queue, string(raw))
	return save()
}

func requestClient(s *state) (*http.Client, string, error) {
	if err := s.ready(); err != nil {
		return nil, "", err
	}
	server, err := origin(s.URL)
	if err != nil {
		return nil, "", err
	}
	client, err := transport(s.CAFile)
	return client, server, err
}

func exactReceipt(value receipt, id string, sequence int64, hash string) bool {
	if value.Schema != "bearings.agent.receipt.v1" || value.ID != id || value.Sequence != sequence || value.Hash != hash {
		return false
	}
	switch value.Status {
	case "pending", "applied", "rejected", "superseded":
		return true
	}
	return false
}

func flush(s *state, save func() error) (*receipt, error) {
	if err := s.ready(); err != nil {
		return nil, err
	}
	if len(s.Queue) == 0 {
		return nil, nil
	}
	client, server, err := requestClient(s)
	if err != nil {
		return nil, err
	}
	defer client.CloseIdleConnections()
	var last *receipt
	for len(s.Queue) > 0 {
		raw := []byte(s.Queue[0])
		var queued struct {
			ID       string `json:"report_id"`
			Sequence int64  `json:"sequence"`
		}
		if len(raw) > maxBody || json.Unmarshal(raw, &queued) != nil || !uuid.MatchString(queued.ID) || queued.Sequence <= 0 {
			return nil, errors.New("queued report is invalid; local input retained")
		}
		result := new(receipt)
		if err := post(client, server, reportsPath, "device:"+s.DeviceID, s.key(), raw, "", result); err != nil {
			return nil, err
		}
		if !exactReceipt(*result, queued.ID, queued.Sequence, digest(raw)) {
			return nil, errors.New("receipt does not acknowledge exact queued report")
		}
		s.Receipt = result
		s.Queue[0] = ""
		s.Queue = s.Queue[1:]
		if err := save(); err != nil {
			return nil, err
		}
		if result.Status == "rejected" {
			return nil, errors.New("report rejected during processing; check status and device history")
		}
		last = result
		if len(s.Queue) > 0 {
			time.Sleep(11 * time.Second)
		}
	}
	return last, nil
}

func status(s *state) (receipt, error) {
	var result receipt
	if s.Receipt == nil || !uuid.MatchString(s.Receipt.ID) {
		return result, errors.New("no previous receipt")
	}
	client, server, err := requestClient(s)
	if err != nil {
		return result, err
	}
	defer client.CloseIdleConnections()
	body := []byte(`{"schema":"bearings.agent.status.v1","report_id":"` + s.Receipt.ID + `"}`)
	if err := post(client, server, statusPath, "device:"+s.DeviceID, s.key(), body, "", &result); err != nil {
		return result, err
	}
	if !exactReceipt(result, s.Receipt.ID, s.Receipt.Sequence, s.Receipt.Hash) {
		return result, errors.New("status receipt differs from acknowledged report")
	}
	return result, nil
}
