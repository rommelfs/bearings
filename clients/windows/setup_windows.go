// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"os"
	"path/filepath"
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

	copyKey = 101 + iota
	enrollKey
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

type setupWindow struct {
	window, publicKey, code, ca, note uintptr
	buttons                           []uintptr
	dir                               string
	font, instance, dpi               uintptr
	busy                              bool
	results                           chan string
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

func (w *setupWindow) controls(key, note string) error {
	const (
		tabStop = 0x10000
		border  = 0x800000
		edit    = border | tabStop | 0x0080 // ES_AUTOHSCROLL
	)
	parts := []uintptr{
		w.add("STATIC", "1. Give this public key to your Bearings administrator for the existing asset.", 0, 0, 20, 18, 590, 23),
		w.add("STATIC", "2. Paste the one-time registration code.", 0, 0, 20, 97, 590, 23),
		w.add("STATIC", "Approved CA file (optional, paste a PEM file path)", 0, 0, 20, 157, 586, 20),
		w.add("STATIC", "3. Confirm a report is applied before enabling automatic reports.", 0, 0, 20, 217, 586, 23),
	}
	w.publicKey = w.add("EDIT", key, edit|0x0800, 0, 20, 45, 460, 26)
	w.code = w.add("EDIT", "", edit|0x0020, 0, 20, 124, 586, 26) // ES_PASSWORD
	w.ca = w.add("EDIT", "", edit, 0, 20, 182, 586, 26)
	w.note = w.add("STATIC", note, 0, 0, 20, 321, 586, 78)
	copy := w.add("BUTTON", "Copy public key", tabStop, copyKey, 493, 44, 113, 29)
	w.buttons = []uintptr{
		w.add("BUTTON", "Enroll and send first report", tabStop, enrollKey, 20, 247, 190, 30),
		w.add("BUTTON", "Send report", tabStop, sendReport, 218, 247, 105, 30),
		w.add("BUTTON", "Check status", tabStop, checkReport, 331, 247, 106, 30),
		w.add("BUTTON", "Enable automatic reports", tabStop, enableSchedule, 20, 284, 190, 30),
	}
	for _, control := range append(parts, append(w.buttons, w.publicKey, w.code, w.ca, w.note, copy)...) {
		if control == 0 {
			return errors.New("could not create the Windows setup controls")
		}
	}
	sendMessage.Call(w.code, 0x00C5, 16_000, 0) // EM_SETLIMITTEXT
	sendMessage.Call(w.ca, 0x00C5, 4096, 0)
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

func (w *setupWindow) operation(action uintptr, code, ca string) (string, error) {
	s, err := openStore(w.dir, false)
	if err != nil {
		return "", err
	}
	defer s.close()
	switch action {
	case enrollKey:
		g, err := readGrant(code)
		if err != nil {
			return "", err
		}
		if ca != "" {
			ca, err = filepath.Abs(ca)
			if err != nil {
				return "", errors.New("invalid approved CA path")
			}
		}
		if _, err := enroll(&s.state, s.save, g, ca); err != nil {
			return "", err
		}
		fallthrough
	case sendReport:
		r, err := reportNow(s)
		if err != nil {
			return "", err
		}
		if r == nil {
			return "No pending report. Use Send report to collect another observation.", nil
		}
		return "Report status: " + r.Status + ". If pending, use Check status.", nil
	case checkReport, enableSchedule:
		r, err := status(&s.state)
		if err != nil {
			return "", err
		}
		if action == checkReport || r.Status != "applied" {
			return "Report status: " + r.Status + ". Automatic reports require an applied report.", nil
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
		if action == copyKey {
			sendMessage.Call(w.publicKey, 0x00B1, 0, ^uintptr(0)) // EM_SETSEL
			sendMessage.Call(w.publicKey, 0x0301, 0, 0)           // WM_COPY
			w.response("Public key copied. Give it to your Bearings administrator.")
			return 0
		}
		if action >= enrollKey && action <= enableSchedule && !w.busy {
			if action == enableSchedule {
				answer, _, _ := messageBox.Call(hwnd,
					uintptr(unsafe.Pointer(utf16Text("Install a copy in your Windows profile and create a task that sends inventory every six hours while you are signed in?"))),
					uintptr(unsafe.Pointer(utf16Text("Enable Bearings reports"))), 0x124) // Yes/No with No as default
				if answer != 6 {
					return 0
				}
			}
			var code, ca string
			if action == enrollKey {
				code, ca = field(w.code, 16_000), field(w.ca, 4096)
				setText.Call(w.code, uintptr(unsafe.Pointer(utf16Text(""))))
			}
			w.setBusy(true)
			w.response("Working. Keep this window open.")
			go func() {
				result, err := w.operation(action, code, ca)
				if err != nil {
					result = err.Error()
				}
				w.results <- result
				postMessage.Call(hwnd, wmResult, 0, 0)
			}()
			return 0
		}
	case wmResult:
		select {
		case result := <-w.results:
			w.response(result)
			w.setBusy(false)
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
	key, enrolled := s.state.publicKey(), s.state.DeviceID != ""
	s.close()
	if proc := user32.NewProc("SetProcessDPIAware"); proc.Find() == nil {
		proc.Call()
	}
	w := &setupWindow{dir: dir, dpi: 96, results: make(chan string, 1)}
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
		0x00CA0000, 0x80000000, 0x80000000, w.scale(650), w.scale(459), 0, 0, w.instance, 0)
	if w.window == 0 {
		return errors.New("could not open the Windows setup window")
	}
	note := "Waiting for your Bearings registration code."
	if enrolled {
		note = "This Windows account is already enrolled. Send a report or check its status."
	}
	if err := w.controls(key, note); err != nil {
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
