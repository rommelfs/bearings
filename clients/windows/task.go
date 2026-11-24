// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"encoding/xml"
	"strings"
	"time"
)

func taskXML(sid, program, directory string, start time.Time) string {
	escape := func(value string) string {
		var out strings.Builder
		xml.EscapeText(&out, []byte(value))
		return out.String()
	}
	return `<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Send Windows machine inventory to Bearings every six hours.</Description></RegistrationInfo>
<Triggers><TimeTrigger><Repetition><Interval>PT6H</Interval></Repetition><StartBoundary>` +
		start.Format("2006-01-02T15:04:05") + `</StartBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>
<Principals><Principal id="Reporter"><UserId>` + escape(sid) + `</UserId>
<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable>
<ExecutionTimeLimit>PT30M</ExecutionTimeLimit></Settings>
<Actions Context="Reporter"><Exec><Command>` + escape(program) + `</Command><Arguments>report</Arguments>
<WorkingDirectory>` + escape(directory) + `</WorkingDirectory></Exec></Actions>
</Task>`
}
