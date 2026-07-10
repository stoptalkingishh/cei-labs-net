# Security Policy, Routing Prevention & QoS Throttling

Zero-cost enforcement of DNS control, bandwidth fairness, and application
throttling on **pfSense** (Unbound + Limiters + Snort/OpenAppID) or
**OPNsense** (Unbound + Shaper + Zenarmor Free). Reference rule fragments
live under `config/pfsense/` and `config/opnsense/`; this doc is the
authoritative step-by-step for both platforms.

---

## 1. Foolproof DNS Interception (NAT Port Forward)

Goal: players cannot bypass the resolver by hardcoding `8.8.8.8` / `1.1.1.1`
(or any other DNS server) — **all** port-53 traffic leaving VLAN 30/40 gets
transparently redirected to the local Unbound resolver, regardless of what
destination IP the client thinks it's talking to.

**pfSense: Firewall → NAT → Port Forward**

| Field | Value |
| :--- | :--- |
| Interface | `vlan30_player`, `vlan40_player` (one rule per interface, or a floating rule applied to both) |
| Protocol | `TCP/UDP` |
| Destination | `any` |
| Destination port range | `53 (DNS)` |
| Redirect target IP | `127.0.0.1` (local Unbound resolver) |
| Redirect target port | `53` |
| Filter rule association | `Add associated filter rule` (auto-creates the pass rule) |

> pfSense/OPNsense both require **NAT reflection** to be permitted for this
> to work when the redirect target is the router's own loopback — this is
> handled automatically when the rule targets `127.0.0.1`, but confirm under
> System → Advanced → Firewall & NAT that "Reflection for port forwards" is
> not globally disabled.

**OPNsense: Firewall → NAT → Port Forward** — identical fields, same
outcome; OPNsense will also auto-generate the matching filter rule if you
leave "Automatically add a rule" checked.

XML reference: [`config/pfsense/dns-redirect-nat.xml`](../config/pfsense/dns-redirect-nat.xml)

> **If VLAN 20 runs `cei-labs-engine`:** the local Unbound resolver also
> needs a **wildcard** DNS override for `*.${BASE_DOMAIN}` (e.g.
> `*.ctf.local`), not just a single `ctfd.<domain>` A-record — Traefik
> routes both the fixed `ctfd.${BASE_DOMAIN}` hostname *and* per-team
> instance subdomains like `team-42-juice-shop.apps.${BASE_DOMAIN}`
> generated on demand by the orchestrator. A single non-wildcard override
> only covers the scoreboard, not challenge instances. See
> [`ecosystem-architecture.md`](ecosystem-architecture.md) §2 and §6.

---

## 2. Advanced Bypass Prevention (DoH / DoT)

Redirecting port 53 stops plain DNS, but modern clients (browsers, OSes)
fall back to encrypted DNS which rides over normal HTTPS/TLS ports and is
invisible to the port-53 NAT rule above.

**Block DNS-over-TLS (DoT), port 853**

Firewall → Rules → `vlan30_player` / `vlan40_player` — add a **Block** rule
above the general allow rule:

| Field | Value |
| :--- | :--- |
| Action | Block |
| Protocol | TCP |
| Destination port | `853` |
| Description | `Block DoT (DNS-over-TLS)` |

**Block DNS-over-HTTPS (DoH)**

DoH rides on port 443 alongside normal HTTPS, so it can't be blocked by
port alone — it requires signature/hostname-based blocking:

- **pfSense (Unbound / DNS Resolver):** Services → DNS Resolver → enable
  **"Python Module"** and turn on the built-in DoH blocklist option, or
  install the free `pfBlockerNG` package and subscribe to a public DoH
  provider IP/domain feed (e.g., the community-maintained
  `dns-doh-providers` list). Apply the feed as a block list on the
  WAN-facing firewall rule for player VLANs.
- **OPNsense (Unbound):** Services → Unbound DNS → General → enable
  **"Block DoH Servers"** (Unbound ships a maintained list of known public
  DoH endpoint domains/IPs under `unbound/doh_domains` / `doh_ips`). This
  is free and requires no additional package.

Both toggles are best-effort (the list of public DoH endpoints changes),
so treat this as defense-in-depth on top of the port-53 NAT redirect, not a
standalone guarantee.

XML reference: [`config/pfsense/block-dot-doh.xml`](../config/pfsense/block-dot-doh.xml)

---

## 3. Data Mitigation & Per-IP Traffic Shaper Limiters

Two `dummynet`-backed limiter pipes, masked per-source/per-destination
address so bandwidth is allocated **per player IP**, not shared globally —
one heavy downloader can't starve the rest of the room.

**pfSense/OPNsense: Firewall → Shaper → Limiters → New Limiter**

| Limiter | Bandwidth | Mask | Applied Direction |
| :--- | :--- | :--- | :--- |
| `Player_Upload` | `5 Mbit/s` | Source address (`/32` per IP) | In on VLAN30/40 (upload = client → WAN) |
| `Player_Download` | `10 Mbit/s` | Destination address (`/32` per IP) | Out on VLAN30/40 (download = WAN → client) |

Attach both limiters to a floating firewall rule (or the per-VLAN outbound
allow rule) covering VLAN 30 and VLAN 40 traffic to WAN, with
`Player_Upload` set as the "In" pipe and `Player_Download` set as the "Out"
pipe. Because the mask is per-address, pfSense/OPNsense dynamically spins up
a sub-queue per client IP under the hood — no per-player rule duplication
needed.

XML reference: [`config/pfsense/limiters.xml`](../config/pfsense/limiters.xml)

---

## 4. Quality of Service (QoS) & Application Throttling ("The Penalty Box")

A priority-queue layer sits **above** the per-IP limiters so that,
regardless of a player's remaining 5/10 Mbit budget, latency-sensitive CTF
traffic is never queued behind bulk transfers, and known bandwidth-abuse
traffic is shoved into a deliberately crippled pipe.

### 4.1 Priority Queues (Firewall → Shaper → Queues, under a `PRIQ` or `HFSC` root)

| Queue | Priority | Matches |
| :--- | :--- | :--- |
| `qHigh` | **7 (highest)** | DNS (port 53 — post-NAT-redirect traffic to Unbound), ICMP (ping), any traffic to `10.10.20.0/24` (the CTF Infra subnet — CTFd/Traefik on ports 80/443; matches on the subnet, not a single host, since `cei-labs-engine` can span multiple Swarm nodes) |
| `qInteractive` | **4** | SSH (port 22); HTTP/HTTPS to published challenge ports on VLAN 20; `10.10.20.0/24:30000-32767` (`cei-labs-engine`'s orchestrator-allocated SSH/analyst-workspace ports, live-confirmed — see `network-topology.md` "Challenge ports only") |
| `qDefault` | 2 | Everything else not otherwise classified |

See [`ecosystem-architecture.md`](ecosystem-architecture.md) for what
actually runs behind that subnet (`cei-labs-engine`'s Traefik/CTFd/
orchestrator stack) and why hostname-based routing matters for the DNS
interception rule in §1 above.

Bulk/streaming/update traffic is **not** a fourth priority queue — it is
diverted into the `Heavy_Traffic_Throttle` limiter pipe instead (§4.2),
which enforces a hard 256 Kbit/s ceiling rather than a scheduling priority.
`config/pfsense/qos-queues.xml` therefore only defines three `<queue>`
elements; do not create a `qHeavyThrottle` queue object in the GUI.

Implement via **Firewall → Rules**, per VLAN 30/40, ordered top-to-bottom:
rules for `qHigh` matches first (DNS/ICMP/scoreboard-IP), then
`qInteractive` (SSH/HTTP/HTTPS-to-VLAN20), then a catch-all into
`qDefault`. Each rule sets its "Queue" (pfSense) / "Set queue" (OPNsense)
field accordingly — no separate NAT step needed here, this is pure traffic
shaping on already-permitted traffic.

### 4.2 The "Slow-Mo" Throttle Pipe

A dedicated, brutally narrow limiter for confirmed bandwidth-hog
applications — not meant to be usable, meant to be a deterrent:

**Firewall → Shaper → Limiters → New Limiter**

| Field | Value |
| :--- | :--- |
| Name | `Heavy_Traffic_Throttle` |
| Bandwidth | `256 Kbit/s` |
| Mask | Source address (so the penalty applies per offending client, not shared across all offenders) |

### 4.3 Application Matching → Layer 7 DPI

Port/protocol rules alone can't catch BitTorrent, Steam, Netflix, YouTube,
or Windows Update — these need signature-based deep packet inspection.
Both options below are free:

- **pfSense:** Install **Snort** (System → Package Manager) and enable the
  **OpenAppID** detection engine under Snort → Global Settings. Enable
  application signatures for: `bittorrent`, `steam`, `netflix`, `youtube`,
  `windowsupdate` (and similar OS-update signatures for macOS/Linux package
  managers if relevant). Configure Snort in **IPS mode is not required** —
  for shaping purposes, use Snort's App ID detection combined with a
  `pfSense` **floating rule + Layer7/App-ID alias** (or, on newer pfSense,
  feed matched flows into a dedicated firewall alias table via the
  `snort2c` / app-detection hook) and point that alias's firewall rule at
  the `Heavy_Traffic_Throttle` limiter/queue.
- **OPNsense:** Install **Zenarmor (Sunny Valley) Free** (System → Firmware
  → Plugins → `os-sensei`, then enable the free tier). Zenarmor Free
  includes application/category signatures — enable categories for
  **Peer-to-Peer/BitTorrent**, **Gaming Downloads (Steam)**, **Streaming
  Media (Netflix, YouTube)**, and **Software Updates**. Under Zenarmor →
  Policies, create a policy that matches those categories and sets the
  **traffic shaper action** to the `Heavy_Traffic_Throttle` pipe (Zenarmor
  integrates directly with the native OPNsense Shaper, so no manual alias
  bridging is required).

Result: any packet matching those signatures is immediately reclassified
into `Heavy_Traffic_Throttle` (256 Kbit/s) regardless of the player's
remaining `Player_Download`/`Player_Upload` budget — bulk/streaming/update
traffic is throttled to a crawl while CTF-relevant traffic (DNS, scoreboard,
challenge ports, SSH) rides the priority queues untouched.

### Rule ordering (top to bottom, per player VLAN)

1. Block VLAN30↔VLAN30 / VLAN40↔VLAN40 (player isolation — see topology doc)
2. Block outbound TCP/853 (DoT)
3. DNS NAT redirect (→ `127.0.0.1:53`) → tag `qHigh`
4. ICMP → tag `qHigh`
5. Traffic to `10.10.20.0/24` (Scoreboard/CTF Infra) → tag `qHigh`
6. Traffic to `Wargame_Reference_Sites` alias (§4.4) → tag `qInteractive`
7. App-ID/Zenarmor match (BitTorrent/Steam/Netflix/YouTube/Updates) → `Heavy_Traffic_Throttle`
8. SSH (22), HTTP/HTTPS to VLAN 20 challenge ports → tag `qInteractive`
9. Default allow to WAN → tag `qDefault`, in/out through `Player_Upload` / `Player_Download` limiters

Rule 6 must sit **above** rule 7 — the whole point of the dedicated
alias rule is to guarantee these specific hosts land in `qInteractive`
before the App-ID/Zenarmor bulk-signature match ever gets a chance to
reclassify them into `Heavy_Traffic_Throttle`.

XML reference: [`config/pfsense/qos-queues.xml`](../config/pfsense/qos-queues.xml),
notes: [`config/opnsense/zenarmor-shaper-notes.md`](../config/opnsense/zenarmor-shaper-notes.md)

### 4.4 Guaranteed-Reachable Reference Sites (Wargame Allowlist)

Player VLANs already default-allow to WAN (§ rule 9 above) — general
internet access already works, this section does **not** restrict it
further. Its purpose is narrower and additive: the self-hosted wargames
content (`CEI-Labs-Wargames`, see
[`docs/network-access.md`](https://github.com/stoptalkingishh/CEI-Labs-Wargames/blob/main/docs/network-access.md)
in that repo) links a small, fixed set of external reference pages
directly from challenge hints/descriptions — Wikipedia articles and a
handful of technical references. Without an explicit rule, those hosts
would fall through to the default WAN rule (§4.3's App-ID/Zenarmor
match runs *before* the default-allow catch-all), which risks an
overzealous DPI signature (e.g. a broad "Software Updates" or
CDN-category match) throttling a page a participant is actively trying
to read mid-challenge, to 256 Kbit/s, with no obvious cause from the
player's side.

**pfSense/OPNsense: Firewall → Aliases → New Alias**

| Field | Value |
| :--- | :--- |
| Name | `Wargame_Reference_Sites` |
| Type | `Host(s)` (FQDN entries — pfSense/OPNsense periodically re-resolve these via DNS on their own, no manual IP maintenance needed) |
| Hosts | `en.wikipedia.org`, `git-scm.com`, `help.ubuntu.com`, `jwiegley.github.io`, `linux.die.net` |

Add a **pass** rule on `vlan30_player`/`vlan40_player`, matching TCP
80/443 to this alias, tagged `qInteractive`, placed above the App-ID/
Zenarmor match rule (rule ordering item 6, above).

XML reference: [`config/pfsense/wargame-reference-allowlist.xml`](../config/pfsense/wargame-reference-allowlist.xml)

**Keeping this list current:** the domain list is generated from the
"Helpful reading" links embedded in `CEI-Labs-Wargames`' challenge
build scripts (`scripts/build_bandit.py`, `build_krypton.py`,
`build_natas.py`). See that repo's `docs/network-access.md` for the
audit command and the per-domain justification. Whenever a wargame
content update adds a new external reference link, both this alias and
that doc need the same addition — treat `docs/network-access.md` as the
source of truth, this alias as its network-side mirror.
