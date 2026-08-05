# Fedora Swarm Test Plan

This is the live-router plan for putting the local Fedora server candidates
into a Docker Swarm for CEI Labs testing. It follows the current operator
requirement: use the live OPNsense topology first, not the older generic
VLAN-20 reference design.

## Source of truth

- Network baseline:
  [`docs/opnsense-end-state.md`](opnsense-end-state.md).
- Engine implementation:
  [`cei-labs-engine`](https://github.com/stoptalkingishh/cei-labs-engine),
  especially `ansible/site.yml`, `ansible/inventory.ini`,
  `ansible/roles/common`, `ansible/roles/swarm`, and `docker/stack.yml`.
- Challenge content:
  [`CEI-Labs-Wargames`](https://github.com/stoptalkingishh/CEI-Labs-Wargames).

## Current live status

The current OPNsense deployment exposes the server/operator network on
`em0` / `192.168.10.0/24`. Player Wi-Fi is separate on `ue1` /
`10.10.32.0/22` and must not host Swarm nodes.

Live discovery from OPNsense and the operator laptop currently shows:

| Host | Evidence | Current status |
| :--- | :--- | :--- |
| `192.168.10.120` | DHCP lease `DESKTOP-Q8892V6`; local laptop | Already a one-node Docker Desktop Swarm manager on Docker Desktop's internal `192.168.65.3` address. Useful for local-only tests, not the Fedora-server Swarm target. |
| `192.168.10.192` | OPNsense ARP: Dell MAC `d4:ae:52:cc:7a:f1`; laptop TCP check | SSH port 22 is open. Ports 80, 443, 2377, 7946, and 4789 are not open yet. Treat as the first Fedora/server candidate to verify. |
| `192.168.10.235` | dnsmasq lease hostname `host`, MAC `00:d8:61:e5:4e:0f` | No tested service responded on ports 22, 80, 443, 2377, 7946, or 4789. Treat as an unverified lease, not an accepted Swarm node. |
| `10.10.32.2`, `10.10.32.3` | OPNsense ARP on Player Wi-Fi | NETGEAR AP/client-bridge devices. Do not join these to Swarm. |

## Target end state

1. OPNsense remains the policy mediator:
   - LAN / server / operator network: `192.168.10.0/24`, gateway
     `192.168.10.1`.
   - Player Wi-Fi: `10.10.32.0/22`, gateway `10.10.32.1`.
   - Swarm nodes live only on `192.168.10.0/24`.
2. The first stable Fedora server becomes the primary Swarm manager.
   - Current candidate: `192.168.10.192`, pending SSH login and OS
     verification.
   - Reserve its IP in OPNsense DHCP or assign it statically before deploying
     `cei-labs-engine`.
3. Additional Fedora servers join as workers after identity, OS, storage, and
   firewall verification.
4. The local Windows laptop can remain a development/test station, but it must
   not be treated as production Swarm capacity unless explicitly accepted.
5. `cei-labs-engine` deploys unchanged through Docker Swarm:
   - use `ansible/site.yml` to install Docker and form/grow the Swarm;
   - use `docker/stack.yml` for Traefik, CTFd, Redis, MariaDB, orchestrator,
     gateways, and challenge/workspace services;
   - use `CEI-Labs-Wargames` only after the CTFd endpoint is live and API
     credentials are available.

## Required repo alignment

The older docs still say "VLAN 20 host(s)" in several places. For this live
deployment, replace that operational assumption with:

> CEI Labs Engine runs on Fedora Docker Swarm nodes reachable on the live
> `192.168.10.0/24` LAN/server network unless the operator explicitly
> reintroduces a dedicated server VLAN.

Keep the generic VLAN-20 reference as a reference architecture only.

## Fedora host acceptance checklist

Run this before adding any host to inventory:

```sh
hostname
cat /etc/os-release
ip addr
ip route
systemctl is-active sshd
systemctl is-active firewalld
docker --version || true
docker info || true
free -h
df -h
```

Minimum acceptance:

- Fedora or another `RedHat`-family OS supported by
  `cei-labs-engine/ansible/roles/common`.
- Static or DHCP-reserved address on `192.168.10.0/24`.
- Default gateway `192.168.10.1`.
- SSH access from the deployment machine.
- Docker Engine can be installed and managed by Ansible.
- Enough CPU/RAM/disk for the expected test load.
- No conflicting Docker Swarm membership before the run, unless intentionally
  reusing an existing Swarm.

## Firewall and OPNsense requirements

The `cei-labs-engine` Ansible common role already opens the Fedora host
firewall for:

| Port(s) | Protocol | Scope | Purpose |
| :--- | :--- | :--- | :--- |
| 22 | TCP | deployment/admin hosts | SSH |
| 2377 | TCP | Swarm nodes only | Swarm management |
| 7946 | TCP/UDP | Swarm nodes only | Swarm gossip |
| 4789 | UDP | Swarm nodes only | VXLAN overlay datapath |
| 80, 443 | TCP | player/staff access via OPNsense policy | Traefik / CTFd / HTTP challenges |
| 30001-31999 | TCP | player/staff access via OPNsense policy | Bulk analyst and Kali workspace ports |
| 32000-32767 | TCP | player/staff access via OPNsense policy | Participant gateway ports |

OPNsense must allow the same traffic where it crosses routed boundaries. In
the current live topology, Swarm node-to-node traffic should stay inside
`192.168.10.0/24` and not traverse OPNsense, but player access from
`10.10.32.0/22` to the engine endpoints does traverse OPNsense and must be
allowed only to the intended CEI Labs ports.

## Ansible inventory target

Do not commit real private-key paths or secrets. Start from an inventory like
this after the host identities are verified:

```ini
[swarm_managers]
node1 ansible_host=192.168.10.192 ansible_user=<fedora-admin-user>

[swarm_workers]
# node2 ansible_host=<next-verified-fedora-ip> ansible_user=<fedora-admin-user>

[swarm_cluster:children]
swarm_managers
swarm_workers

[all:vars]
ansible_python_interpreter=/usr/bin/python3
common_firewalld_zone=public
```

Then run from the `cei-labs-engine` checkout:

```sh
ansible-galaxy collection install -r ansible/requirements.yml
ansible-playbook -i ansible/inventory.ini ansible/site.yml
```

After the Swarm is formed, run the engine stack from the primary manager:

```sh
./scripts/stack-up.sh
docker node ls
docker stack services cei-labs
```

## Validation plan

Do not mark the Swarm usable until these pass:

1. From the primary manager:

   ```sh
   docker info --format '{{json .Swarm}}'
   docker node ls
   docker network ls
   docker stack services cei-labs
   ```

2. From the operator laptop on `192.168.10.0/24`:

   ```sh
   curl -kI https://ctfd.<base-domain>/
   ```

3. From a Player Wi-Fi client on `10.10.32.0/22`:

   ```sh
   curl -kI https://ctfd.<base-domain>/
   ```

4. Launch one representative web challenge, one SSH/single-target challenge,
   and one noVNC/attacker workflow from CTFd.
5. Confirm direct player lateral movement stays blocked:
   - no access to OPNsense admin surfaces;
   - no access to Docker management ports;
   - no peer-to-peer Player Wi-Fi visibility beyond what the AP lane
     explicitly accepts.
6. Push wargame content only after the CTFd URL and API token are confirmed:

   ```sh
   CTFD_URL=https://ctfd.<base-domain> \
   CTFD_TOKEN=<redacted> \
   ./deploy.sh
   ```

## Current blockers

- Confirm SSH credentials and OS identity for `192.168.10.192`.
- Decide whether `192.168.10.235` is a Fedora server, an offline/stale lease,
  or something else.
- Reserve stable addresses for accepted Fedora servers in OPNsense.
- Decide the base domain/DNS override for CTFd and wildcard app routing on the
  live network.
- Keep WAN `ue0` link-state cleanup separate from the internal Swarm task.
