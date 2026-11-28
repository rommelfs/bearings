// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var packageName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9+_.-]{0,127}$`)
var archName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`)

func parsePackages(raw []byte, manager string) ([]component, error) {
	scanner := bufio.NewScanner(bytes.NewReader(raw))
	scanner.Buffer(make([]byte, 4096), 8192)
	var out []component
	keys := map[string]bool{}
	for scanner.Scan() {
		fields := strings.Split(scanner.Text(), "\t")
		if manager == "dpkg" {
			if len(fields) != 4 && len(fields) != 6 {
				return nil, errors.New("malformed dpkg output")
			}
			if fields[0] != "installed" {
				continue
			}
			fields = fields[1:]
		}
		if manager == "rpm" && len(fields) == 3 && fields[0] == "gpg-pubkey" {
			continue
		}
		var source *packageSource
		if manager == "dpkg" && len(fields) == 5 {
			if !packageName.MatchString(fields[3]) || len(fields[4]) == 0 || len(fields[4]) > 120 || strings.ContainsAny(fields[4], "\r\n\x00") {
				return nil, errors.New("invalid source package metadata")
			}
			source = &packageSource{Name: fields[3], Version: fields[4]}
			fields = fields[:3]
		}
		if len(fields) != 3 || !packageName.MatchString(fields[0]) || !archName.MatchString(fields[2]) || len(fields[1]) == 0 || len(fields[1]) > 120 || strings.ContainsAny(fields[1], "\r\n\x00") {
			return nil, errors.New("package identity/version exceeds the supported contract")
		}
		c := component{Source: source, Manager: manager, Name: fields[0], Version: fields[1], Architecture: fields[2]}
		c.Key = manager + ":" + c.Name + ":" + c.Architecture
		out = append(out, c)
		if len(out) > 5000 {
			return nil, errors.New("more than 5000 installed packages; no partial snapshot produced")
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if len(out) == 0 {
		return nil, errors.New("empty package database is not a complete software observation")
	}
	counts := map[string]int{}
	for _, c := range out {
		counts[c.Key]++
	}
	for i := range out {
		c := &out[i]
		if manager == "rpm" && (counts[c.Key] > 1 || strings.HasPrefix(c.Name, "kernel")) {
			c.Key += "@" + c.Version
		}
		if len(c.Key) > 255 {
			return nil, errors.New("package instance identity exceeds the bounded profile")
		}
		if keys[c.Key] {
			return nil, errors.New("duplicate package instance; no ambiguous snapshot published")
		}
		keys[c.Key] = true
	}

	sort.Slice(out, func(i, j int) bool { return out[i].Key < out[j].Key })
	return out, nil
}
func packages() ([]component, error) {
	if _, err := os.Stat("/var/lib/dpkg/status"); err == nil {
		raw, err := command("/usr/bin/dpkg-query", "-W", "-f=${db:Status-Status}\t${Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n")
		if err != nil {
			return nil, err
		}
		return parsePackages(raw, "dpkg")
	}
	if _, err := os.Stat("/usr/bin/rpm"); err == nil {
		raw, err := command("/usr/bin/rpm", "-qa", "--queryformat", "%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n")
		if err != nil {
			return nil, err
		}
		return parsePackages(raw, "rpm")
	}
	return nil, errors.New("supported dpkg or RPM package database not found")
}
func osRelease(raw []byte) map[string]string {
	values := map[string]string{}
	for _, line := range strings.Split(string(raw), "\n") {
		k, v, found := strings.Cut(line, "=")
		if !found || (k != "ID" && k != "VERSION_ID") {
			continue
		}
		v = strings.TrimSpace(v)
		if len(v) >= 2 && ((v[0] == '"' && v[len(v)-1] == '"') || (v[0] == '\'' && v[len(v)-1] == '\'')) {
			v = v[1 : len(v)-1]
		}
		if len(v) > 0 && len(v) <= 120 && !strings.ContainsAny(v, "\r\n\x00") {
			values[k] = v
		}
	}
	return values
}
func uts(b []int8) string {
	var out []byte
	for _, v := range b {
		if v == 0 {
			break
		}
		out = append(out, byte(v))
	}
	return string(out)
}
func kernelScope() string {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/usr/bin/systemd-detect-virt", "--container", "--quiet")
	cmd.Env = []string{"PATH=/usr/bin:/bin", "LC_ALL=C"}
	_, err := cmd.Output()
	if err == nil {
		return "shared"
	}
	var exit *exec.ExitError
	if errors.As(err, &exit) && exit.ExitCode() == 1 && len(exit.Stderr) == 0 && ctx.Err() == nil {
		return "host"
	}
	return "unknown"
}
func operating() operatingSystem {
	result := operatingSystem{ID: "unknown", Version: "unknown", Architecture: "unknown", Kernel: "unknown", KernelScope: kernelScope(), RebootHint: "unknown"}
	if raw, err := readBounded("/etc/os-release", 65536); err == nil {
		v := osRelease(raw)
		if v["ID"] != "" {
			result.ID = v["ID"]
		}
		if v["VERSION_ID"] != "" {
			result.Version = v["VERSION_ID"]
		}
	}
	var u syscall.Utsname
	if syscall.Uname(&u) == nil {
		result.Architecture = uts(u.Machine[:])
		result.Kernel = uts(u.Release[:])
	}
	if _, err := os.Stat("/var/run/reboot-required"); err == nil {
		result.RebootHint = "present"
	} else if os.IsNotExist(err) {
		result.RebootHint = "not_observed"
	}
	return result
}
func nginxName(s string) bool {
	return s == "nginx" || strings.HasPrefix(s, "nginx-") || strings.HasPrefix(s, "libnginx-mod-")
}
func collect(inventory bool, selected []string, serviceName string) (*report, error) {
	if (inventory && (len(selected) > 0 || serviceName != "")) || (!inventory && len(selected) == 0 && serviceName == "") || (len(selected) > 0 && serviceName != "") {
		return nil, errors.New("choose exactly one scope: --inventory, --service nginx, or --package NAME")
	}
	if serviceName != "" && serviceName != "nginx" {
		return nil, errors.New("only the explicitly supported nginx service profile is available")
	}
	all, err := packages()
	if err != nil {
		return nil, err
	}
	r := &report{Schema: tag, ReportID: newID(), Sequence: 1, ObservedAt: time.Now().UTC().Format(time.RFC3339Nano), Scope: "system-packages", Complete: true, OS: operating(), Services: []service{}}
	// A failed network enumeration must not discard a valid software inventory.
	// Omission preserves the last server-side network observation and its age.
	gaps := []string{}
	if host, err := networkClaim(); err == nil {
		r.Host = &host
	} else {
		fmt.Fprintln(os.Stderr, "network observation unavailable:", err)
		gaps = append(gaps, "network")
	}
	if serviceName != "" {
		r.Scope = "nginx-packages"
		r.Services = append(r.Services, nginx())
		for _, c := range all {
			if nginxName(c.Name) {
				r.Components = append(r.Components, c)
			}
		}
	} else if len(selected) > 0 {
		r.Scope = "selected-packages"
		r.Complete = false
		wanted := map[string]bool{}
		for _, name := range selected {
			if !packageName.MatchString(name) {
				return nil, errors.New("invalid exact package selector")
			}
			wanted[name] = false
		}
		for _, c := range all {
			if _, ok := wanted[c.Name]; ok {
				r.Components = append(r.Components, c)
				wanted[c.Name] = true
			}
		}
		for _, found := range wanted {
			if !found {
				return nil, errors.New("requested package is not in the installed database; absence is not a removal report")
			}
		}
	} else {
		r.Components = all
	}
	if len(r.Components) == 0 {
		return nil, errors.New("no installed packages in this explicit scope; no report produced")
	}
	if inventory {
		var complete bool
		r.Applications, complete = collectApplications("/etc/bearings-linux/application-probes.json")
		if !complete {
			gaps = append(gaps, "applications")
		}
		r.Gaps = &gaps
	}
	r.ObservedAt = time.Now().UTC().Format(time.RFC3339Nano)
	return r, nil
}

// Compare executable identities only. This does not assess library mappings or prove a patch effective.
func nginx() service {
	result := service{Name: "nginx", State: "unknown", Coverage: "unavailable"}
	raw, err := command("/usr/bin/systemctl", "show", "nginx.service", "--property=MainPID", "--property=LoadState")
	if err != nil {
		return result
	}
	properties := map[string]string{}
	for _, line := range strings.Split(string(raw), "\n") {
		name, value, ok := strings.Cut(line, "=")
		if ok {
			properties[name] = value
		}
	}
	if properties["LoadState"] != "loaded" {
		return result
	}
	pid, err := strconv.Atoi(properties["MainPID"])
	if err != nil {
		return result
	}
	if pid == 0 {
		return service{Name: "nginx", State: "not_running", Coverage: "main_process_only"}
	}
	match, err := sameExecutable(pid, "/usr/sbin/nginx")
	if err != nil {
		return result
	}
	result.Coverage = "main_process_only"
	result.State = "executable_matches"
	if !match {
		result.State = "different_executable"
	}
	// Main-process-only is always disclosed, even when its executable matches.
	return result
}
func processStart(raw []byte) (string, error) {
	end := strings.LastIndex(string(raw), ")")
	if end < 0 {
		return "", errors.New("invalid process status")
	}
	parts := strings.Fields(string(raw[end+1:]))
	if len(parts) < 20 {
		return "", errors.New("incomplete process status")
	}
	return parts[19], nil
}
func sameExecutable(pid int, installed string) (bool, error) {
	if pid <= 0 || filepath.Clean(installed) != "/usr/sbin/nginx" {
		return false, errors.New("unsupported executable profile")
	}
	return compareExecutable("/proc", pid, installed)
}
func compareExecutable(procRoot string, pid int, installed string) (bool, error) {
	statPath := filepath.Join(procRoot, strconv.Itoa(pid), "stat")
	before, err := readBounded(statPath, 8192)
	if err != nil {
		return false, err
	}
	start, err := processStart(before)
	if err != nil {
		return false, err
	}
	target, err := os.Readlink(filepath.Join(procRoot, strconv.Itoa(pid), "exe"))
	if err != nil {
		return false, err
	}
	if strings.TrimSuffix(target, " (deleted)") != installed {
		return false, errors.New("main process is not the configured nginx executable")
	}
	running, err := os.Stat(filepath.Join(procRoot, strconv.Itoa(pid), "exe"))
	if err != nil {
		return false, err
	}
	disk, err := os.Stat(installed)
	if err != nil {
		return false, err
	}
	after, err := readBounded(statPath, 8192)
	if err != nil {
		return false, err
	}
	again, err := processStart(after)
	if err != nil || again != start {
		return false, errors.New("process changed while observing")
	}
	return os.SameFile(running, disk), nil
}
