// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bytes"
	"encoding/binary"
	"encoding/xml"
	"strings"
	"time"
	"unicode/utf16"
)

func taskXML(sid, program, directory string, start time.Time) string {
	escape := func(value string) string {
		var out strings.Builder
		xml.EscapeText(&out, []byte(value))
		return out.String()
	}
	return `<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Send Windows machine inventory to Bearings every six hours.</Description></RegistrationInfo>
<Triggers><TimeTrigger><Enabled>true</Enabled><StartBoundary>` +
		start.Format("2006-01-02T15:04:05") + `</StartBoundary><Repetition><Interval>PT6H</Interval></Repetition></TimeTrigger></Triggers>
<Principals><Principal id="Reporter"><UserId>` + escape(sid) + `</UserId>
<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable>
<ExecutionTimeLimit>PT30M</ExecutionTimeLimit></Settings>
<Actions Context="Reporter"><Exec><Command>` + escape(program) + `</Command><Arguments>report</Arguments>
<WorkingDirectory>` + escape(directory) + `</WorkingDirectory></Exec></Actions>
</Task>`
}

func taskOutput(raw []byte) string {
	if len(raw) >= 2 && (bytes.HasPrefix(raw, []byte{0xff, 0xfe}) || raw[1] == 0) {
		raw = bytes.TrimPrefix(raw, []byte{0xff, 0xfe})
		units := make([]uint16, 0, len(raw)/2)
		for len(raw) >= 2 {
			units = append(units, binary.LittleEndian.Uint16(raw))
			raw = raw[2:]
		}
		return strings.TrimSpace(strings.TrimRight(string(utf16.Decode(units)), "\x00"))
	}
	return strings.TrimSpace(string(bytes.TrimPrefix(raw, []byte{0xef, 0xbb, 0xbf})))
}

func matchesReporterTask(output, sid, program string) bool {
	if strings.HasPrefix(output, "<?xml ") {
		_, rest, ok := strings.Cut(output, "?>")
		if !ok {
			return false
		}
		// schtasks can label its output UTF-16; taskOutput already decoded it.
		output = rest
	}
	var task struct {
		XMLName    xml.Name `xml:"http://schemas.microsoft.com/windows/2004/02/mit/task Task"`
		Enabled    *bool    `xml:"Settings>Enabled"`
		Principals []struct {
			User     string `xml:"UserId"`
			Logon    string `xml:"LogonType"`
			RunLevel string `xml:"RunLevel"`
		} `xml:"Principals>Principal"`
		Triggers struct {
			Items []struct {
				XMLName  xml.Name
				Enabled  *bool  `xml:"Enabled"`
				Interval string `xml:"Repetition>Interval"`
				Duration string `xml:"Repetition>Duration"`
				End      string `xml:"EndBoundary"`
			} `xml:",any"`
		} `xml:"Triggers"`
		Actions struct {
			Items []struct {
				XMLName   xml.Name
				Command   string `xml:"Command"`
				Arguments string `xml:"Arguments"`
			} `xml:",any"`
		} `xml:"Actions"`
	}
	if xml.Unmarshal([]byte(output), &task) != nil || len(task.Principals) != 1 ||
		len(task.Triggers.Items) != 1 || len(task.Actions.Items) != 1 || (task.Enabled != nil && !*task.Enabled) {
		return false
	}
	user, trigger, action := task.Principals[0], task.Triggers.Items[0], task.Actions.Items[0]
	return strings.EqualFold(user.User, sid) && user.Logon == "InteractiveToken" &&
		(user.RunLevel == "" || user.RunLevel == "LeastPrivilege") &&
		trigger.XMLName.Local == "TimeTrigger" && (trigger.Enabled == nil || *trigger.Enabled) &&
		trigger.Interval == "PT6H" && trigger.Duration == "" && trigger.End == "" &&
		action.XMLName.Local == "Exec" && strings.EqualFold(action.Command, program) && action.Arguments == "report"
}
