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
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	tag         = "bearings.agent.v1"
	maxBody     = 1_000_000
	enrollPath  = "/api/v1/agent/enroll/"
	reportsPath = "/api/v1/agent/reports/"
	statusPath  = "/api/v1/agent/status/"
	covered     = `("@method" "@path" "@authority" "content-digest" "content-type" "x-bearings-key")`
)

var uuid = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var grantToken = regexp.MustCompile(`^[A-Za-z0-9_-]{32,64}$`)

func identifier() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func digest(body []byte) string {
	hash := sha256.Sum256(body)
	return hex.EncodeToString(hash[:])
}

func origin(raw string) (string, error) {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil ||
		u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || strings.Contains(raw, "#") ||
		(u.EscapedPath() != "" && u.EscapedPath() != "/") {
		return "", errors.New("use a trusted HTTPS origin without credentials, path, query or fragment")
	}
	host := strings.ToLower(u.Hostname())
	for _, c := range host {
		if c <= 32 || c >= 127 || strings.ContainsRune("%/\\", c) {
			return "", errors.New("use an ASCII HTTPS hostname")
		}
	}
	if port := u.Port(); port != "" {
		n, err := strconv.Atoi(port)
		if err != nil || n < 1 || n > 65535 {
			return "", errors.New("invalid HTTPS port")
		}
		if n != 443 {
			return "https://" + net.JoinHostPort(host, strconv.Itoa(n)), nil
		}
	}
	if strings.Contains(host, ":") {
		host = "[" + host + "]"
	}
	return "https://" + host, nil
}

// The fixed RFC 9421 profile shared with the Linux client and independently verified by Django.
func sign(req *http.Request, body []byte, key ed25519.PrivateKey, identity string, now time.Time, nonce string) {
	hash := sha256.Sum256(body)
	contentDigest := "sha-256=:" + base64.StdEncoding.EncodeToString(hash[:]) + ":"
	params := fmt.Sprintf(`%s;created=%d;keyid=%q;alg="ed25519";expires=%d;nonce=%q;tag=%q`,
		covered, now.Unix(), identity, now.Unix()+300, nonce, tag)
	base := fmt.Sprintf("\"@method\": POST\n\"@path\": %s\n\"@authority\": %s\n\"content-digest\": %s\n\"content-type\": application/json\n\"x-bearings-key\": %s\n\"@signature-params\": %s",
		req.URL.EscapedPath(), req.URL.Host, contentDigest, identity, params)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Content-Digest", contentDigest)
	req.Header.Set("X-Bearings-Key", identity)
	req.Header.Set("Signature-Input", "bearings="+params)
	req.Header.Set("Signature", "bearings=:"+base64.StdEncoding.EncodeToString(ed25519.Sign(key, []byte(base)))+":")
}

func transport(caFile string) (*http.Client, error) {
	roots, err := x509.SystemCertPool()
	if err != nil {
		return nil, errors.New("system certificate trust unavailable")
	}
	if caFile != "" {
		raw, err := readBounded(caFile, 1_000_000)
		if err != nil || !roots.AppendCertsFromPEM(raw) {
			return nil, errors.New("approved CA file is unreadable, oversized or invalid")
		}
	}
	return &http.Client{
		Timeout:       20 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		Transport: &http.Transport{
			DialContext:         (&net.Dialer{Timeout: 5 * time.Second}).DialContext,
			TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 10 * time.Second,
			MaxResponseHeaderBytes: 16_384, DisableCompression: true,
			TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots},
		},
	}, nil
}

func post(client *http.Client, server, path, identity string, key ed25519.PrivateKey, body []byte, bearer string, result any) error {
	if len(body) > maxBody {
		return errors.New("request exceeds the inventory size limit")
	}
	req, err := http.NewRequest(http.MethodPost, server+path, bytes.NewReader(body))
	if err != nil {
		return errors.New("invalid HTTPS destination")
	}
	sign(req, body, key, identity, time.Now(), identifier())
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	response, err := client.Do(req)
	if err != nil {
		return errors.New("HTTPS delivery failed; check connectivity and certificate trust")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusAccepted {
		return fmt.Errorf("server refused request (HTTP %d); local input retained", response.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 65_537))
	content, _, _ := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || len(raw) > 65_536 || content != "application/json" || json.Unmarshal(raw, result) != nil {
		return errors.New("invalid server response; local input retained")
	}
	return nil
}

func readBounded(path string, max int64) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > max {
		return nil, errors.New("file is not regular or exceeds bounds")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	raw, err := io.ReadAll(io.LimitReader(file, max+1))
	if err != nil || int64(len(raw)) > max {
		return nil, errors.New("could not read bounded file")
	}
	return raw, nil
}
