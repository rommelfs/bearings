// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/binary"
	"encoding/xml"
	"strings"
	"testing"
	"time"
	"unicode/utf16"
)

func TestTaskScheduleUsesCurrentInteractiveAccount(t *testing.T) {
	const sid = "S-1-5-21-100-200-300-400"
	const directory = `C:\Users\Example & User\Programs\Bearings`
	const program = directory + `\bearings-windows.exe`
	start := time.Date(2026, 11, 24, 9, 30, 0, 0, time.UTC)
	raw := taskXML(sid, program, directory, start)
	// Trigger children follow the order required by the published Task Scheduler schema.
	const trigger = "<TimeTrigger><Enabled>true</Enabled><StartBoundary>2026-11-24T09:30:00</StartBoundary><Repetition><Interval>PT6H</Interval></Repetition></TimeTrigger>"
	if !strings.Contains(raw, trigger) || !strings.Contains(raw, `<Task version="1.3"`) {
		t.Fatal("task XML no longer matches the scheduler schema version or trigger order")
	}
	var task struct {
		XMLName   xml.Name
		Interval  string `xml:"Triggers>TimeTrigger>Repetition>Interval"`
		Start     string `xml:"Triggers>TimeTrigger>StartBoundary"`
		User      string `xml:"Principals>Principal>UserId"`
		Logon     string `xml:"Principals>Principal>LogonType"`
		RunLevel  string `xml:"Principals>Principal>RunLevel"`
		Command   string `xml:"Actions>Exec>Command"`
		Arguments string `xml:"Actions>Exec>Arguments"`
		Directory string `xml:"Actions>Exec>WorkingDirectory"`
		Overlap   string `xml:"Settings>MultipleInstancesPolicy"`
		CatchUp   bool   `xml:"Settings>StartWhenAvailable"`
	}
	if err := xml.Unmarshal([]byte(strings.Replace(raw, "UTF-16", "UTF-8", 1)), &task); err != nil {
		t.Fatal(err)
	}
	if task.XMLName.Local != "Task" || task.User != sid || task.Logon != "InteractiveToken" ||
		task.RunLevel != "LeastPrivilege" || task.Interval != "PT6H" || task.Start != "2026-11-24T09:30:00" ||
		task.Command != program || task.Arguments != "report" || task.Directory != directory ||
		task.Overlap != "IgnoreNew" || !task.CatchUp {
		t.Fatal("task contract did not preserve the schedule, interactive identity and executable path")
	}
}

func TestVerifyWindowsScheduledTask(t *testing.T) {
	const sid = "S-1-5-21-100-200-300-400"
	const directory = `C:\Users\Jörg & User\Programs\Bearings`
	const program = directory + `\bearings-windows.exe`
	raw := taskXML(sid, program, directory, time.Now())
	encoded := []byte{0xff, 0xfe}
	for _, unit := range utf16.Encode([]rune(raw)) {
		encoded = binary.LittleEndian.AppendUint16(encoded, unit)
	}
	if !matchesReporterTask(taskOutput(encoded), sid, program) {
		t.Fatal("did not accept the registered task's UTF-16 XML")
	}
	for _, alteration := range [][2]string{
		{sid, "S-1-5-18"},
		{"<Settings>", "<Settings><Enabled>false</Enabled>"},
		{"<Enabled>true</Enabled>", "<Enabled>false</Enabled>"},
		{"<Interval>PT6H</Interval>", "<Interval>PT1H</Interval>"},
		{"</Interval>", "</Interval><Duration>P1D</Duration>"},
		{"<Arguments>report</Arguments>", "<Arguments>status</Arguments>"},
		{"</Exec>", "</Exec><Exec><Command>another.exe</Command></Exec>"},
	} {
		if matchesReporterTask(strings.Replace(raw, alteration[0], alteration[1], 1), sid, program) {
			t.Errorf("accepted task with changed %s", alteration[0])
		}
	}
}
