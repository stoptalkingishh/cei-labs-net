# OPNsense End-State Buildout

This is the implementation checklist for the current live CEI-Labs OPNsense
box. It supersedes the earlier five-VLAN router-on-a-stick plan for this
deployment.

Source of truth for this page is live router discovery from
`cei-router.ctf.internal` at `https://192.168.10.1`, plus the prior Claude
hardware notes for the same box.

## Current live hardware state

Verified from the OPNsense box with `hostname`, `uname -a`, `ifconfig -a`,
`netstat -rn`, `arp -an`, `sockstat -4 -l`, `pciconf -lv`, `usbconfig`, and
`configctl interface list arp`.

| Device | OPNsense role | Live interface | Addressing | Link state |
| :--- | :--- | :--- | :--- | :--- |
| Onboard Intel I219-V | LAN / management + CTF infra | `em0` | `192.168.10.1/24` | active, 1000baseT full-duplex |
| Lenovo USB-C Ethernet | WAN | `ue0` | DHCP/DHCP6, currently `192.168.1.111/24` when link is up | reported no carrier during the latest SSH check |
| Realtek RTL8153 USB Ethernet | Player Wi-Fi | `ue1` / `opt3` | `10.10.32.1/22` | active, 1000baseT full-duplex |
| Intel Wireless-AC 8265 | unused legacy wireless WAN | `iwm0_wlan0` | no carrier | not part of target state |

The practical deployment is now two internal networks plus WAN:

| Network | Interface | Subnet | DHCP |
| :--- | :--- | :--- | :--- |
| LAN / management / CTF infra | `em0` | `192.168.10.0/24` | dnsmasq range `192.168.10.41`-`192.168.10.245`, 86400s |
| Player Wi-Fi | `ue1` / `opt3` | `10.10.32.0/22` | dnsmasq range `10.10.32.10`-`10.10.35.250`, 7200s |
| WAN | `ue0` | DHCP from upstream `192.168.1.0/24` network | upstream-provided |

This means the old `10.10.10.0/24`, `10.10.20.0/24`, `10.10.40.0/24`, and
`10.10.50.0/24` segmented design is not the current live deployment.

## Leftover VLAN state to clean up

The router still has leftover VLAN interfaces from the earlier design:

| Interface | VLAN tag | Parent | Description |
| :--- | :---: | :--- | :--- |
| `vlan01` | 10 | `em0` | `VLAN10_Management` |
| `vlan02` | 20 | `em0` | `VLAN20_CTF_Infra` |
| `vlan03` | 30 | `em0` | stale `VLAN30_Player_WiFi` tag |
| `vlan04` | 40 | `em0` | `VLAN40_Player_Wired` |
| `vlan05` | 50 | `em0` | `VLAN50_Staff` |

These VLANs are active at the OS level but are unused leftovers now that
Player Wi-Fi is on the dedicated `ue1` interface. Before declaring the box
clean, remove or disable these stale VLAN assignments through the OPNsense
configuration workflow and re-run interface discovery.

## Devices visible from OPNsense

Latest ARP/device view from the router:

| IP | MAC | Interface | Manufacturer / likely role |
| :--- | :--- | :--- | :--- |
| `192.168.10.1` | `e8:6a:64:41:68:54` | `em0` | OPNsense LAN |
| `192.168.10.120` | `b4:a9:fc:62:11:c1` | `em0` | `DESKTOP-Q8892V6`, operator laptop |
| `192.168.10.192` | `d4:ae:52:cc:7a:f1` | `em0` | Dell device |
| `192.168.1.111` | `60:7d:09:3a:f0:21` | `ue0` | OPNsense WAN adapter |
| `192.168.1.254` | `68:ab:a9:49:fc:e1` | `ue0` | upstream gateway |
| `10.10.32.1` | `9c:eb:e8:c3:70:92` | `ue1` | OPNsense Player-WiFi gateway |
| `10.10.32.2` | `2c:30:33:41:8b:7a` | `ue1` | NETGEAR AP/client bridge |
| `10.10.32.3` | `34:98:b5:64:16:9a` | `ue1` | NETGEAR AP/client bridge |

dnsmasq lease data additionally showed:

| IP | MAC | Hostname |
| :--- | :--- | :--- |
| `192.168.10.120` | `b4:a9:fc:62:11:c1` | `DESKTOP-Q8892V6` |
| `192.168.10.235` | `00:d8:61:e5:4e:0f` | `host` |

The AP lane should treat the two visible NETGEAR devices as real hardware to
verify first. If the final requirement remains three APs, add and verify a
third AP on `ue1`/Player-WiFi and capture its ARP/DHCP entry before marking
wireless complete.

## Listening services on the router

Latest IPv4 listeners:

| Service | Listener | Notes |
| :--- | :--- | :--- |
| OPNsense web UI | `*:80`, `*:443` | lighttpd |
| SSH | `*:22` | enabled for root/admin workflow |
| dnsmasq DHCP | `*:67` | DHCP on LAN and Player-WiFi ranges |
| Unbound DNS | `*:53` | DNS listener |
| NTP | `*:123`, `192.168.10.1:123`, `10.10.32.1:123` | local time service |

## Immediate end-state tasks

1. Remove or disable stale VLAN interfaces `vlan01`-`vlan05` if the two-network
   topology is final.
2. Keep `em0` as the combined management/CTF-infra LAN unless the operator
   explicitly reintroduces a dedicated server VLAN.
3. Keep `ue1` as the dedicated Player-WiFi interface with gateway
   `10.10.32.1/22` and DHCP `10.10.32.10`-`10.10.35.250`.
4. Validate both visible NETGEAR APs are pure bridge/AP devices:
   no DHCP server, no NAT, no routing, and player clients receive OPNsense
   leases from `10.10.32.0/22`.
5. Add and validate the third AP only if three-AP coverage remains required.
6. Re-check WAN link state on `ue0`; latest SSH discovery reported `no carrier`
   even though configctl still showed the prior DHCP lease.
7. Decide whether Headscale should run on the OPNsense jail or the LAN host;
   if Headscale advertises subnets, the current default route to expose is
   `192.168.10.0/24`, not the stale `10.10.20.0/24`.

## Verification commands

Run these from an authenticated OPNsense shell after each hardware or config
change:

```sh
hostname
ifconfig -a
netstat -rn
arp -an
sockstat -4 -l
configctl interface list ifconfig
configctl interface list arp
```

For DHCP state, inspect:

```sh
cat /var/db/dnsmasq.leases
cat /usr/local/etc/dnsmasq.conf
```

Do not mark the box fully deployed until the live outputs match the intended
two-network topology and the AP checks pass from real client devices.
