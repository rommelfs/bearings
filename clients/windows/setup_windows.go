// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"os"
	"runtime"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32 = windows.NewLazySystemDLL("user32.dll")
	gdi32  = windows.NewLazySystemDLL("gdi32.dll")
	kernel = windows.NewLazySystemDLL("kernel32.dll")

	registerClass = user32.NewProc("RegisterClassExW")
	createWindow  = user32.NewProc("CreateWindowExW")
	defaultWindow = user32.NewProc("DefWindowProcW")
	getMessage    = user32.NewProc("GetMessageW")
	dialogMessage = user32.NewProc("IsDialogMessageW")
	postMessage   = user32.NewProc("PostMessageW")
	sendMessage   = user32.NewProc("SendMessageW")
	setText       = user32.NewProc("SetWindowTextW")
	getText       = user32.NewProc("GetWindowTextW")
	enableWindow  = user32.NewProc("EnableWindow")
	showWindow    = user32.NewProc("ShowWindow")
	messageBox    = user32.NewProc("MessageBoxW")
)

const (
	wmCommand = 0x0111
	wmClose   = 0x0010
	wmDestroy = 0x0002
	wmResult  = 0x8001

	enrollKey = 101 + iota
	sendReport
	checkReport
	enableSchedule
)

type windowClass struct {
	size, style             uint32
	procedure               uintptr
	classExtra, windowExtra int32
	instance, icon, cursor  uintptr
	background              uintptr
	menu, class             *uint16
	smallIcon               uintptr
}

type windowMessage struct {
	window        uintptr
	message       uint32
	word, pointer uintptr
	stamp         uint32
	point         [2]int32
	private       uint32
}

var removalStarted = errors.New("local removal started")

type setupResult struct {
	text  string
	close bool
}

type setupWindow struct {
	window, code, note  uintptr
	buttons             []uintptr
	dir                 string
	font, instance, dpi uintptr
	busy                bool
	results             chan setupResult
}

func utf16Text(value string) *uint16 {
	return windows.StringToUTF16Ptr(strings.ReplaceAll(value, "\x00", ""))
}

func uiError(hwnd uintptr, text string) {
	messageBox.Call(hwnd, uintptr(unsafe.Pointer(utf16Text(text))), uintptr(unsafe.Pointer(utf16Text("Bearings Windows"))), 0x10)
}

func (w *setupWindow) scale(px int) uintptr { return uintptr(px) * w.dpi / 96 }

func (w *setupWindow) add(class, label string, style, id uintptr, left, top, width, height int) uintptr {
	control, _, _ := createWindow.Call(0, uintptr(unsafe.Pointer(utf16Text(class))), uintptr(unsafe.Pointer(utf16Text(label))),
		style|0x50000000, w.scale(left), w.scale(top), w.scale(width), w.scale(height), w.window, id, w.instance, 0)
	if control != 0 {
		sendMessage.Call(control, 0x0030, w.font, 1)
	}
	return control
}

func (w *setupWindow) controls(server, note string) error {
	const tabStop = 0x10000
	const edit = 0x800000 | tabStop | 0x0080
	parts := []uintptr{
		w.add("STATIC", "Bearings server: "+server, 0, 0, 20, 18, 586, 24),
		w.add("STATIC", "Paste the Bearings rollout key.", 0, 0, 20, 57, 586, 23),
	}
	w.code = w.add("EDIT", "", edit|0x0020, 0, 20, 85, 586, 26)
	w.note = w.add("STATIC", note, 0, 0, 20, 218, 586, 78)
	w.buttons = []uintptr{
		w.add("BUTTON", "Register and enable reports", tabStop, enrollKey, 20, 132, 190, 30),
		w.add("BUTTON", "Send report", tabStop, sendReport, 218, 132, 105, 30),
		w.add("BUTTON", "Check status", tabStop, checkReport, 331, 132, 106, 30),
		w.add("BUTTON", "Enable automatic reports", tabStop, enableSchedule, 20, 174, 190, 30),
	}
	for _, control := range append(parts, append(w.buttons, w.code, w.note)...) {
		if control == 0 {
			return errors.New("could not create the Windows setup controls")
		}
	}
	sendMessage.Call(w.code, 0x00C5, 16_000, 0)
	return nil
}

func field(hwnd uintptr, limit int) string {
	raw := make([]uint16, limit+1)
	getText.Call(hwnd, uintptr(unsafe.Pointer(&raw[0])), uintptr(len(raw)))
	return strings.TrimSpace(windows.UTF16ToString(raw))
}

func (w *setupWindow) response(value string) {
	setText.Call(w.note, uintptr(unsafe.Pointer(utf16Text(value))))
}

func (w *setupWindow) operation(action uintptr, code string) (string, error) {
	s, err := openStore(w.dir, false)
	if err != nil {
		return "", err
	}
	defer s.close()
	if action == sendReport || action == checkReport {
		started, err := remoteUninstall(s)
		if err != nil {
			return "", err
		}
		if started {
			return "", removalStarted
		}
	}
	switch action {
	case enrollKey:
		hostname, err := os.Hostname()
		if err != nil && rolloutInput(code) {
			return "", errors.New("cannot read the Windows computer name")
		}
		if _, err := enrollCode(&s.state, s.save, code, "", hostname); err != nil {
			return "", err
		}
		name, scheduleErr := scheduleReporter()
		report, reportErr := reportNow(s)
		if scheduleErr != nil {
			return "Registered. " + scheduleErr.Error() + ". Use Enable automatic reports to retry.", nil
		}
		if reportErr != nil || report == nil {
			return "Registered. Automatic reports enabled. The first report will retry.\r\nTask: " + name, nil
		}
		return "Registered. Automatic reports enabled every six hours while signed in.\r\nFirst report: " + report.Status + ".", nil
	case sendReport:
		r, err := reportNow(s)
		if err != nil {
			return "", err
		}
		if r == nil {
			return "No pending report. Use Send report to collect another observation.", nil
		}
		return "Report status: " + r.Status + ". If pending, use Check status.", nil
	case checkReport:
		updateStatus := "Client updates: enabled."
		if s.state.Update != nil {
			if s.state.Update.Status != "" {
				updateStatus = "Client updates: " + s.state.Update.Status + "."
			}
			if s.state.Update.Disabled {
				updateStatus = "Client updates: disabled."
			}
			if s.state.Update.Error != "" {
				updateStatus += " " + s.state.Update.Error
			}
		}
		if buildInfo().Key == "" {
			updateStatus = "Client updates: this build has no release trust anchor."
		}
		taskStatus := "Automatic reports: Windows task could not be verified."
		if task, err := currentReporterTask(); err == nil {
			taskStatus = task.status()
		}
		if err := s.state.ready(); err != nil {
			return updateStatus + "\r\n" + taskStatus + "\r\nReport status: " + err.Error(), nil
		}
		r, err := status(&s.state)
		if err != nil {
			return updateStatus + "\r\n" + taskStatus + "\r\nReport status: " + err.Error(), nil
		}
		return updateStatus + "\r\n" + taskStatus + "\r\nReport status: " + r.Status + ".", nil
	case enableSchedule:
		if err := s.state.ready(); err != nil {
			return "", err
		}
		name, err := scheduleReporter()
		if err != nil {
			return "", err
		}
		return "Automatic reports enabled every six hours while you are signed in.\r\nTask: " + name, nil
	}
	return "", nil
}

func (w *setupWindow) setBusy(busy bool) {
	w.busy = busy
	var enabled uintptr
	if !busy {
		enabled = 1
	}
	for _, button := range w.buttons {
		enableWindow.Call(button, enabled)
	}
}

func (w *setupWindow) event(hwnd uintptr, message uint32, word, param uintptr) uintptr {
	switch message {
	case wmCommand:
		action := word & 0xffff
		if action >= enrollKey && action <= enableSchedule && !w.busy {
			if action == enableSchedule {
				answer, _, _ := messageBox.Call(hwnd,
					uintptr(unsafe.Pointer(utf16Text("Install a copy in your Windows profile and create a task that sends inventory and checks signed Bearings client updates every six hours while you are signed in?"))),
					uintptr(unsafe.Pointer(utf16Text("Enable Bearings reports"))), 0x124) // Yes/No with No as default
				if answer != 6 {
					return 0
				}
			}
			var code string
			if action == enrollKey {
				code = field(w.code, 16_000)
				setText.Call(w.code, uintptr(unsafe.Pointer(utf16Text(""))))
			}
			w.setBusy(true)
			w.response("Working. Keep this window open.")
			go func() {
				result, err := w.operation(action, code)
				if err != nil {
					result = err.Error()
				}
				w.results <- setupResult{text: result, close: errors.Is(err, removalStarted)}
				postMessage.Call(hwnd, wmResult, 0, 0)
			}()
			return 0
		}
	case wmResult:
		select {
		case result := <-w.results:
			w.response(result.text)
			w.setBusy(false)
			if result.close {
				postMessage.Call(hwnd, wmClose, 0, 0)
			}
		default:
		}
		return 0
	case wmClose:
		if w.busy {
			return 0
		}
	case wmDestroy:
		user32.NewProc("PostQuitMessage").Call(0)
		return 0
	}
	result, _, _ := defaultWindow.Call(hwnd, uintptr(message), word, param)
	return result
}

func hidePrivateConsole() {
	var processes [2]uint32
	count, _, _ := kernel.NewProc("GetConsoleProcessList").Call(uintptr(unsafe.Pointer(&processes[0])), uintptr(len(processes)))
	if count == 1 && processes[0] == uint32(os.Getpid()) {
		console, _, _ := kernel.NewProc("GetConsoleWindow").Call()
		if console != 0 {
			showWindow.Call(console, 0)
		}
	}
}

func setupGUI() error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	dir, err := defaultStateDir()
	if err != nil {
		return err
	}
	s, err := openStore(dir, true)
	if err != nil {
		return err
	}
	enrolled := s.state.DeviceID != ""
	server := defaultServer
	if enrolled {
		server = s.state.URL
	}
	s.close()
	server, err = origin(server)
	if err != nil {
		return errors.New("download the Windows client built by your Bearings server")
	}
	if proc := user32.NewProc("SetProcessDPIAware"); proc.Find() == nil {
		proc.Call()
	}
	w := &setupWindow{dir: dir, dpi: 96, results: make(chan setupResult, 1)}
	if proc := user32.NewProc("GetDpiForSystem"); proc.Find() == nil {
		if dpi, _, _ := proc.Call(); dpi != 0 {
			w.dpi = dpi
		}
	}
	w.instance, _, _ = kernel.NewProc("GetModuleHandleW").Call(0)
	w.font, _, _ = gdi32.NewProc("GetStockObject").Call(17)
	cursor, _, _ := user32.NewProc("LoadCursorW").Call(0, 32512)
	className := utf16Text("BearingsWindowsSetup")
	class := windowClass{procedure: windows.NewCallback(w.event), instance: w.instance,
		cursor: cursor, background: 6, class: className}
	class.size = uint32(unsafe.Sizeof(class))
	if registered, _, _ := registerClass.Call(uintptr(unsafe.Pointer(&class))); registered == 0 {
		return errors.New("could not register the Windows setup window")
	}
	w.window, _, _ = createWindow.Call(0, uintptr(unsafe.Pointer(className)), uintptr(unsafe.Pointer(utf16Text("Bearings Windows "+version))),
		0x00CA0000, 0x80000000, 0x80000000, w.scale(650), w.scale(356), 0, 0, w.instance, 0)
	if w.window == 0 {
		return errors.New("could not open the Windows setup window")
	}
	note := "Waiting for your Bearings rollout key."
	if enrolled {
		note = "This Windows account is already enrolled. Send a report or check its status."
	}
	if err := w.controls(server, note); err != nil {
		user32.NewProc("DestroyWindow").Call(w.window)
		return err
	}
	hidePrivateConsole()
	showWindow.Call(w.window, 5)
	var message windowMessage
	for {
		result, _, _ := getMessage.Call(uintptr(unsafe.Pointer(&message)), 0, 0, 0)
		switch int32(result) {
		case -1:
			return errors.New("the Windows setup window could not process a message")
		case 0:
			return nil
		}
		if handled, _, _ := dialogMessage.Call(w.window, uintptr(unsafe.Pointer(&message))); handled == 0 {
			user32.NewProc("TranslateMessage").Call(uintptr(unsafe.Pointer(&message)))
			user32.NewProc("DispatchMessageW").Call(uintptr(unsafe.Pointer(&message)))
		}
	}
}
