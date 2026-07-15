# Security Audit: Status (cei-labs-net)

**Related:** [`cei-labs-engine` status](../../cei-labs-engine/docs/security-audit-status.md) · [`CEI-Labs-Wargames` status](../../CEI-Labs-Wargames/docs/security-audit-status.md)

## What this is

A full cybersecurity audit of all three repos in this ecosystem
(`CEI-Labs-Wargames`, `cei-labs-engine`, `cei-labs-net`), run as three
parallel independent reviews, deliberately excluding the CTF tracks'
own intentional teaching vulnerabilities (SUID binaries, SQLi, command
injection, etc. — those are the point). This doc covers this repo's six
findings; see the related docs above for the other two repos'.

## Findings and fixes (all merged to `main`)

| Severity | Finding | Branch | Verification |
| :--- | :--- | :--- | :--- |
| Critical | The documented `block VLAN40net → VLAN40net` firewall rule can't see traffic between two wired stations on the same switch — ordinary Layer-2 switching never reaches pfSense/OPNsense at all. Fix requires switch-level Port Isolation (new hard requirement) to force that traffic to actually hairpin through the router first. | `fix/vlan40-peer-isolation` (merged) | Root cause confirmed by direct reasoning about switch/router L2-vs-L3 behavior; **still needs real-hardware verification** — no physical switch available in this environment to test the Port Isolation config itself. |
| High | IPv6 was never addressed anywhere in this repo's policy — every rule is IPv4-only. Fix disables IPv6 in three independent layers (system-level, per-interface, explicit filter block) rather than mirroring the whole policy in IPv6. | `fix/disable-ipv6-player-vlans` (merged) | Documentation/config-only; **still needs a live pfSense instance to test against** — none available in this environment. |
| High | The DoT block only covered TCP/853 — DoQ (RFC 9250) rides UDP/853 and was completely unblocked. | `fix/block-doq-dns-bypass` (merged) | Documentation/config-only; **still needs a live pfSense instance to test against**. |
| Medium-High | Firewall rules are split across 5+ independent XML fragments with no mechanical enforcement of import order — confirmed a concrete failure mode where importing fragments in the wrong sequence lets a later catch-all `pass` rule silently defeat an earlier-intended `block` rule. | `fix/master-rule-ordering-doc` (merged) | New `docs/firewall-rule-order.md` is the single source of truth; verified by direct inspection of each fragment's actual rule content and pfSense's documented first-match-wins evaluation order. Doc-only, nothing further to verify. |
| Medium | Wi-Fi encryption method (WPA2/WPA3 vs. open) was never specified anywhere. | `fix/specify-wifi-encryption` (merged) | Documentation-only; **still needs a real AP to confirm the SSID configuration**. |
| Low | No DNS-rebinding protection — a player-controlled public domain could resolve to an internal RFC1918 address. | `fix/dns-rebinding-protection` (merged) | Documentation/config-only; explicitly verified by reasoning that Unbound's `private-address` check only applies to upstream-sourced answers, not local-zone/host-override entries, so it can't break `cei-labs-engine`'s own wildcard DNS routing. **Still needs a live Unbound instance to confirm.** |

None of this repo's six fixes needed Docker at all — they're all
documentation and pfSense/OPNsense XML reference-fragment changes, so
none were affected by the Docker Desktop/WSL2 build-layer degradation
that blocked live verification on the other two repos (see those repos'
own status docs). All six are merged to `main`, in severity order,
resolving a handful of textual conflicts along the way where two
branches independently touched the same README table row or
network-topology bullet list — in every case the two changes were
complementary (e.g. Port Isolation + RA-Guard on the same switch-port
row), not contradictory, so both were kept.

## What's still open

The real remaining gap for four of the six (VLAN40 isolation, IPv6,
DoQ, Wi-Fi encryption, DNS rebinding) is the same as it's always been
for this repo: nothing here is testable without actual pfSense/OPNsense
hardware and a real AP, which this environment doesn't have. Every fix
includes a `verification-checklist.md` entry so it gets tested for real
the first time this is deployed to real hardware. `fix/master-rule-
ordering-doc` is the only one of the six that's doc-only with nothing
further to verify.

## Selected AP update — 2026-07-15

The event hardware is now identified as SonicWall SonicPoint ACe
(APL26-0AE) units running OpenWrt. The selection and its live acceptance
gates are documented in
[`access-point-sonicpoint-ace.md`](access-point-sonicpoint-ace.md). Hardware
identification closes the vendor/model planning gap, and the expected
inventory is now two units. It does not close the Wi-Fi verification gap:
firmware pinning, physical inventory confirmation, RF survey, same-AP and
cross-AP isolation, full concurrent-client capacity, and degraded operation
with one AP unavailable remain open until exercised on the physical units.

## Not done

All six findings are merged to `main`. No PRs were opened (merged
directly, since these were single-purpose audit-fix branches created in
the same environment doing the merging).
