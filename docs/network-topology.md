# Network Topology & VLAN Architecture

This is a **router-on-a-stick** design: a single pfSense/OPNsense box with
one LAN interface, trunked into a managed switch that fans out five VLANs to
access points and wired stations. All inter-VLAN routing and firewalling
happens on the pfSense/OPNsense box itself.

```
                 ┌─────────────────────┐
   WAN ─────────▶│  pfSense/OPNsense   │
                 │   (Core Router/FW)  │
                 └──────────┬──────────┘
                             │ LAN (802.1Q trunk: VLANs 10/20/30/40/50)
                 ┌──────────┴──────────┐
                 │   24-Port Managed    │
                 │   L2 Core Switch     │
                 └──┬───┬────┬────┬────┘
        Port 1(trunk)│   │Ports 2-5│    │Port 10  │Ports 11-24
        (uplink)     │   │(AP trunks)   │(access) │(access)
                      ▼   ▼              ▼          ▼
                  Mgmt/Wi-Fi APs     Docker Host   Wired Stations
                  (VLAN 10/30/50)    (VLAN 20)      (VLAN 40)
```

## 1. Physical Wiring Configuration

| Link | Switch Port(s) | Mode | Carries |
| :--- | :--- | :--- | :--- |
| **WAN** | — (router WAN NIC) | N/A | Venue internet feed |
| **LAN (uplink)** | Port 1 | 802.1Q Trunk | All VLANs (10, 20, 30, 40, 50) |
| **AP Links** | Ports 2–5 | 802.1Q Trunk | Management (10), Player Wi-Fi (30), Staff Wi-Fi (50) |
| **Docker Infrastructure Host** | Port 10 | Access (untagged) | VLAN 20 |
| **Wired Hardline Stations** | Ports 11–24 | Access (untagged) | VLAN 40 |

Notes:

- AP trunk ports carry only the VLANs each AP actually broadcasts SSIDs
  for — typically Player Wi-Fi (30) and Staff Wi-Fi (50), plus Management
  (10) for the AP's own control-plane IP. Do **not** trunk VLAN 20 or 40 to
  APs.
- Every AP SSID-to-VLAN mapping must have **Client Isolation** (a.k.a. AP
  isolation / peer-to-peer blocking) enabled at the radio level. This stops
  same-SSID players from reaching each other directly over the air, which
  the switch/firewall ACLs cannot see or stop.
- **Ports 11–24 must have switch-level Port Isolation (a.k.a. Protected
  Ports / Private VLAN Edge) enabled — this is not optional, see the
  callout below.**
- **Enable RA-Guard (Router Advertisement Guard) on every player-facing
  port** (11–24, and the AP trunk ports 2–5) if the switch supports it.
  This network runs IPv6 disabled end-to-end (see
  [`security-qos-policy.md`](security-qos-policy.md) §0) — RA-Guard stops
  a rogue or misconfigured device plugged into a player port from handing
  out its own IPv6 router advertisements and auto-configuring peers onto
  a network segment this repo's firewall policy was never written to
  cover, before that traffic ever reaches pfSense/OPNsense at all.
- **Every SSID must use WPA2-Personal or WPA3-Personal — no open/
  unauthenticated SSID on any VLAN, including staff/management.** This
  was previously unstated anywhere in this repo. WPA3-Personal is
  preferred where every expected client device supports it (WPA3 closes
  several passive-capture weaknesses WPA2-Personal has); fall back to
  WPA2-Personal/AES(CCMP) — never WEP or WPA/TKIP — if broad device
  compatibility is a concern for a public player-facing SSID.
  Player-facing SSIDs (VLAN 30) should use a passphrase distributed at
  check-in, rotated per event; Staff (VLAN 50) and any AP management
  SSID (VLAN 10) should use a separate, non-public passphrase not
  shared with players.
- Ports 6–9 are unassigned by this layout (Ports 1–5 are the uplink/AP
  trunks, 10 is the Docker host, 11–24 are wired stations). Leave them
  disabled/spare rather than defaulting them into an access VLAN, so an
  unauthorized device plugged into an open port doesn't land on a live
  network.

> **Why wired stations need switch-level isolation, not just a firewall
> rule:** two hosts on the same VLAN, on the same switch, talking to each
> other is *ordinary local Layer-2 switching* — that traffic never reaches
> pfSense/OPNsense, so a firewall rule alone cannot see or block it. (This
> is exactly why Wi-Fi needs AP-side Client Isolation instead of relying on
> the firewall — the wired side has the identical problem and needs the
> wired equivalent.) **Port Isolation** on the switch (sometimes called
> Protected Ports or Private VLAN Edge/PVE) restricts each isolated port
> (11–24) to only forward traffic to designated "uplink" port(s) — Port 1
> here — never to another isolated port directly. That forces
> station-to-station traffic up to pfSense/OPNsense as an actual routed
> hairpin (same subnet, in and back out the same interface), which is what
> finally gives the firewall's `block VLAN40net → VLAN40net` rule (§3
> below, [`security-qos-policy.md`](security-qos-policy.md) §5) something
> real to act on. Enable this on whichever switch you use — for the
> TP-Link JetStream reference hardware in the main README, this is
> **Switching → Port Isolation**, with the "Uplink Port" set to Port 1 for
> every port in 11–24.

## 2. VLAN & DHCP Subnet Map

| VLAN | Name | Subnet | Gateway | DHCP Lease | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **10** | Management | `10.10.10.0/24` | `10.10.10.1` | Static/reserved | pfSense/OPNsense mgmt, switch mgmt, AP control plane |
| **20** | CTF Infrastructure | `10.10.20.0/24` | `10.10.20.1` | Static/reserved | Docker host, scoreboard engine, challenge containers |
| **30** | Player Wi-Fi | `10.10.32.0/22` | `10.10.32.1` | 7200s (2h) | ~1000 usable IPs — absorbs multi-device players (phone + laptop + VM) and MAC-randomization churn without exhausting the pool |
| **40** | Player Wired Hardlines | `10.10.40.0/24` | `10.10.40.1` | 7200s (2h) | Wired player stations |
| **50** | Staff / Operations | `10.10.50.0/24` | `10.10.50.1` | Static/reserved | Organizers, judges, red-team/support staff |

### Why VLAN 30 is a `/22`

A single `/24` (254 usable hosts) is not enough headroom for 80 participants
once you account for: each player bringing a phone *and* a laptop, VMs/NAT
adapters that present additional MAC addresses, and Wi-Fi client MAC
randomization causing devices to re-lease under a "new" address across the
event. `10.10.32.0/22` spans `10.10.32.1`–`10.10.35.254` (~1022 usable
hosts), giving comfortable headroom without redesigning the addressing
scheme mid-event.

## 3. Inter-VLAN Firewall Policy (summary)

Configure these as explicit-allow / default-deny rule sets per VLAN
interface (details and NAT/limiter specifics in
[`security-qos-policy.md`](security-qos-policy.md)):

| Source VLAN | Allowed Destinations | Denied |
| :--- | :--- | :--- |
| 30 (Player Wi-Fi) | VLAN 20 (challenge ports only), WAN (post-shaper/QoS) | VLAN 10, 40, 50, and **VLAN 30 → VLAN 30** (peer players) |
| 40 (Player Wired) | VLAN 20 (challenge ports only), WAN (post-shaper/QoS) | VLAN 10, 30, 50, and **VLAN 40 → VLAN 40** (peer players) |
| 20 (CTF Infra) | WAN (updates only, staff-approved), all VLANs inbound on published challenge ports | Unsolicited outbound to player VLANs |
| 50 (Staff) | VLAN 10, 20, 30, 40, WAN | — |
| 10 (Management) | Self only from player/staff VLANs (block all inbound except from 50) | Player VLANs (30/40) fully blocked from reaching VLAN 10 |

Player-to-player isolation is enforced **twice per medium**, and the two
layers are different for Wi-Fi vs. wired:

- **Wi-Fi (VLAN 30):** AP-side Client Isolation (RF-level, stops traffic
  before it ever reaches the switch) plus the firewall's
  `block VLAN30net → VLAN30net` rule as defense-in-depth for any traffic
  that does make it to pfSense/OPNsense.
- **Wired (VLAN 40):** switch-level Port Isolation on ports 11–24 (§1
  above — this is the layer that actually stops ordinary same-switch
  traffic, which never reaches the firewall on its own) plus the
  firewall's `block VLAN40net → VLAN40net` rule, which only gets a
  chance to act because Port Isolation forces that traffic to hairpin
  through the router in the first place.

A player who plugs a switch into their own hardline port and connects a
second device to it still can't reach a neighbor on a different port,
since Port Isolation is enforced per-port on the core switch regardless
of what's plugged into an individual isolated port.

### "Challenge ports only" on VLAN 20 — the actual port list

If VLAN 20 runs `cei-labs-engine` (one reference deployment this network
supports, not a hard requirement — see
[`ecosystem-architecture.md`](ecosystem-architecture.md)), "challenge
ports" concretely means:

| Port(s) | Protocol | Purpose |
| :--- | :--- | :--- |
| 80, 443 | TCP | Traefik ingress (CTFd, and Traefik-routed challenge instances) |
| 30000–32767 | TCP | `cei-labs-engine`'s orchestrator: trusted per-instance gateway ports for single-target SSH and range-attacker SSH/noVNC, plus bulk-spawned analyst/Kali workspaces (see `ORCHESTRATOR_SSH_PORT_RANGE_START/END` and `ANALYST_BASE_PORT` in `cei-labs-engine`'s `docker/.env.example`) |

Any VLAN-20 deployment that isn't `cei-labs-engine` will have its own port
list — treat the table above as the concrete instance of "challenge ports
only" for that one reference deployment, not a universal constant.

### Swarm inter-node ports (multi-host VLAN 20 only)

If `cei-labs-engine` (or any Docker Swarm workload) spans more than one
physical host on VLAN 20, those hosts need to reach each other — not
players — on:

| Port(s) | Protocol | Purpose |
| :--- | :--- | :--- |
| 2377 | TCP | Swarm cluster management |
| 7946 | TCP + UDP | Node-to-node gossip |
| 4789 | UDP | Overlay network data path (VXLAN) |

This is intra-VLAN-20 traffic between the CTF Infra hosts themselves — it
does **not** need a player-facing firewall rule, since pfSense/OPNsense
don't restrict same-subnet host-to-host traffic by default. Only relevant
if VLAN 20 is deliberately built as a multi-node cluster; a single-host
VLAN 20 deployment can ignore this section entirely.
