# OPNsense: Headscale Jail, HAProxy/ACME, and Docker Fallback

OPNsense-specific implementation notes for the Headscale remote-access
runbook ([`docs/headscale-remote-access.md`](../../docs/headscale-remote-access.md)).
Assumes OPNsense on the CEI-Labs edge box, router-on-a-stick topology,
VLAN 20 = CTF Infrastructure (`10.10.20.0/24`).

## 1. Install the plugins

`System → Firmware → Plugins`:

- `os-iocage` (or use the built-in `System → Jail` management, if present on
  your OPNsense version) — jail provisioner.
- `os-haproxy` — reverse proxy / TLS termination.
- `os-acme-client` (installs with `os-haproxy` typically) — Let's Encrypt.

Reinstall on an OPNsense upgrade (jail contents persist separately, but the
plugins are part of the base system image and must be added to a fresh
install).

## 2. Create the Headscale jail

Via the Jail UI (`System → Jail → Add`) or `iocage`:

| Field | Value |
| :--- | :--- |
| Name | `headscale` |
| Interface | one reachable by HAProxy (e.g. VLAN 10 mgmt `10.10.10.2/24`) |
| IPv4 | `10.10.10.2` static, gateway = edge box `10.10.10.1` |
| Internet access | enabled (for `pkg install` and node coordination) |
| Sysvipc / mounts | only what the package install requires; keep minimal |

Record the jail's IP — the HAProxy backend will point at it.

## 3. Install Headscale in the jail

```sh
# inside the jail
pkg install -y headscale
mkdir -p /var/lib/headscale /etc/headscale
headscale configdump > /etc/headscale/config.yaml
# edit config.yaml per the runbook, then:
sysrc headscale_enable=YES
service headscale start
```

Headscale listens on `0.0.0.0:8080` inside the jail. **Do not** expose 8080
to the WAN — only HAProxy reaches it on the LAN side.

## 4. HAProxy + ACME in front

1. **ACME** (`Services → ACME Client`): issue a cert for `headscale.<domain>`.
   Add the cert to `HAProxy → Settings → Virtual Servers → Certificates`.
2. **Backend** (`Services → HAProxy → Backend`): one server = jail
   `10.10.10.2:8080`.
   - Health check: http on path `/health` (Headscale serves `/health`), or
     no health check and rely on HAProxy upstream failure handling.
3. **Frontend** (`Services → HAProxy → Frontend`):
   - Bind `0.0.0.0:443` (or a specific WAN IP).
   - Map `headscale.<domain>` (rule → ACL `req.hdr(Host)`) to the backend.
   - Terminate the ACME cert; HTTP/1.1. WebSocket/upgrade for the Noise
     control connection is handled by default (do not force HTTP/2-only).
4. **NAT** (`Firewall → NAT → Port Forward`): only if HAProxy does **not**
   bind the WAN IP directly. If it binds WAN, no extra NAT rule is needed.
   Prefer binding WAN in HAProxy to keep the port-forward surface minimal.
   If a port-forward is used: WAN `443 → 10.10.10.2:8080`, interface WAN,
   redirect local = yes.
5. Keep the existing player-VLAN rules; this adds exactly one inbound 443
   rule, and it is Haproxy-terminated (no raw WAN → jail hole).

> **WebSocket caveat:** Tailscale clients speak a WebSocket/HTTP-upgrade
> protocol to the control server. OPNsense HAProxy handles `Upgrade`/`
> websocket` by default, but if you see `noise handshake failed` / "message
> authentication failed" in `headscale debug tail`, the usual cause is
> HAProxy or an intermediate proxy buffering the connection. Ensure the
> frontend does not force HTTP/2 and that `Connection: upgrade` is passed
> through.

## 5. Verify reachability

From a WAN-side client (hostile-network test, not local):

```sh
curl -sI https://headscale.example.com/health   # 200 OK
tailscale up --login-server https://headscale.example.com --authkey <key>
tailscale status                                 # connected
```

A failed `headscale debug tail` handshake while `curl /health` succeeds
points squarely at the HAProxy upgrade/WebSocket handling, not at DNS or the
jail service.

## 6. Option B fallback — Headscale Docker on the VLAN 20 host

If a jail on the box isn't viable, run Headscale as a container on the
existing VLAN 20 Docker host. Reference compose (keep the hardened posture of
`docker/docker-compose.yml` in mind — read_only, no-new-privileges, resource
caps):

```yaml
services:
  headscale:
    image: headscale/headscale:latest
    container_name: headscale
    restart: unless-stopped
    ports:
      - "8080:8080"         # proxied, not WAN-exposed
      - "9090:9090"         # metrics, LAN-only
    volumes:
      - ./config:/etc/headscale
      - ./data:/var/lib/headscale
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop: [ALL]
    pids_limit: 128
    mem_limit: 256m
```

Then OPNsense port-forwards WAN `443 → <docker-host>:8080` (or the compose
adds Caddy to terminate TLS on 443 and forwards `443 → caddy:443`).

> Fallback only — Option A (jail on the box) is the recommended path.
