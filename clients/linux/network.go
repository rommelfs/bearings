// SPDX-License-Identifier: AGPL-3.0-or-later
//go:build linux

package main

import (
	"errors"
	"net"
	"net/netip"
	"os"
	"sort"
)

type declaredAddress struct {
	Interface string `json:"interface"`
	Address   string `json:"address"`
}
type declaredHost struct {
	Hostname  string            `json:"hostname"`
	Addresses []declaredAddress `json:"addresses"`
}

// No DNS lookup, external IP service, MAC address or traffic discovery is used.
func networkClaim() (declaredHost, error) {
	hostname, err := os.Hostname()
	if err != nil || len(hostname) == 0 || len(hostname) > 180 {
		return declaredHost{}, errors.New("local hostname unavailable or too long")
	}
	host := declaredHost{Hostname: hostname, Addresses: []declaredAddress{}}
	interfaces, err := net.Interfaces()
	if err != nil {
		return host, errors.New("local interface enumeration failed")
	}
	for _, iface := range interfaces {
		if iface.Flags&net.FlagLoopback != 0 || iface.Flags&net.FlagUp == 0 {
			continue
		}
		addresses, err := iface.Addrs()
		if err != nil {
			return host, errors.New("local interface addresses could not be read completely")
		}
		for _, address := range addresses {
			prefix, err := netip.ParsePrefix(address.String())
			if err != nil {
				return host, errors.New("unsupported interface address shape")
			}
			if !prefix.Addr().IsGlobalUnicast() {
				continue
			}
			host.Addresses = append(host.Addresses, declaredAddress{Interface: iface.Name, Address: prefix.String()})
			if len(host.Addresses) > 64 {
				return host, errors.New("more than 64 configured addresses; narrow enrollment through explicit existing-asset binding")
			}
		}
	}
	sort.Slice(host.Addresses, func(i, j int) bool {
		a, b := host.Addresses[i], host.Addresses[j]
		if a.Interface == b.Interface {
			return a.Address < b.Address
		}
		return a.Interface < b.Interface
	})
	return host, nil
}
