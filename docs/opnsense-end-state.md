# OPNsense End-State Buildout

This is the implementation checklist for the current CEI-Labs edge box target:
OPNsense on a two-interface firewall, one managed switch, VLAN-separated server
and player networks, three bridge-only APs, and Headscale for staff remote
access.

Use this as the top-level build sheet. The deeper security controls remain in
[`network-topology.md`](network-topology.md),
[`security-qos-policy.md`](security-qos-policy.md), and
[`verification-checklist.md`](verification-checklist.md).

## Physical interface assignment

The OPNsense box has exactly two required physical interfaces:

| Interface | Role | Connects to | Configuration |
| :--- | :--- | :--- | :--- |
| WAN | Internet uplink | Venue ISP/modem/upstream router | DHCP or static from venue; no player/client devices |
| LAN trunk | 802.1Q trunk | Managed switch port 1 | Parent interface for VLANs 10, 20, 30, 40, 50 |

Do not use extra NICs for ad hoc management or AP links unless the topology is
rewritten. The LAN trunk is the mediator path: APs, server hosts, staff devices,
and players all reach OPNsense through VLAN interfaces on that trunk, and
OPNsense remains the only router, DHCP server, resolver, and policy boundary.

## VLAN interfaces on OPNsense

Create these VLANs on the LAN-trunk parent interface:

| VLAN | Interface name | IPv4 gateway | DHCP role |
| :--- | :--- | :--- | :--- |
| 10 | `vlan10_mgmt` | `10.10.10.1/24` | Static/reserved only |
| 20 | `vlan20_ctf_infra` | `10.10.20.1/24` | Static/reserved server leases |
| 30 | `vlan30_player_wifi` | `10.10.32.1/22` | Player Wi-Fi DHCP, 7200s lease |
| 40 | `vlan40_player_wired` | `10.10.40.1/24` | Wired-player DHCP, 7200s lease |
| 50 | `vlan50_staff` | `10.10.50.1/24` | Static/reserved or staff DHCP |

Disable IPv6 globally and set IPv6 configuration type to `None` on every VLAN
interface before opening player networks.

## Server network

VLAN 20 is the server network. The reference `cei-labs-engine` host lands on
switch port 10 as an untagged VLAN 20 access port.

Minimum static/reserved assignments:

| Device | Address | Notes |
| :--- | :--- | :--- |
| OPNsense VLAN 20 gateway | `10.10.20.1` | Default gateway for server network |
| Primary CEI-Labs engine host | `10.10.20.10` | Docker/Swarm host for CTFd, Traefik, orchestrator |
| Additional engine hosts | `10.10.20.11+` | Only if multi-node Swarm is intentionally used |

The only player-facing server access should be the published challenge and
scoreboard ports documented in `network-topology.md`. Management surfaces stay
reachable from VLAN 50 and, if explicitly allowed, Headscale staff nodes.

## Three AP layout

All APs run as bridge-only OpenWrt access points. They do not route, NAT,
forward DNS, run DHCP, or mediate policy. OPNsense mediates by being the VLAN
gateway and firewall for every SSID.

| AP | Switch port | Port mode | VLANs |
| :--- | :--- | :--- | :--- |
| AP-1 | 2 | Isolated 802.1Q trunk | 10, 30, 50 |
| AP-2 | 3 | Isolated 802.1Q trunk | 10, 30, 50 |
| AP-3 | 4 | Isolated 802.1Q trunk | 10, 30, 50 |
| Spare AP | 5 | Disabled until needed | 10, 30, 50 when assigned |

Required SSID mapping:

| SSID class | VLAN | Required AP behavior |
| :--- | :--- | :--- |
| Player Wi-Fi | 30 | WPA2/WPA3-Personal, client isolation enabled, event passphrase |
| Staff Wi-Fi | 50 | WPA2/WPA3-Personal, separate staff passphrase, client isolation enabled |
| AP management | 10 | No public SSID unless explicitly needed; management reachable only from approved staff/management sources |

The switch must isolate AP trunk ports 2-5 from one another for tagged player
traffic while still allowing each AP to reach port 1. If the switch cannot
isolate tagged AP trunks, use one player VLAN per AP and route/firewall between
them on OPNsense instead of putting all APs on one Layer-2 player segment.

## Headscale

Headscale is the staff remote-access control plane. It does not replace VLAN
firewalling and must not expose player networks by default.

Required end state:

- Headscale reachable at a real public HTTPS FQDN, not a raw IP.
- A staff tailnet/user namespace exists.
- A subnet router advertises VLAN 20 only by default: `10.10.20.0/24`.
- Player subnets are not advertised: `10.10.30.0/22`, `10.10.40.0/24`.
- ACLs are default-deny and explicitly allow staff nodes to VLAN 20 server
  destinations only unless the operator approves additional ranges.

## Live discovery gate

The following cannot be truthfully completed from this repo alone. Run them
from an authenticated shell or console on the OPNsense box and paste results
back into the deployment log:

```sh
ifconfig -a
netstat -rn
arp -an
sockstat -4 -l
```

From OPNsense UI or shell, also capture:

- assigned WAN/LAN parent interface names;
- VLAN interface names and gateway addresses;
- DHCP lease tables for VLANs 10, 20, 30, 40, 50;
- ARP table showing visible APs, switch management IP, and VLAN 20 server host;
- HAProxy/ACME status for Headscale;
- Headscale node list and approved routes.

Do not mark the box fully deployed until these observations match the tables
above and the relevant checks in `verification-checklist.md` pass from client
devices on the actual VLANs.
