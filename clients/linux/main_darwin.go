// SPDX-License-Identifier: AGPL-3.0-or-later

package main

import (
	"bytes"
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const launchLabel = "lu.circl.bearings.inventory"

var macServer string // HTTPS origin embedded by prepare-clients.

type macInstall struct {
	app, binary, launch, state string
}

func localMac() (macInstall, error) {
	home, err := os.UserHomeDir()
	if err != nil || !filepath.IsAbs(home) || os.Geteuid() == 0 {
		return macInstall{}, errors.New("run Bearings as the macOS user who will send reports")
	}
	app := filepath.Join(home, "Applications", "Bearings.app")
	return macInstall{
		app:    app,
		binary: filepath.Join(app, "Contents", "MacOS", "bearings-macos"),
		launch: filepath.Join(home, "Library", "LaunchAgents", launchLabel+".plist"),
		state:  filepath.Join(home, "Library", "Application Support", "Bearings Inventory"),
	}, nil
}

func launchTarget() string { return "gui/" + strconv.Itoa(os.Getuid()) }

func launchctl(args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, "/bin/launchctl", args...).CombinedOutput()
	if err != nil {
		message := strings.TrimSpace(string(out))
		return fmt.Errorf("launchctl %s failed: %s", args[0], message)
	}
	return nil
}

func plistEscape(value string) string {
	var buf bytes.Buffer
	_ = xml.EscapeText(&buf, []byte(value))
	return buf.String()
}

func (m macInstall) enable() error {
	if _, err := origin(macServer); err != nil {
		return errors.New("download a configured Bearings app from your server")
	}
	if err := m.installApp(); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(m.launch), 0700); err != nil {
		return err
	}
	plist := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>%s</string>
<key>ProgramArguments</key><array><string>%s</string><string>periodic</string></array>
<key>StartInterval</key><integer>900</integer>
<key>RunAtLoad</key><true/>
<key>ProcessType</key><string>Background</string>
</dict></plist>`, launchLabel, plistEscape(m.binary))
	if err := writePrivate(m.launch, []byte(plist)); err != nil {
		return err
	}
	if launchctl("print", launchTarget()+"/"+launchLabel) == nil {
		return nil
	}
	if err := launchctl("enable", launchTarget()+"/"+launchLabel); err != nil {
		return err
	}
	if err := launchctl("bootstrap", launchTarget(), m.launch); err != nil {
		return err
	}
	return launchctl("print", launchTarget()+"/"+launchLabel)
}

func (m macInstall) uninstall(s *store, action string) error {
	if _, err := os.Lstat(m.app); err == nil {
		if err := macBundleIdentity(m.app); err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if s.config.DeviceID != "" {
		// Persist intent before the server revokes the credential. A lost response
		// or interrupted local cleanup can then finish with the idempotent local action.
		if err := writePrivate(filepath.Join(m.state, "retirement"), []byte("requested")); err != nil {
			return err
		}
		if _, err := uninstallRequest(s, action); err != nil {
			return fmt.Errorf("could not confirm deregistration; local installation retained: %w", err)
		}
	}
	if err := removeIfPresent(m.launch); err != nil {
		return err
	}
	if err := os.RemoveAll(m.app); err != nil {
		return err
	}
	if err := os.RemoveAll(m.state); err != nil {
		return err
	}
	if launchctl("print", launchTarget()+"/"+launchLabel) == nil {
		return launchctl("bootout", launchTarget()+"/"+launchLabel)
	}
	return nil
}

func removeIfPresent(path string) error {
	if err := os.Remove(path); !os.IsNotExist(err) {
		return err
	}
	return nil
}

func (m macInstall) periodic(s *store, compact bool) (result error) {
	if compact {
		if _, err := safeRead(filepath.Join(m.state, "retirement"), 32); err == nil {
			return m.uninstall(s, "local")
		} else if !os.IsNotExist(err) {
			return err
		}
		if action, err := uninstallRequest(s, "check"); err == nil && action == "uninstall" {
			return m.uninstall(s, "acknowledge")
		}
		defer func() {
			if _, err := safeRead(filepath.Join(s.dir, "updates-disabled"), 32); os.IsNotExist(err) {
				result = errors.Join(result, m.update(s))
			} else if err != nil {
				result = errors.Join(result, err)
			}
		}()
	}
	if err := ready(s); err != nil {
		return err
	}
	names, _, err := s.queue()
	if err != nil {
		return err
	}
	if len(names) > 0 {
		if err := flush(s); err != nil {
			return err
		}
	}
	observation, captureErr := collectMac()
	if compact {
		err = s.enqueueInventoryCapture(observation, captureErr)
	} else if captureErr != nil {
		return captureErr
	} else {
		baseline, baselineErr := s.readInventoryBaseline()
		if baselineErr != nil {
			return baselineErr
		}
		observation.applyCoverageCapabilities(baseline)
		err = s.enqueue(observation)
	}
	if err != nil {
		return err
	}
	if err := flush(s); err != nil {
		return fmt.Errorf("local report retained or server rejected publication: %w", err)
	}
	return nil
}

func (m macInstall) setup(s *store, input io.Reader) error {
	if _, err := origin(macServer); err != nil {
		return errors.New("download a configured Bearings app from your server")
	}
	if err := m.installApp(); err != nil {
		return err
	}
	if s.config.DeviceID == "" {
		if err := bootstrap(s, macServer, "", input); err != nil {
			return err
		}
	}
	if err := ready(s); err != nil {
		return err
	}
	if s.config.URL != macServer {
		return errors.New("this account is already registered with a different Bearings server")
	}
	if err := m.enable(); err != nil {
		return fmt.Errorf("registered, but automatic reports could not be enabled: %w", err)
	}
	fmt.Println("Registered. The launch agent will send a report now and every 15 minutes while you are signed in.")
	return nil
}

func run(args []string) error {
	if len(args) == 1 && args[0] == "version" {
		fmt.Println(version)
		return nil
	}
	m, err := localMac()
	if err != nil {
		return err
	}
	if len(args) == 0 {
		return macGUI(m)
	}
	if len(args) > 1 {
		return errors.New("expected a single command")
	}
	return m.run(args[0], os.Stdin)
}

func (m macInstall) run(action string, input io.Reader) error {
	if action == "coverage" {
		issues := []macCoverageIssue{}
		total := 0
		r, err := collectMacWithCoverage(func(issue macCoverageIssue) {
			total++
			if len(issues) < 50 {
				issues = append(issues, issue)
			}
		})
		if err != nil {
			return err
		}
		return output(map[string]any{
			"complete": r.Complete, "gaps": *r.Gaps,
			"issues": issues, "additional_issues": total - len(issues),
		})
	}
	if action == "collect" {
		r, err := collectMac()
		if err != nil {
			return err
		}
		return output(r)
	}
	s, err := openStore(m.state, action == "install")
	if err != nil {
		return err
	}
	defer s.close()
	switch action {
	case "install":
		return m.setup(s, input)
	case "archive-bootstrap":
		name, err := archiveBootstrap(s)
		if err == nil {
			if name == "" {
				fmt.Println("No pending rollout to archive.")
			} else {
				fmt.Println("Pending rollout archived. Retry installation with a current rollout key.")
			}
		}
		return err
	case "report", "periodic":
		return m.periodic(s, action == "periodic")
	case "status":
		return getStatus(s, "")
	case "flush":
		return flush(s)
	case "update":
		return m.update(s)
	case "updates-on":
		return removeIfPresent(filepath.Join(s.dir, "updates-disabled"))
	case "updates-off":
		return writePrivate(filepath.Join(s.dir, "updates-disabled"), []byte("disabled"))
	case "uninstall":
		return m.uninstall(s, "local")
	default:
		return errors.New("use install, collect, coverage, report, flush, status, update, updates-on, updates-off, archive-bootstrap, uninstall or version")
	}
}

func dialog(script string, values ...string) (string, error) {
	args := append([]string{"-e", script}, values...)
	out, err := exec.Command("/usr/bin/osascript", args...).Output()
	return strings.TrimRight(string(out), "\r\n"), err
}

func macGUI(m macInstall) error {
	for {
		action, err := dialog(`set choice to choose from list {"Register and enable reports", "Send report", "Check report status", "Check for client update", "Enable automatic client updates", "Disable automatic client updates", "Archive failed registration", "Uninstall"} with title "Bearings" with prompt "Choose an action." default items {"Register and enable reports"}
if choice is false then return ""
return item 1 of choice`)
		if err != nil || action == "" {
			return err
		}
		message := ""
		switch action {
		case "Register and enable reports":
			input := ""
			s, err := openStore(m.state, true)
			if err == nil {
				enrolled := s.config.DeviceID != ""
				s.close()
				if !enrolled {
					input, err = dialog(`on run argv
return text returned of (display dialog ("Server: " & item 1 of argv & return & "Paste the organization rollout key.") default answer "" with title "Bearings" with hidden answer)
end run`, macServer)
					if err != nil {
						continue
					}
				}
				err = m.run("install", strings.NewReader(input+"\n"))
			}
			if err != nil {
				message = err.Error()
			} else {
				message = "Registered. Automatic reports run every 15 minutes while signed in."
			}
		case "Check report status":
			message = m.guiStatus()
		case "Send report":
			err = m.run("report", nil)
			message = "Report received. Check report status to see whether the server applied it."
		case "Check for client update":
			err = m.run("update", nil)
			message = "Update check completed."
		case "Enable automatic client updates":
			err = m.run("updates-on", nil)
			message = "Automatic client updates are enabled."
		case "Disable automatic client updates":
			err = m.run("updates-off", nil)
			message = "Automatic client updates are disabled."
		case "Archive failed registration", "Uninstall":
			confirm, confirmErr := dialog(`on run argv
display dialog (item 1 of argv) buttons {"Cancel", "Continue"} default button "Cancel" cancel button "Cancel" with title "Bearings"
return "confirmed"
end run`, action+"?")
			if confirmErr != nil || confirm != "confirmed" {
				continue
			}
			if action == "Uninstall" {
				err = m.run("uninstall", nil)
				message = "Bearings was deregistered and removed."
			} else {
				err = m.run("archive-bootstrap", nil)
				message = "Registration state checked. You can retry with a current rollout key."
			}
		}
		if err != nil {
			message = err.Error()
		}
		_, _ = dialog(`on run argv
display dialog (item 1 of argv) with title "Bearings" buttons {"OK"} default button "OK"
end run`, message)
		if action == "Uninstall" && err == nil {
			return nil
		}
	}
}

func (m macInstall) guiStatus() string {
	s, err := openStore(m.state, false)
	if err != nil {
		return err.Error()
	}
	defer s.close()
	ack, err := reportStatus(s, "")
	if err != nil {
		return err.Error()
	}
	schedule := "Automatic reporting is inactive."
	if launchctl("print", launchTarget()+"/"+launchLabel) == nil {
		schedule = "Automatic reporting is active while signed in."
	}
	message := "Report status: " + ack.Status + ". " + schedule
	if ack.Error != "" {
		message += " " + ack.Error
	}
	return message
}
