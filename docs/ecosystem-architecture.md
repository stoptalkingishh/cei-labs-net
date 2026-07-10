# CEI-Labs Ecosystem: How the Three Repos Interplay

`cei-labs-net` is one of three repositories that together make up a single
CTF/training deployment. None of the three is independently deployable —
each depends on the layer below it:

| Repo | Role | Depends on |
| :--- | :--- | :--- |
| [`cei-labs-net`](.) *(this repo)* | Physical/virtual network: VLANs, DNS control, per-player bandwidth limits, QoS, player isolation | Hardware only |
| [`cei-labs-engine`](https://github.com/stoptalkingishh/cei-labs-engine) | The platform that actually runs on VLAN 20: Docker Swarm stack (Traefik + CTFd + Challenge Instance Orchestrator + MariaDB/Redis + Juice Shop/Kali-noVNC/analyst containers) | `cei-labs-net`'s VLAN 20 host(s) and outbound internet (image pulls from GHCR) |
| [`CEI-Labs-Wargames`](https://github.com/stoptalkingishh/CEI-Labs-Wargames) | Challenge content pipeline: generates Bandit/Krypton/Natas-based challenge definitions and pushes them into a running CTFd via `ctfcli` | A reachable `cei-labs-engine` CTFd instance (`CTFD_URL` + `CTFD_TOKEN`) |

```
Player (VLAN 30/40)
   │  DNS forced to local Unbound, DoT/DoH/DoQ blocked,
   │  5/10 Mbit per-IP cap, QoS prioritizes DNS/ICMP/scoreboard
   ▼
pfSense/OPNsense  ──(cei-labs-net)──
   │  passes qHigh-tagged traffic through to VLAN 20
   ▼
VLAN 20 — CTF Infrastructure host(s), Docker Swarm  ──(cei-labs-engine)──
   │  Traefik (ports 80/443, Swarm routing mesh)
   ├─▶ CTFd (+ instance-launcher plugin) ──▶ MariaDB, Redis
   └─▶ Challenge Instance Orchestrator ──▶ per-team Juice Shop /
        target+attacker containers, on overlay networks that never
        include CTFd or the database

CEI-Labs-Wargames (run from a staff machine / CI, not on the player network)
   │  deploy.sh → ctfcli → CTFD_URL + CTFD_TOKEN
   ▼
Pushes Bandit/Krypton/Natas challenge YAML into the running CTFd above
```

## Concrete integration points

### 1. The "Scoreboard Engine host" this repo references is CTFd behind Traefik

`docs/security-qos-policy.md` and `docs/verification-checklist.md` refer to
`10.10.20.X` as the high-priority (`qHigh`) destination. In practice that's
**Traefik**, fronting CTFd on **ports 80/443** — `cei-labs-engine` uses
Swarm's routing mesh, so any Swarm node's IP on VLAN 20 answers on those
ports regardless of which node actually runs the container. The QoS/limiter
rules in this repo should match on `10.10.20.0/24:80,443`, not a single
hardcoded host IP, if the CTF Infra host list grows beyond one machine.

### 2. CTFd is reached by hostname, not bare IP — this affects DNS interception

`cei-labs-engine`'s Quick Start has players/staff open
`https://ctfd.<your-base-domain>`. Since `cei-labs-net`'s Unbound resolver
transparently intercepts **all** player DNS (see
`docs/security-qos-policy.md` §1), that base domain must resolve correctly
through the local resolver — either via a local DNS override/A-record
pointing `ctfd.<base-domain>` at the VLAN 20 host(s), or by ensuring
Traefik's TLS cert (`docker/traefik/certs/`, `dynamic/tls.yml.example` in
`cei-labs-engine`) matches whatever hostname the local override uses.
Without this, DNS interception (correctly) breaks access to the scoreboard
itself for anyone not using the exact configured hostname.

### 3. `docker/docker-compose.yml` in this repo is a standalone template, not how the engine deploys

`cei-labs-engine` deploys everything via `docker/stack.yml` under **Docker
Swarm**, driven by its own orchestrator service — not by hand-running
`docker compose up` per challenge. The hardened `docker-compose.yml`
template in this repo is a **reference for standalone/ad hoc challenge
containers deployed outside the orchestrator** (e.g. a one-off challenge
not wired into CTFd's instance-launcher), or as a hardening baseline to
compare `cei-labs-engine`'s own container configs against. It is not a
substitute for `cei-labs-engine`'s stack.

This also means the VLAN 20 host(s) need `docker swarm init` (single host)
or to be joined via `cei-labs-engine`'s `ansible/site.yml` (multi-host) —
not just a bare Docker Engine install — before `cei-labs-engine` can be
deployed. Update your build runbook accordingly.

### 4. Admin surface restriction is a shared responsibility

`cei-labs-engine`'s own security posture doc calls for minimizing exposure
of CTFd's `/admin` routes. `cei-labs-net`'s VLAN policy
(`docs/network-topology.md` §3) currently allows VLAN 30/40 → VLAN 20 on
"challenge ports only" — when implementing the actual firewall rule, scope
that explicitly to CTFd's public/API routes and exclude `/admin`, or add a
Traefik-level IP-allowlist/BasicAuth middleware restricting `/admin` to
VLAN 50 (Staff) and VLAN 10 (Management) only, per `cei-labs-engine`'s own
recommendation.

### 5. `CEI-Labs-Wargames` never touches the player network

`deploy.sh` runs `ctfcli` against `CTFD_URL`/`CTFD_TOKEN` — it's a
content-push step run once (or in CI) from a machine with API access to
CTFd, typically VLAN 50 (Staff) or an external CI runner reaching the venue
over VPN/WAN. It has no interaction with VLANs 30/40, the DNS/QoS policy,
or the Docker template in this repo. If run from CI, that CI runner's
egress IP needs to be allowed to reach CTFd's `/api/v1/*` — the
inter-VLAN policy table doesn't currently need any change for this, since
Staff (VLAN 50) already has unrestricted access to VLAN 20.

### 6. TLS trust — confirmed root cause and fix (live-tested)

Cloning both repos and running `cei-labs-engine`'s Swarm stack against
`CEI-Labs-Wargames`' `deploy.sh` locally surfaced the actual failure mode,
not just the suspected one:

- **What players see:** `cei-labs-engine`'s LAN/venue default
  (`USE_LETSENCRYPT=false`) presents a self-signed or staff-provided cert.
  A browser warning is expected and acceptable for a LAN event — no
  `cei-labs-net` action needed.
- **What broke `deploy.sh`:** the current `ctfcli` package (0.1.x) reads a
  config key called `ssl_verify` (default `True`) — **not** `insecure`,
  which `deploy.sh` was writing and which `ctfcli` silently ignores. Fixed
  in `CEI-Labs-Wargames` (Phase 4 of the integration work) with an opt-in
  `CTFD_INSECURE=true` env var that writes `ssl_verify = false` only when
  explicitly set. Confirmed live: `ctf challenge sync` succeeded end-to-end
  once this was in place.
- **`cei-labs-net` implication:** none directly — this was purely a
  `CEI-Labs-Wargames` config-generation bug. It's documented here because
  it was discovered while verifying this repo's DNS/TLS assumptions were
  accurate, and because whoever runs `deploy.sh` against a self-signed
  `cei-labs-engine` instance needs `CTFD_INSECURE=true` set.

### 7. Two of three curriculum tracks depend on the open internet, not VLAN 20

`CEI-Labs-Wargames`' Bandit and Krypton/Natas-style challenges (confirmed
by reading `scripts/build_bandit.py` etc.) are pure CTFd metadata — no
containers, no images — pointing players at real
`*.labs.overthewire.org` hosts over SSH (`bandit.labs.overthewire.org:2220`
and similar). This traffic never touches VLAN 20 at all.

Implication for `cei-labs-net`: this traffic needs outbound reachability
from VLAN 30/40, which the existing default-allow-to-WAN rule already
covers — no firewall change needed. But it rides the standard
`qDefault`/`Player_Upload`/`Player_Download` path, not `qHigh`, and a
venue internet outage or an OverTheWire outage silently breaks two of the
three curriculum tracks. Add a pre-event connectivity check to
`verification-checklist.md` (done) rather than assuming it's covered by
the VLAN-20 checks.

**Status update (2026-07-09):** all three tracks are being migrated to
self-hosted `cei-labs-engine` instances (one persistent SSH box per team
for Bandit/Krypton via `single-target`, one shared attacker + target
range per team for Natas via `target-attacker`) — see
`CEI-Labs-Wargames/docs/self-hosted-wargames-blueprint.md`. In progress
on a feature branch, not yet on `main` in either repo. Once merged, this
finding is resolved: no outbound-internet dependency, all traffic stays
on VLAN 20, and the connectivity check above becomes unnecessary (leave
it in the checklist until the migration actually lands on `main`).
Confirmed while building that migration: `single-target` (Bandit/Krypton)
already falls within the documented `30000–32767` range above;
`target-attacker` (Natas) uses Traefik exclusively (no directly-published
port at all for the attacker or target), so it needs nothing beyond the
already-documented `80,443` — **no `cei-labs-net` change is required**
for either instance type.

## What's out of scope for `cei-labs-net`

This repo does not, and should not, contain: CTFd configuration, challenge
content, container images for challenges, or Swarm stack definitions — all
of that lives in `cei-labs-engine` and `CEI-Labs-Wargames`. `cei-labs-net`'s
job ends at "VLAN 20 has connectivity, the right ports get priority, and
players can't bypass DNS/bandwidth controls to reach it or each other."
