// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/json"
	"encoding/pem"
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
