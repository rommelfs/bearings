// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/xml"
	"strings"
	"testing"
	"time"
)

func TestTaskScheduleUsesCurrentInteractiveAccount(t *testing.T) {
	const sid = "S-1-5-21-100-200-300-400"
	const directory = `C:\Users\Example & User\Programs\Bearings`
	const program = directory + `\bearings-windows.exe`
	start := time.Date(2026, 11, 24, 9, 30, 0, 0, time.UTC)
	raw := taskXML(sid, program, directory, start)
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
