// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"crypto/ed25519"
	"encoding/json"
	"encoding/pem"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"golang.org/x/text/cases"
)

// Fixed seed and expected signature were produced by the independent Python RFC 9421 library.
func TestSignatureVector(t *testing.T) {
	seed := make([]byte, 32)
	for i := range seed {
		seed[i] = byte(i)
	}
	body := []byte(`{"reference":"cross-language-test"}`)
	req, err := http.NewRequest("POST", "https://bearings.example:9441"+reportsPath, nil)
	if err != nil {
		t.Fatal(err)
	}
	sign(req, body, ed25519.NewKeyFromSeed(seed), "device:12345678-1234-4234-8234-123456789abc",
		time.Unix(1700000000, 0), "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
	if got := req.Header.Get("Signature"); got != "bearings=:6RUeJqY1me+GuPixUXZdqDwrSm48fdJmcH/USrjEf4F3Z55JcYx+GOqZ5Bk72ePh2fTEqwgEo9kZKFEJuF6NCw==:" {
		t.Fatal("signature differs from independent oracle")
	}
	if got, err := origin("https://Example.org:443/"); err != nil || got != "https://example.org" {
		t.Fatal("RFC 9421 authority must omit the HTTPS default port")
	}
	if result := cases.Fold().String("Straße İ"); result != "strasse i\u0307" {
		t.Fatal("registry identity must match the receiver's Unicode case folding")
	}
}

func TestHTTPSDeliveryRetainsExactQueuedBytes(t *testing.T) {
	s := initialState()
	expires := time.Now().Add(time.Hour).UTC()
	s.DeviceID, s.ExpiresAt = identifier(), &expires
	value := &report{ID: identifier(), Schema: tag}
	if err := enqueue(&s, func() error { return nil }, value); err != nil {
		t.Fatal(err)
	}
	queued := s.Queue[0]
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, err := io.ReadAll(r.Body)
		if err != nil || string(raw) != queued || r.URL.Path != reportsPath || r.Header.Get("X-Bearings-Key") != "device:"+s.DeviceID {
			t.Error("retry differs from queued input")
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(receipt{Schema: "bearings.agent.receipt.v1", ID: value.ID,
			Sequence: value.Sequence, Hash: digest(raw), Status: "pending"})
	}))
	defer server.Close()
	s.URL = server.URL
	if _, err := flush(&s, func() error { return nil }); err == nil || len(s.Queue) != 1 || s.Queue[0] != queued {
		t.Fatal("untrusted TLS must preserve exact pending data")
	}
	ca := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	s.CAFile = ca
	result, err := flush(&s, func() error { return nil })
	if err != nil || result == nil || result.Status != "pending" || len(s.Queue) != 0 {
		t.Fatalf("trusted retry failed: %v", err)
	}
	result.Sequence++
	if exactReceipt(*result, value.ID, value.Sequence, digest([]byte(queued))) {
		t.Fatal("mismatched receipt accepted")
	}
}

func TestEnrollmentRetryRetainsRequestIdentity(t *testing.T) {
	s := initialState()
	g := grant{Schema: "bearings.agent.grant.v1", PublicKey: s.publicKey(),
		Token:   identifier() + ".public-test-token-of-at-least-32-characters",
		AssetID: identifier(), ExpiresAt: time.Now().Add(time.Hour)}
	requests := make(chan string, 2)
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if r.URL.Path != enrollPath || r.Header.Get("Authorization") != "Bearer "+g.Token || err != nil {
			t.Error("unexpected enrollment request")
		}
		requests <- string(body)
		if len(requests) == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(enrolled{Schema: "bearings.agent.enrolled.v1", DeviceID: identifier(),
			AssetID: g.AssetID, ExpiresAt: g.ExpiresAt})
	}))
	defer server.Close()
	g.URL = server.URL
	ca := filepath.Join(t.TempDir(), "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	save := func() error { return nil }
	if _, err := enroll(&s, save, g, ca); err == nil || s.Pending == nil || s.DeviceID != "" {
		t.Fatal("failed enrollment must preserve the pending request")
	}
	if _, err := enroll(&s, save, g, ""); err != nil || s.Pending != nil || s.DeviceID == "" {
		t.Fatalf("retry failed: %v", err)
	}
	if len(requests) != 2 || <-requests != <-requests {
		t.Fatal("enrollment retry changed the authenticated request body")
	}
}

func TestPythonStateFormat(t *testing.T) {
	prior := []byte(`{"seed":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=","counter":3,"queue":["{\"sequence\":3,\"name\":\"caf\\u00e9\"}"],"url":"https://example.org","ca_file":"","pending":{"identity":"enroll:12345678-1234-4234-8234-123456789abc","body":{"schema":"bearings.agent.enroll.v1","request_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}}}`)
	var s state
	if err := json.Unmarshal(prior, &s); err != nil || !s.valid() {
		t.Fatalf("Python state cannot be opened: %v", err)
	}
	if s.Queue[0] != `{"sequence":3,"name":"caf\u00e9"}` ||
		string(s.Pending.Body) != `{"schema":"bearings.agent.enroll.v1","request_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}` {
		t.Fatal("previous pending bytes changed")
	}
}
