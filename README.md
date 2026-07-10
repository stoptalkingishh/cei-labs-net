# CEI-Labs CTF Network Infrastructure

Configuration files, firewall rule sets, traffic shaping limits, and Docker
deployment structures required to host a high-density, zero-software-cost
Capture The Flag (CTF) environment for up to **80 active participants**.

This repository is **one of three** that together make up a full CTF/training
deployment — none of the three stands alone:

- [`cei-labs-engine`](https://github.com/stoptalkingishh/cei-labs-engine) — the platform itself: a Docker Swarm stack (Traefik + CTFd + Challenge Instance Orchestrator + Juice Shop/Kali-noVNC/analyst containers) that runs on the VLAN 20 host(s) this repo provisions
- [`CEI-Labs-Wargames`](https://github.com/stoptalkingishh/CEI-Labs-Wargames) — challenge content pipeline; pushes Bandit/Krypton/Natas-based challenges into a running `cei-labs-engine` CTFd instance via `ctfcli`
- `cei-labs-net` *(this repo)* — network, security, and container-hosting infrastructure that the other two run on top of

See [`docs/ecosystem-architecture.md`](docs/ecosystem-architecture.md) for
exactly how the three interconnect (DNS interception vs. CTFd's
hostname-based routing, what "Scoreboard Engine host" actually means,
where the Docker template in this repo fits vs. `cei-labs-engine`'s own
Swarm stack, and admin-surface isolation).

The core requirements this repo satisfies: a zero-cost software stack on a
**pfSense/OPNsense** core, paired with a multi-node budget wireless network,
that survives intense player-side network scanning (`nmap`, etc.), enforces
absolute isolation between players, caps overall data consumption, and
aggressively throttles non-essential traffic (streaming, game downloads, OS
updates) so bandwidth stays available for the CTF itself.

---

## Repository Layout

```
cei-labs-net/
├── README.md
├── docs/
│   ├── network-topology.md      # Physical wiring, VLAN/DHCP map, router-on-a-stick design
│   ├── security-qos-policy.md   # DNS interception, DoH/DoT/DoQ blocking, limiters, QoS queues
│   ├── verification-checklist.md # Pre-event runbook to confirm every control actually works
│   └── ecosystem-architecture.md # How this repo, cei-labs-engine, and CEI-Labs-Wargames fit together
├── config/
│   ├── pfsense/                 # pfSense XML fragments (aliases, limiters, NAT, filter rules)
│   └── opnsense/                # OPNsense equivalents (Shaper, Unbound, Zenarmor notes)
└── docker/
    ├── docker-compose.yml       # Reusable, hardened challenge deployment template
    └── .env.example
```

---

## Recommended Budget Hardware Blueprint

To maintain peak performance during intensive network scanning without
enterprise software licensing fees, we recommend the following hardware
profile:

| Component | Recommendation | Specifications / Notes |
| :--- | :--- | :--- |
| **Core Router / Firewall** | Refurbished SFF Desktop (e.g., Dell OptiPlex / HP ProDesk) | Intel Core i3/i5, 8GB RAM, 120GB SSD. Must install **pfSense** or **OPNsense** (Open Source). |
| **Network Interface Card** | PCIe Multi-Port Intel Gigabit NIC | **Critical:** Intel chipsets (e.g., i350-T4) to process high packet streams in hardware rather than overloading the host CPU. |
| **Core Switch** | 24-Port Managed Layer 2 Gigabit Switch | Must support **802.1Q VLAN tagging**, Access Control Lists (ACLs), and per-port **Port Isolation** (a.k.a. Protected Ports / Private VLAN Edge) — required on the wired player ports, VLAN tagging alone is not sufficient for peer isolation. **RA-Guard** recommended if available (blocks rogue IPv6 router advertisements on player ports — see `docs/network-topology.md` §1). (e.g., TP-Link JetStream series). |
| **Wireless Access Points** | 3 to 4 Multi-Node Business APs | **Minimum Wi-Fi 6 (802.11ax)** capable of broadcasting multiple SSIDs mapped to VLANs with **Client Isolation** enabled. |

See [`docs/network-topology.md`](docs/network-topology.md) for the full
wiring diagram and VLAN/subnet map, and
[`docs/security-qos-policy.md`](docs/security-qos-policy.md) for the
DNS-lockdown, traffic-shaping, and QoS configuration.

---

## Quick Start

1. Image the core router box with pfSense or OPNsense and complete the
   interface assignment wizard (WAN + LAN trunk).
2. Follow [`docs/network-topology.md`](docs/network-topology.md) to lay out
   VLANs 10/20/30/40/50 on the core switch and APs.
3. Apply the firewall/NAT/limiter rules in
   [`docs/security-qos-policy.md`](docs/security-qos-policy.md) (reference
   fragments live under `config/pfsense/` and `config/opnsense/`).
4. Stand up the CTF Infrastructure host(s) on VLAN 20 (`docker swarm init`,
   or join via `cei-labs-engine`'s Ansible playbook for multi-host) and
   deploy [`cei-labs-engine`](https://github.com/stoptalkingishh/cei-labs-engine)'s
   Swarm stack — that's what actually serves CTFd/Traefik/challenges on
   this VLAN. The hardened template in
   [`docker/docker-compose.yml`](docker/docker-compose.yml) here is for
   standalone challenge containers deployed *outside* that orchestrator,
   not a replacement for it (see
   [`docs/ecosystem-architecture.md`](docs/ecosystem-architecture.md) §3).
5. Before opening registration, run every check in
   [`docs/verification-checklist.md`](docs/verification-checklist.md) —
   isolation, DNS interception, DoT/DoH/DoQ blocking, limiters, QoS, and
   Docker hardening all need to be confirmed live, not assumed from config.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
