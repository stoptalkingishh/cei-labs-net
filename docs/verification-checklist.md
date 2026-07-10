# Pre-Event Verification Checklist

Every control described in this repo (`network-topology.md`,
`security-qos-policy.md`, `docker/docker-compose.yml`) must be tested from a
**client on VLAN 30 or VLAN 40** — not from the pfSense/OPNsense box itself
— since firewall-local traffic doesn't traverse the same rules as player
traffic. Run this full pass at least once during setup, and re-run the
"Day-Of Smoke Test" section after final hardware placement.

Use a single throwaway test laptop/VM connected to Player Wi-Fi (VLAN 30)
and, separately, a wired hardline port (VLAN 40) for each check below.

---

## 0. IPv6 lockdown

- [ ] `ipconfig /all` (Windows) or `ip -6 addr` (Linux/macOS) on a VLAN
      30/40 client shows **no IPv6 address at all** — not even a
      link-local (`fe80::...`) address obtained via router
      advertisement from pfSense/OPNsense itself (a link-local address
      the OS assigned to itself with no router involved is expected and
      fine; one that shows a non-`fe80` global/ULA prefix, or DNS
      servers listed under an IPv6 adapter, means SLAAC/RA is active
      somewhere and layer 2 of `security-qos-policy.md` §0 isn't
      actually working).
- [ ] `ping -6` (or `ping6`) to a known public IPv6 host (e.g.
      `2606:4700:4700::1111`) from a VLAN 30/40 client **fails** —
      confirms IPv6 is genuinely blocked/unreachable, not just
      unconfigured on the client by coincidence.
- [ ] If the core switch supports RA-Guard: confirm it's enabled on at
      least one wired player port (11–24) via the switch admin UI —
      full traffic-level RA-spoofing verification is optional (it's a
      defense-in-depth layer behind the system-level IPv6 disable
      above, not the primary control).

## 1. VLAN & DHCP sanity

- [ ] Client on VLAN 30 Wi-Fi receives an address inside `10.10.32.0/22`
      with gateway `10.10.32.1` (`ipconfig`/`ip a`).
- [ ] Client on VLAN 40 wired port receives an address inside
      `10.10.40.0/24` with gateway `10.10.40.1`.
- [ ] Docker host NIC (port 10) is untagged and lands on `10.10.20.0/24`.
- [ ] Lease time on VLAN 30/40 shows 7200s (`ipconfig /all` → "Lease
      Obtained/Expires" delta, or `ip addr show` + `dhclient -v` output).

## 2. Player isolation (VLAN30↔VLAN30, VLAN40↔VLAN40, cross-VLAN)

- [ ] Two test clients on VLAN 30 Wi-Fi (same SSID) **cannot** ping or
      reach each other (`ping <peer-ip>` times out) — confirms AP Client
      Isolation.
- [ ] Switch admin UI shows **Port Isolation** (a.k.a. Protected Ports /
      Private VLAN Edge) enabled on every port in 11–24, with Port 1 set
      as the permitted uplink — check this **before** the ping test
      below; it's the layer that actually matters, the firewall rule is
      backup (see `network-topology.md` §1's callout).
- [ ] Two test clients on VLAN 40 wired ports **cannot** ping each other
      — this is switch-level Port Isolation doing the real work; the
      firewall's `block VLAN40net → VLAN40net` rule only ever sees this
      traffic *because* Port Isolation forces it up to the router first
      (a firewall rule alone cannot stop ordinary same-switch traffic —
      confirm this isn't accidentally passing by disabling Port
      Isolation alone and re-testing; the ping should then succeed,
      proving the firewall rule was never actually reaching it).
- [ ] VLAN 30/40 client **cannot** reach `10.10.10.0/24` (Management) or
      `10.10.50.0/24` (Staff) — `ping`/`nmap -p 22,443` should be fully
      blocked.
- [ ] VLAN 30/40 client **can** reach published challenge ports on
      `10.10.20.0/24` (Docker host / CTF Infra), including the
      `30000-32767/tcp` range if VLAN 20 runs `cei-labs-engine` (its
      orchestrator's SSH/analyst-workspace ports — confirm with
      `nc -zv <ctf-infra-ip> 32000` or similar against a real allocated
      instance).
- [ ] `nmap -sn 10.10.32.0/22` from a player client returns **no other
      hosts** besides the gateway (validates isolation holds up under an
      actual scan, since the event explicitly expects players to run
      `nmap`).

## 3. DNS interception

- [ ] `nslookup example.com 8.8.8.8` from a VLAN 30/40 client still returns
      a resolved answer (proves it was silently redirected, not dropped)
      **and** `dig +short CHAOS TXT id.server @8.8.8.8` (or equivalent
      Unbound diagnostic query) identifies the local resolver, not Google's.
- [ ] Same test against `1.1.1.1` and at least one lesser-known public
      resolver.
- [ ] Confirm via `Diagnostics → States` (pfSense) or `Firewall → Log Files
      → Live View` (OPNsense) that the port-53 NAT redirect rule is
      matching player-VLAN traffic during the test.
- [ ] A domain on Unbound's blocklist (if any content filtering is layered
      on top) resolves/fails as expected — confirms the redirect actually
      lands on the intended Unbound instance, not just any resolver.
- [ ] If VLAN 20 runs `cei-labs-engine`: confirm the **wildcard** override
      resolves both the fixed hostname (`ctfd.<base-domain>`) and a
      synthetic subdomain under the instance pattern (e.g.
      `test.apps.<base-domain>`) — a non-wildcard override will pass the
      first check and silently fail the second, breaking every
      orchestrator-launched challenge instance for players. See
      `ecosystem-architecture.md` §2.
- [ ] Confirm outbound reachability to `*.labs.overthewire.org` (e.g.
      `nc -zv bandit.labs.overthewire.org 2220`) from a VLAN 30/40 client —
      if `CEI-Labs-Wargames`' Bandit/Krypton/Natas content is deployed,
      two of the three curriculum tracks depend on this external service
      being reachable, not on VLAN 20 at all (`ecosystem-architecture.md`
      §7). A venue firewall or filtering proxy blocking non-standard SSH
      ports would silently break these tracks.

## 4. DoT / DoH bypass prevention

- [ ] `openssl s_client -connect 1.1.1.1:853` from a player client fails to
      connect (confirms port 853 block).
- [ ] A browser on the test client with DoH manually enabled and pointed at
      a known public DoH endpoint (e.g. Cloudflare's `1.1.1.1` DoH profile)
      either fails to resolve or is observably intercepted — check
      `Firewall → Log Files` for a block hit, or confirm resolution still
      routes through local Unbound.
- [ ] Note in the event runbook that DoH blocking is best-effort (signature
      list-based) — do not treat step 2 as a hard guarantee, only as
      confirmation the current list is working.

## 5. Per-IP bandwidth limiters

- [ ] Single client speed test (e.g. `iperf3` against a controlled server,
      or a real speed-test site) on VLAN 30/40 caps at **~5 Mbit/s
      upload** and **~10 Mbit/s download** (small variance from TCP
      overhead is expected).
- [ ] Two simultaneous clients each independently hit ~5/10 Mbit/s (not
      splitting a shared 5/10 pool) — confirms the per-source/per-destination
      mask is actually creating dynamic per-IP sub-queues
      (`Status → Queues` / `Diagnostics → Limiter Info` should show
      multiple dynamic pipe instances).

## 6. QoS priority queues

- [ ] While a client is saturating its `Player_Download` limiter (e.g.
      running the speed test from §5), a `ping` to `10.10.20.1` (or another
      VLAN 20 host) from the **same client** stays low-latency
      (sub-50ms-ish on local network, not spiking to seconds) — confirms
      `qHigh` is protecting ICMP/scoreboard traffic from bulk-traffic
      queuing delay.
- [ ] DNS resolution latency stays low under the same saturated-link
      condition.
- [ ] SSH interactive session (`qInteractive`) to a challenge host stays
      responsive (no multi-second keystroke lag) while the link is
      saturated by a background download.

## 7. Application throttling ("Slow-Mo" pipe)

- [ ] From a test client, initiate a BitTorrent download (use a legal
      test torrent, e.g. a Linux ISO torrent) — confirm via
      `Firewall → Shaper → Pipes → Heavy_Traffic_Throttle` (pfSense) or
      `Zenarmor → Reports → Application Usage` (OPNsense) that the flow is
      detected and throughput drops to ~256 Kbit/s.
- [ ] Repeat for a Steam download, and for YouTube/Netflix playback —
      confirm each buffers/stalls consistent with a 256 Kbit/s cap.
- [ ] Trigger a Windows Update check/download on a Windows test client —
      confirm it's caught by the same signature set and throttled.
- [ ] Confirm CTF-relevant HTTP/HTTPS traffic to challenge ports on VLAN 20
      is **not** misclassified into the throttle pipe (false-positive
      check) — load a challenge web page and confirm normal speed.

## 8. Docker challenge hardening

Run these against a disposable test service deployed from
`docker/docker-compose.yml`:

- [ ] `docker inspect <container>` shows `"Privileged": false`,
      `"ReadonlyRootfs": true`, and `CapDrop: ["ALL"]`.
- [ ] Attempt a fork bomb inside the container (`:(){ :|:& };:` or
      equivalent, in an isolated test — **do not run this against a
      production challenge container**) and confirm `pids_limit: 128`
      stops it from taking down the host (`docker stats` shows the
      container hitting its pid ceiling and erroring, host stays
      responsive).
- [ ] Confirm the CPU ceiling: run a busy loop inside the container
      (`docker exec <container> sh -c "yes > /dev/null &"`, repeat 2-3x to
      spin multiple cores' worth of load) and watch `docker stats
      <container>` — CPU% should plateau around `50%` (one core =
      `100%` in `docker stats` accounting), confirming `cpus: 0.5` is
      capping it rather than letting it consume the whole host CPU.
- [ ] Confirm the container cannot reach the infra/engine network:
      `docker exec <container> ping <engine-host-ip>` fails (validates
      `challenge_net` isolation from `infra_net`).
- [ ] Confirm the restart cap, **not** with `docker kill`/`docker stop` —
      Docker treats those as user-initiated and will not re-trigger
      `on-failure` at all (`RestartCount` stays 0 no matter how many times
      you kill it). Instead override the test container's command to fail
      on its own, e.g. add a `docker-compose.override.yml` setting
      `command: ["sh", "-c", "exit 1"]`, bring it up, wait ~10s, and confirm
      `docker inspect <container> --format '{{.RestartCount}} {{.State.Status}}'`
      shows `5 exited` — Docker retried exactly 5 times on genuine failure,
      then stopped.
- [ ] Confirm memory ceilings hold under real memory pressure. Installing a
      stress tool via a package manager (`apk add stress`) will fail inside
      the hardened container — `read_only: true` blocks the package
      manager's own lock/log files, which is itself confirmation the
      read-only rootfs is working. Either (a) bake a stress tool into the
      challenge image at build time and run it against the real container,
      or (b) validate the underlying mem_limit/OOM mechanism directly with
      a throwaway container at the same limit:
      `docker run --rm --memory=256m alpine sh -c "a=$(cat /dev/zero | tr '\0' 'a' | head -c 400000000); echo done"`
      — expect exit code `137` (SIGKILL from the memory cgroup), confirming
      the same `mem_limit` value used in `docker-compose.yml` gets enforced
      by the host.

---

## Day-Of Smoke Test (abbreviated, run after final hardware placement)

Run this 10-minute pass after APs/switch are physically placed and powered
in their final event positions, since RF conditions and cable runs can
surface issues not present during bench testing:

1. Connect to each of the 3–4 Player Wi-Fi APs individually (not just the
   nearest one) and repeat §1 (DHCP) and §2 (isolation) once per AP.
2. Run one DNS interception check (§3) and one bandwidth check (§5) from
   the wired hardline row.
3. Confirm CTFd (`cei-labs-engine`'s Traefik on `10.10.20.0/24:443`,
   reached by its configured hostname — see
   [`ecosystem-architecture.md`](ecosystem-architecture.md) §2 for why the
   hostname matters here, not just the IP) is reachable and
   `qHigh`-prioritized from at least one Wi-Fi and one wired client.
4. Spot-check `Firewall → Shaper → Pipes` / `Zenarmor` dashboard shows
   near-zero baseline traffic in `Heavy_Traffic_Throttle` before doors open
   (a nonzero baseline pre-event may indicate a misclassification rule
   catching legitimate traffic).

If any check fails, do not open registration/Wi-Fi to players until the
underlying rule (cross-referenced in `security-qos-policy.md` /
`network-topology.md`) is fixed and the specific check re-passes.
