# Headscale on the Edge for Remote Access

This document is the **plan + runbook** for spinning up a self-hosted
[Headscale](https://headscale.net) control server — an open-source
drop-in for the Tailscale coordination server — on the CEI-Labs edge
router so staff can reach the servers (CTF infrastructure, currently on the
`192.168.10.0/24` LAN) from anywhere without punching per-service firewall
holes.

> **Live topology (verified 2026-08-05 over SSH by @Codex 5.5):** the box is
> `cei-router.ctf.internal`, OPNsense 26.7. The deployment has shifted from
> the original five-VLAN design to a **simplified two-network topology**:
> - `em0` — LAN / management + CTF infra, `192.168.10.1/24`
> - `ue1` (`opt3`) — Player Wi-Fi, `10.10.32.1/22`
> - `ue0` — WAN
> - Stale `vlan01`–`vlan05` (tags 10/20/30/40/50) still exist on `em0` but are
>   **not** part of the active design.
> The subnet the tailnet should expose for server access is therefore
> **`192.168.10.0/24`** (not the older `10.10.20.0/24`). Player Wi-Fi
> `10.10.32.0/22` must NOT be advertised. If a dedicated server VLAN is later
> reintroduced, revisit this route.

Headscale only runs the **control plane** (node identity, netmap, ACLs).
Node-to-node traffic is encrypted WireGuard mesh with NAT traversal
handled by the Tailscale clients themselves, relayed through DERP when no
direct path exists. Headscale never touches the actual data-plane traffic.

## Platform

Nominal platform is **OPNsense** (confirmed by the operator 2026-08-05:
"i will be using opensense not pfsense"). This matters because —

- **Jails are a first-class OPNsense capability** but do not exist on
  pfSense. The upstream Headscale project and OPNsense users report running
  Headscale in a jail works out of the box
  ([juanfont/headscale#1533](https://github.com/juanfont/headscale/issues/1533)).
- OPNsense ships HAProxy + ACME plugins that are the natural way to get a
  real public TLS certificate in front of the jail (Headscale needs HTTPS;
  raw-IP or self-signed breaks most Tailscale clients).

If the box were pfSense (no jails, no jail manager), the Docker-on-VLAN-20
host path (Option B below) would be the fallback.
## Goals / non-goals

- **Goal:** a staff node anywhere on the internet can `tailscale up
  --login-server https://headscale.<domain>` and reach the LAN hosts
  (`192.168.10.0/24`, management + CTF infra) and the edge box.
- **Non-goal:** exposing any service to the public WAN directly. The only
  inbound WAN exposure this adds is HTTPS (443) to the Headscale control
  plane. Everything else happens inside the mesh.

## Network model (this box)

The box currently runs a **simplified two-network topology** (verified
2026-08-05), replacing the older five-VLAN router-on-a-stick design:

- **LAN** (`em0`): `192.168.10.1/24` — management + CTF infra together.
  This is the subnet the servers live on and the primary tailnet target.
- **Player Wi-Fi** (`ue1`/`opt3`): `10.10.32.1/22` — player-facing, isolated
  from the tailnet.
- **WAN** (`ue0`): upstream.

The `docs/network-topology.md` five-VLAN model (10 mgmt / 20 CTF / 30 player /
40 wired / 50 staff) is the older design; stale `vlan01`–`vlan05` interfaces
remain on `em0` but are not the active path.

Headscale places a node *inside* the network that advertises subnet routes
for the private range — remote peers reach **`192.168.10.0/24`** through it.
See "Subnet routers" below.

## Options

### Option A — Headscale jail on the OPNsense box (RECOMMENDED)

Create a FreeBSD jail (via OPNsense's built-in jail tooling / iocage) on the
edge box itself. Install the `headscale` package/binary inside it. Front it
with OPNsense HAProxy + ACME for real TLS on WAN 443 → jail.

- **Pros:** control plane lives on the always-on edge device (the box is the
  natural "choke point" for every staff VPN anyway); no dependency on the
  Docker host being up; matches the operator's "on the box" request.
- **Cons:** jail state is **not** captured by OPNsense's own configuration
  backup — the install must be reproducible from this doc; adds HAProxy/ACME
  surface to the edge.

### Option B — Headscale Docker on a LAN host (fallback)

Run Headscale as a container on a LAN host on `192.168.10.0/24` where the
servers run (e.g. the Docker/CTF infra host). OPNsense NATs WAN 443 → host;
TLS in the compose via Caddy/Traefik.

- **Pros:** consistent with the repo's existing Docker pattern
  (`docker/docker-compose.yml`); container is easy to back up and restore.
- **Cons:** depends on the Docker host being up; WAN 443 forwards all the way
  to the VM/container; not "on the box."

### Option C — bhyve VM on the OPNsense box

Run Headscale inside a FreeBSD/Linux VM under OPNsense bhyve.

- **Pros:** independent of the Docker host; physically on the box.
- **Cons:** heavier than a jail; overkill when jails are available. Only if
  Option A is somehow not viable on the installed version.

**This PR implements Option A** (jail + HAProxy/ACME), with Option B
documented as the fallback under `config/opnsense/headscale-notes.md`.

## Prerequisites

- OPNsense with a publicly reachable WAN (static IP or a DDNS-managed IP)
  and a **domain you control**. A real public FQDN is strongly preferred;
  `server_url` must be a valid `https://headscale.<domain>`.
- OPNsense **HAProxy** and **ACME** plugins installed
  (`System → Firmware → Plugins` → `os-haproxy`, `os-acme-client`).
- Jail tooling: `os-iocage` or OPNsense's built-in Jail management UI.

## Design decisions

| Decision | Choice | Why |
| :--- | :--- | :--- |
| Control plane location | Jail on the edge box | Always-on, natural VPN choke point; "on the box" |
| TLS | WAN 443 → HAProxy → jail (acme) | Real cert; Tailscale clients need HTTPS |
| Headscale port | 8080 inside jail | Default; reverse-proxied behind HAProxy |
| DB | SQLite | Single-operator tailnet; adequate |
| Auth | Preauth keys; OIDC recommended later | Default-deny posture matches this repo |
| MagicDNS | `tailnet.<domain>` | Internal names, not authoritative |
| Subnet routes | Advertise `192.168.10.0/24` via the edge as a subnet router | Reach LAN/CTF-infra hosts without agents on each |

## Open items (operator input before finalizing ACLs)

These were surfaced on the channel and remain open; the runbook below works
with the default assume-they-shall-be-decided values, but the **ACL section
changes based on the answers**:

1. **Public reachability:** confirm the FQDN (`headscale.<domain>`) that will
   resolve to the box's WAN IP. Fill `HEADSCALE_DOMAIN` with it.
2. **Node set ("the servers"):** exactly which hosts must be reachable
   remotely — the LAN `192.168.10.0/24` (management + CTF infra +
   `cei-router.ctf.internal`) — and whether a dedicated server VLAN is ever
   reintroduced. Used to scope the advertised
   subnet routes and the ACL allow-list.

---

## Runbook — Option A (jail + HAProxy/ACME)

### 1. Create the jail

Using OPNsense's Jail UI (or `iocage` CLI), create a jail `headscale`:

- IP: a static address on the LAN (`192.168.10.0/24`) reachable from the
  edge, e.g. `192.168.10.2/24`. Headscale only needs to be reachable by the
  edge's HAProxy (loopback/local) and by registered nodes on the WAN.
- Give it internet access for package install and for node coordination.
- Enable `allow_sysvipc`/`allow.mount` only if the package install requires
  them; keep it minimal.

### 2. Install Headscale inside the jail

```sh
# inside the jail
pkg install -y headscale
# or install a specific release binary from juanfont/headscale releases
```

Create data dir and config:

```sh
mkdir -p /var/lib/headscale /etc/headscale
headscale configdump > /etc/headscale/config.yaml
```

### 3. Configure `config.yaml`

Edit `/etc/headscale/config.yaml`. Key fields (values below are placeholders
to be set per the open items above):

```yaml
server_url: https://headscale.example.com        # HEADSCALE_DOMAIN
listen_addr: 0.0.0.0:8080                        # jail-local, proxied upstream
metrics_listen_addr: 127.0.0.1:9090              # not exposed to WAN
grpc_listen_addr: 127.0.0.1:50443
grpc_allow_insecure: false

noise:
  private_key_path: /var/lib/headscale/noise_private.key

prefixes_v4: [100.64.0.0/10]                     # default CGNAT v4
prefixes_v6: [fd7a:115c:a1e0::/48]               # default ULA v6

derp:
  auto_update_enabled: true
  update_frequency: 24h
  # Optionally run your own DERP later; default public DERP map is fine to start

dns:
  base_domain: tailnet.example.com               # base_domain (not AUTHORITATIVE)
  magic_dns: true
  nameservers:
    global:
      - 1.1.1.1
      - 8.8.8.8

# DMZ policy: client auth via preauth keys. OIDC section can be added later
# for staff SSO.
```

Enable and start:

```sh
sysrc headscale_enable=YES
service headscale start
```

Verify it's listening on 8080 within the jail before wiring the proxy.

### 4. Front it with OPNsense HAProxy + ACME (WAN 443 → jail 8080)

In OPNsense:

1. **ACME:** add the FQDN `headscale.<domain>` under
   `Services → ACME Client`, issue a Let's Encrypt cert for it (HTTP-01 or
   DNS-01). List this cert in HAProxy `Settings → Virtual Servers → Certificates`.
2. **HAProxy backend:** a backend server pointing at the jail `192.168.10.2:8080`.
   Headscale uses WebSocket/HTTP upgrades for the control connection — ensure
   HTTP/1.1 upgrade/websocket behaviour is enabled (default HAProxy handles
   `Upgrade`), and set `Connection` handling so the Noise upgrade isn't
   buffered.
3. **HAProxy frontend:** listen on `0.0.0.0:443`, map `headscale.<domain>` →
   backend, terminate the ACME cert.
4. **Firewall + NAT:** allow WAN → LAN TCP/443 and NAT it through to the jail
   (or HAProxy binds WAN directly). Keep the player VLANs' existing rules
   (`firewall-rule-order.md`) intact — this adds one inbound 443 rule only.
5. If HAProxy itself binds WAN 443, you may not need a separate NAT rule; if
   the jail `server_url` must be reachable on 443 from nodes, ensure the
   published `server_url` matches the HAProxy-public FQDN exactly.

> **Why this works:** Tailscale clients connect to `server_url` over 443 TLS.
> The Noise/handshake and subsequent control traffic is HTTP WebSocket-style;
> HAProxy terminates TLS and reverse-proxies 8080. Nodes on the WAN reach it
> through the public FQDN; nodes already on the LAN can use the same URL.

### 5. First run + create a user and preauth key

```sh
headscale users create staff
headscale nodes register --user staff \
  --key $(headscale nodes preauthkeys create --user staff --reusable --expiration 24h)
```

### 6. Connect a staff node

On a staff device:

```sh
# Linux / macOS
tailscale up --login-server https://headscale.example.com \
  --authkey <tskey-auth-...>
```

Windows (PowerShell):

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" up `
  --login-server "https://headscale.example.com" `
  --authkey "tskey-auth-..."
```

iOS/Android: set **Alternative Coordination Server** to the Headscale URL in
the Tailscale app, then authenticate.

### 7. Make the edge a subnet router (reach the LAN from anywhere)

The edge runs a Tailscale node that advertises the LAN subnet, so remote
staff nodes don't each need an agent on every server.

On the edge box (outside the jail), install the Tailscale binary and:

```sh
tailscale up --login-server https://headscale.example.com \
  --advertise-routes=192.168.10.0/24   # LAN: management + CTF infra
```

On the Headscale server, approve the route:

```sh
headscale nodes approve-routes -n <edge-node-id>   # or: routes in the node edit
```

> **Security check:** only advertise subnets you actually want reachable
> remotely, and reflect exactly that in the ACL allow-list (next section).
> Do **not** advertise the Player Wi-Fi subnet `10.10.32.0/22`.

### 8. ACLs (default-deny — edit `/etc/headscale/acl.hujson`)

Start with a fail-closed policy. Tune per the "node set" answer from the
open items above. Example:

```hujson
{
  "acls": [
    // Remote staff device -> LAN (management + CTF infra) only
    { "action": "accept", "src": ["tag:staff"], "dst": ["192.168.10.0/24:*"] },
    // Allow the subnet router to relay (it must see the hosts it advertises)
    { "action": "accept", "src": ["tag:edge"], "dst": ["192.168.10.0/24:*"] }
    // NO accept for the Player Wi-Fi subnet (10.10.32.0/22)
  ],
  "tagOwners": { "tag:staff": ["emailid:..."] }
}
```

Validate:

```sh
headscale acl validate -f /etc/headscale/acl.hujson
headscale acl save -f /etc/headscale/acl.hujson
```

### 9. Persistence / backup caveat

- The jail's config (`/etc/headscale`, `/var/lib/headscale`, the ACL file)
  is **not** part of OPNsense's configuration backup. Document the full
  install as steps **in this doc** (they are), and/or snapshot the jail/
  ZFS dataset (if the box uses ZFS) as part of the repo's normal backup
  narrative.
- TLS cert is managed by ACME; its private key lives in OPNsense's config
  export — good.

## Adding nodes / ongoing management (quick reference)

```sh
headscale users list                          # all users (a single tailnet)
headscale nodes list                          # registered nodes
headscale nodes register --user staff ...     # register by node key
headscale nodes delete <id>
headscale nodes preauthkeys list --user staff # active preauth keys
headscale nodes approve-routes -n <id>        # approve advertised subnets
headscale acl save -f /etc/headscale/acl.hujson
headscale debug tail                 # live control-plane log tail
```

## Related

- [`config/opnsense/headscale-notes.md`](../config/opnsense/headscale-notes.md) —
  OPNsense-specific jail / HAProxy / ACME and Option-B fallback notes.
- `docs/verification-checklist.md` §9 — remote-access verification checks.
- `docs/network-topology.md` — VLAN map this tailnet overlays.
