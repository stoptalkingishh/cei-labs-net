# Self-Hosted Wargames: Status (cei-labs-net)

**Branch:** `docs/self-hosted-wargames-status-note` @ `cf69afc` (not merged
to `main` @ `b30faa4`)
**Related:** [`cei-labs-engine` status](../../cei-labs-engine/docs/self-hosted-wargames-status.md) · [`CEI-Labs-Wargames` status](../../CEI-Labs-Wargames/docs/self-hosted-wargames-status.md)

## What this is

`CEI-Labs-Wargames` is migrating Bandit/Krypton/Natas from pointing at
OverTheWire's live infrastructure to fully self-hosted `cei-labs-engine`
instances (see that repo's status doc). This repo's own `ecosystem-
architecture.md` had flagged the *old* OTW-dependent design as finding #7
("two curriculum tracks depend on the open internet, not VLAN 20") — this
branch updates that finding to reflect the migration is in flight, and
records the network-level conclusion reached while building it.

## What changed

`docs/ecosystem-architecture.md`: added a status note under finding #7.

## The actual finding: no firewall/topology change is needed here

Read `cei-labs-engine`'s orchestrator code directly (not just documentation)
while that migration was being built, specifically to answer this repo's
own open question from finding #7:

- **`single-target`** (Bandit/Krypton — one persistent SSH box per team)
  already falls within the documented `10.10.20.0/24:30000–32767` range
  (`security-qos-policy.md`, `network-topology.md`) — same mechanism this
  repo already accounted for.
- **`target-attacker`** (Natas — one shared attacker + target per team)
  uses Traefik *exclusively* for its attacker workstation. Confirmed by
  reading `instance_types.plan_range_attacker()`: it was called with no
  port allocator at all (a real gap, since fixed on the `cei-labs-engine`
  side to give it real SSH too — see that repo's status doc) and even after
  that fix, the attacker's *additional* SSH port draws from the exact same
  `30000–32767` pool `single-target` already uses. Nothing beyond the
  already-documented `80,443` is required for either instance type.

Both `security-qos-policy.md` and `network-topology.md` were re-read in
full during this check and needed no edits — their existing port-range
language already covers this correctly.

## Known open items

- Finding #7's "outbound reachability to OverTheWire" pre-event
  connectivity check should stay in `verification-checklist.md` until the
  self-hosted migration actually lands on `main` in the other two repos —
  removing it now would be premature (the OTW-dependent version is still
  what's on `main` today).
- No changes needed to `config/pfsense/qos-queues.xml` or any other
  firewall/QoS config file — the conclusion above is documentation-only.

## Not done at all

No PRs opened, nothing merged to `main`.
