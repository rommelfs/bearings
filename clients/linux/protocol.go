// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const maxBody = 1000000
const tag = "bearings.agent.v1"
const enrollmentPath = "/api/v1/agent/enroll/"
const reportPath = "/api/v1/agent/reports/"
const statusPath = "/api/v1/agent/status/"
const covered = `("@method" "@path" "@authority" "content-digest" "content-type" "x-bearings-key")`

func newID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic("operating-system randomness unavailable")
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}
func digest(body []byte) string { d := sha256.Sum256(body); return hex.EncodeToString(d[:]) }
func origin(raw string) (string, error) {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") || u.Opaque != "" {
		return "", errors.New("use a trusted HTTPS origin without credentials, path, query or fragment")
	}
	u.Host = strings.ToLower(u.Host)
	u.Path = ""
	return u.String(), nil
}

// This is the fixed RFC 9421 profile emitted by this client, not a general signature parser.
// The server verifies it with an independent RFC 9421 library and checks body integrity separately.
func sign(req *http.Request, body []byte, key ed25519.PrivateKey, identity string, now time.Time, nonce string) {
	d := sha256.Sum256(body)
	contentDigest := "sha-256=:" + base64.StdEncoding.EncodeToString(d[:]) + ":"
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Content-Digest", contentDigest)
	req.Header.Set("X-Bearings-Key", identity)
	params := fmt.Sprintf(`%s;created=%d;keyid=%q;alg="ed25519";expires=%d;nonce=%q;tag=%q`, covered, now.Unix(), identity, now.Unix()+300, nonce, tag)
	signatureBase := fmt.Sprintf("\"@method\": POST\n\"@path\": %s\n\"@authority\": %s\n\"content-digest\": %s\n\"content-type\": application/json\n\"x-bearings-key\": %s\n\"@signature-params\": %s", req.URL.EscapedPath(), strings.ToLower(req.URL.Host), contentDigest, identity, params)
	req.Header.Set("Signature-Input", "bearings="+params)
	req.Header.Set("Signature", "bearings=:"+base64.StdEncoding.EncodeToString(ed25519.Sign(key, []byte(signatureBase)))+":")
}

func transport(caFile string) (*http.Client, error) {
	roots, err := x509.SystemCertPool()
	if err != nil {
		return nil, errors.New("system trust store unavailable")
	}
	if caFile != "" {
		stat, err := os.Stat(caFile)
		if err != nil || !stat.Mode().IsRegular() || stat.Mode().Perm()&0022 != 0 {
			return nil, errors.New("CA file must be a regular file protected against untrusted writes")
		}
		raw, err := readBounded(caFile, 1024*1024)
		if err != nil || len(raw) > 1024*1024 || !roots.AppendCertsFromPEM(raw) {
			return nil, errors.New("explicit CA file is unreadable or invalid")
		}
	}
	return &http.Client{Timeout: 20 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }, Transport: &http.Transport{
		Proxy: http.ProxyFromEnvironment, DialContext: (&net.Dialer{Timeout: 5 * time.Second}).DialContext,
		TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 10 * time.Second, MaxResponseHeaderBytes: 16384,
		DisableCompression: true, MaxIdleConns: 2, TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots},
	}}, nil
}
func send(client *http.Client, server, path, identity string, key ed25519.PrivateKey, body []byte, bearer string) ([]byte, int, error) {
	return sendWithHeaders(client, server, path, identity, key, body, bearer, nil)
}

func sendWithHeaders(client *http.Client, server, path, identity string, key ed25519.PrivateKey, body []byte, bearer string, headers *http.Header) ([]byte, int, error) {
	if len(body) > maxBody {
		return nil, 0, errors.New("report exceeds one-megabyte contract; no partial report sent")
	}
	req, err := http.NewRequest("POST", server+path, bytes.NewReader(body))
	if err != nil {
		return nil, 0, errors.New("invalid destination")
	}
	sign(req, body, key, identity, time.Now(), newID())
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	response, err := client.Do(req)
	if err != nil {
		return nil, 0, errors.New("HTTPS delivery failed; check connectivity, trusted CA and configured proxy")
	}
	defer response.Body.Close()
	if headers != nil {
		*headers = response.Header
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 65537))
	if err != nil || len(raw) > 65536 {
		return nil, response.StatusCode, errors.New("invalid or oversized server response")
	}
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusAccepted {
		return nil, response.StatusCode, fmt.Errorf("server refused request (HTTP %d); input remains local", response.StatusCode)
	}
	return raw, response.StatusCode, nil
}
func decode(raw []byte, value any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		return errors.New("invalid structured data")
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return errors.New("trailing structured data")
	}
	return nil
}
