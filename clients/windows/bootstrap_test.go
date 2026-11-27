// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestRolloutRegistersNewHostAndResumesEnrollment(t *testing.T) {
	old := defaultServer
	defer func() { defaultServer = old }()
	s := initialState()
	fleet, grantID, assetID, deviceID := identifier(), identifier(), identifier(), identifier()
	rolloutToken := fleet + ".synthetic-rollout-bearer-1234567890"
	enrollmentToken := grantID + ".synthetic-enrollment-bearer-1234567890"
	publicKey := s.publicKey()
	var mu sync.Mutex
	var bootstrapCount int
	var enrollmentBodies []string
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		body, err := io.ReadAll(req.Body)
		if err != nil {
			t.Error(err)
		}
		w.Header().Set("Content-Type", "application/json")
		switch req.URL.Path {
		case bootstrapPath:
			bootstrapCount++
			if req.Header.Get("Authorization") != "Bearer "+rolloutToken ||
				req.Header.Get("X-Bearings-Key") != "fleet:"+fleet ||
				!strings.Contains(string(body), publicKey) {
				t.Error("bootstrap did not present the rollout token and signed local identity")
			}
			json.NewEncoder(w).Encode(grant{Schema: "bearings.agent.grant.v1", URL: defaultServer,
				Token: enrollmentToken, PublicKey: publicKey, RegisterHost: true, ExpiresAt: time.Now().Add(time.Hour)})
		case enrollPath:
			enrollmentBodies = append(enrollmentBodies, string(body))
			if req.Header.Get("Authorization") != "Bearer "+enrollmentToken ||
				req.Header.Get("X-Bearings-Key") != "enroll:"+grantID ||
				!strings.Contains(string(body), `"host":{"hostname":"example-windows","addresses":[]}`) {
				t.Error("redeem did not request the new host with the issued grant")
			}
			if len(enrollmentBodies) == 1 {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			json.NewEncoder(w).Encode(enrolled{Schema: "bearings.agent.enrolled.v1", DeviceID: deviceID,
				AssetID: assetID, ExpiresAt: time.Now().Add(time.Hour)})
		default:
			t.Error("unexpected request path")
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()
	defaultServer = server.URL
	ca := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	save := func() error {
		raw, err := json.Marshal(&s)
		if strings.Contains(string(raw), rolloutToken) {
			t.Fatal("shared rollout token persisted in device state")
		}
		return err
	}
	if _, err := bootstrap(&s, save, rolloutToken, ca, "example-windows"); err == nil || s.Pending == nil || s.Rollout == nil {
		t.Fatal("failed first request must preserve the pending grant and signed enrollment body")
	}
	result, err := bootstrap(&s, save, rolloutToken, ca, "example-windows")
	if err != nil || result.AssetID != assetID || s.DeviceID != deviceID || s.Pending != nil || s.Rollout != nil {
		t.Fatalf("rollout retry failed to enroll and clear its pending state: %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if bootstrapCount != 1 || len(enrollmentBodies) != 2 || enrollmentBodies[0] != enrollmentBodies[1] {
		t.Fatal("retry repeated bootstrap or changed the exact enrollment input")
	}
}

func TestUninstallExchangeUsesTheConfiguredDevice(t *testing.T) {
	s := initialState()
	s.DeviceID = identifier()
	var calls int
	var mu sync.Mutex
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		calls++
		var body map[string]string
		if r.URL.Path != "/api/v1/agent/uninstall/" ||
			r.Header.Get("X-Bearings-Key") != "device:"+s.DeviceID ||
			r.Header.Get("Signature") == "" || json.NewDecoder(r.Body).Decode(&body) != nil {
			t.Error("uninstall request did not use the enrolled device signature")
		}
		if calls == 1 {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		result := map[string]string{"schema": body["schema"], "device_id": s.DeviceID, "action": "uninstall"}
		if body["action"] != "check" {
			result["device_id"] = identifier()
		}
		json.NewEncoder(w).Encode(result)
	}))
	defer server.Close()
	s.URL, s.CAFile = server.URL, filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(s.CAFile, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	if result, err := uninstallRequest(&s, "check"); err != nil || result != "none" {
		t.Fatalf("older servers must leave reporting enabled: %q, %v", result, err)
	}
	if result, err := uninstallRequest(&s, "check"); err != nil || result != "uninstall" {
		t.Fatalf("own request was not delivered: %q, %v", result, err)
	}
	if _, err := uninstallRequest(&s, "acknowledge"); err == nil {
		t.Fatal("accepted an acknowledgment for another device")
	}
}

func TestArchiveBootstrapPreservesIdentityAndPendingStateOnFailure(t *testing.T) {
	s := initialState()
	key := s.publicKey()
	attempt := &rolloutState{Server: "https://bearings.example", Fleet: identifier(), RequestID: identifier()}
	s.Rollout = attempt
	var writes []rolloutState
	archive := func(value rolloutState) error {
		writes = append(writes, value)
		return nil
	}
	fail := func() error { return errors.New("synthetic save failure") }
	ok := func() error { return nil }
	attempt.Grant = &grant{}
	if archived, err := archiveBootstrap(&s, ok, archive); err == nil || archived || len(writes) != 0 {
		t.Fatal("archive allowed when a grant was retained")
	}
	attempt.Grant = nil
	if archived, err := archiveBootstrap(&s, fail, archive); err == nil || archived || s.Rollout != attempt {
		t.Fatal("failed state save discarded the pending request")
	}
	if archived, err := archiveBootstrap(&s, ok, archive); err != nil || !archived || s.Rollout != nil {
		t.Fatal("pending attempt was not archived")
	}
	if len(writes) != 2 || writes[0] != writes[1] || writes[1].RequestID != attempt.RequestID || s.publicKey() != key {
		t.Fatal("archive changed the attempt or device key")
	}
}

func TestBootstrapExplainsRejectedRolloutKey(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()
	old := defaultServer
	defaultServer = server.URL
	defer func() { defaultServer = old }()
	ca := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	s := initialState()
	token := identifier() + ".synthetic-rollout-bearer-1234567890"
	_, err := bootstrap(&s, func() error { return nil }, token, ca, "example-windows")
	if err == nil || !strings.Contains(err.Error(), "invalid or expired") || strings.Contains(err.Error(), token) || s.Rollout == nil || s.Rollout.Grant != nil {
		t.Fatalf("unexpected rollout denial or pending state: %v", err)
	}
}
