// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"errors"
	"io"
	"runtime"
	"sort"
	"strconv"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
	"golang.org/x/text/cases"
)

var architectureProc = windows.NewLazySystemDLL("kernel32.dll").NewProc("IsWow64Process2")

func nativeArchitecture() (string, error) {
	if architectureProc.Find() != nil {
		return "", errors.New("Windows 10 version 1709 or later is required")
	}
	var process, native uint16
	ok, _, _ := architectureProc.Call(uintptr(windows.CurrentProcess()), uintptr(unsafe.Pointer(&process)), uintptr(unsafe.Pointer(&native)))
	if ok == 0 {
		return "", errors.New("Windows native architecture could not be read")
	}
	switch native {
	case 0x014c:
		return "x86", nil
	case 0x8664:
		return "x86_64", nil
	case 0xaa64:
		if process == 0 && runtime.GOARCH == "arm64" {
			return "arm64", nil
		}
	}
	return "", errors.New("run the Bearings executable for the native Windows architecture")
}

func stringValue(key registry.Key, field string, optional bool) (string, error) {
	value, kind, err := key.GetStringValue(field)
	if optional && errors.Is(err, registry.ErrNotExist) {
		return "", nil
	}
	if err != nil || kind != registry.SZ && kind != registry.EXPAND_SZ {
		return "", errors.New("required registry data is unreadable or malformed")
	}
	return value, nil
}

func unchanged(key registry.Key, before *registry.KeyInfo) bool {
	after, err := key.Stat()
	return err == nil && before.SubKeyCount == after.SubKeyCount &&
		before.ValueCount == after.ValueCount && before.ModTime() == after.ModTime()
}

func collectOS(access uint32) (component, error) {
	key, err := registry.OpenKey(registry.LOCAL_MACHINE, osKey, registry.READ|access)
	if err != nil {
		return component{}, errors.New("cannot read the Windows OS registry entry")
	}
	defer key.Close()
	before, err := key.Stat()
	if err != nil {
		return component{}, errors.New("cannot inspect the Windows OS registry entry")
	}
	name, nameErr := stringValue(key, "ProductName", false)
	edition, editionErr := stringValue(key, "EditionID", true)
	installationType, installationErr := stringValue(key, "InstallationType", true)
	release, releaseErr := stringValue(key, "DisplayVersion", true)
	build, buildErr := stringValue(key, "CurrentBuildNumber", false)
	revision, revisionType, revisionErr := key.GetIntegerValue("UBR")
	if nameErr != nil || editionErr != nil || installationErr != nil || releaseErr != nil || buildErr != nil ||
		!digits.MatchString(build) || revisionErr != nil || revisionType != registry.DWORD {
		return component{}, errors.New("Windows product name, edition, release or build metadata is invalid")
	}
	if !unchanged(key, before) {
		return component{}, errors.New("Windows OS registry changed during collection; retry the report")
	}
	return newComponent("win-reg:os:all", name, build+"."+strconv.FormatUint(revision, 10),
		evidence{InstallationType: installationType, Kind: "os", Key: osKey, View: "native", Publisher: "Microsoft", Edition: edition, Release: release})
}

func collectProgram(path, view string, access uint32) (component, error) {
	key, err := registry.OpenKey(registry.LOCAL_MACHINE, path, registry.READ|access)
	if err != nil {
		return component{}, errors.New("uninstall registry entry disappeared or is unreadable")
	}
	defer key.Close()
	before, err := key.Stat()
	if err != nil {
		return component{}, errors.New("cannot inspect an uninstall registry entry")
	}
	name, err := stringValue(key, "DisplayName", true)
	if err != nil {
		return component{}, err
	}
	var version, publisher string
	if name != "" {
		version, err = stringValue(key, "DisplayVersion", true)
		if err != nil {
			return component{}, err
		}
		publisher, err = stringValue(key, "Publisher", true)
		if err != nil {
			return component{}, err
		}
	}
	if !unchanged(key, before) {
		return component{}, errors.New("uninstall registry changed during collection; retry the report")
	}
	if name == "" {
		return component{}, nil
	}
	id := "win-reg:" + digest([]byte(view+":"+cases.Fold().String(path))) + ":all"
	return newComponent(id, name, version, evidence{Kind: "program", Key: path, View: view, Publisher: publisher})
}

func collectView(components []component, view string, access uint32) ([]component, error) {
	root, err := registry.OpenKey(registry.LOCAL_MACHINE, uninstallKey, registry.READ|access)
	if errors.Is(err, registry.ErrNotExist) {
		return components, nil
	}
	if err != nil {
		return nil, errors.New("cannot read the Windows uninstall registry view")
	}
	defer root.Close()
	before, err := root.Stat()
	if err != nil || before.SubKeyCount > maxComponents {
		return nil, errors.New("uninstall registry is unreadable or exceeds the inventory limit")
	}
	names, err := root.ReadSubKeyNames(int(before.SubKeyCount) + 1)
	// ReadSubKeyNames(n) returns EOF when fewer than n entries were found.
	if (err != nil && !errors.Is(err, io.EOF)) || len(names) != int(before.SubKeyCount) {
		return nil, errors.New("uninstall registry changed during enumeration; retry the report")
	}
	for _, name := range names {
		value, err := collectProgram(uninstallKey+`\`+name, view, access)
		if err != nil {
			return nil, err
		}
		if value.Key == "" {
			continue
		}
		if len(components) >= maxComponents {
			return nil, errors.New("inventory exceeds 5000 components")
		}
		components = append(components, value)
	}
	if !unchanged(root, before) {
		return nil, errors.New("uninstall registry changed during collection; retry the report")
	}
	return components, nil
}

func collect() (*report, error) {
	arch, err := nativeArchitecture()
	if err != nil {
		return nil, err
	}
	var access uint32
	if arch != "x86" {
		access = registry.WOW64_64KEY
	}
	os, err := collectOS(access)
	if err != nil {
		return nil, err
	}
	components := []component{os}
	if arch != "x86" {
		components, err = collectView(components, "64", registry.WOW64_64KEY)
		if err != nil {
			return nil, err
		}
	}
	components, err = collectView(components, "32", registry.WOW64_32KEY)
	if err != nil {
		return nil, err
	}
	sort.Slice(components, func(i, j int) bool { return components[i].Key < components[j].Key })
	for i := 1; i < len(components); i++ {
		if components[i-1].Key == components[i].Key {
			return nil, errors.New("duplicate Windows registry identity; no partial report sent")
		}
	}
	value := &report{
		Schema: tag, ID: identifier(), Sequence: 1, ObservedAt: time.Now().UTC(),
		Scope: "windows-machine", Complete: true,
		OS:         operatingSystem{ID: "windows", Version: os.Version, Architecture: arch, Kernel: os.Version, KernelScope: "host", RebootHint: "unknown"},
		Components: components, Services: []struct{}{},
	}
	value.OS.WindowsUpdate = collectUpdates()
	value.OS.RebootHint = value.OS.WindowsUpdate.Reboot
	err = fitWindowsUpdates(value)
	return value, err
}
