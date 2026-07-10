# Security Audit: Status (cei-labs-net)

**Related:** [`cei-labs-engine` status](../../cei-labs-engine/docs/security-audit-status.md) · [`CEI-Labs-Wargames` status](../../CEI-Labs-Wargames/docs/security-audit-status.md)

## What this is

A full cybersecurity audit of all three repos in this ecosystem
(`CEI-Labs-Wargames`, `cei-labs-engine`, `cei-labs-net`), run as three
parallel independent reviews, deliberately excluding the CTF tracks'
own intentional teaching vulnerabilities (SUID binaries, SQLi, command
injection, etc. — those are the point). This doc covers this repo's six
findings; see the related docs above for the other two repos'.

## Findings and fixes (all on separate, unmerged branches — nothing here touches `main`)

| Severity | Finding | Branch | Verification |
| :--- | :--- | :--- | :--- |
| Critical | The documented `block VLAN40net → VLAN40net` firewall rule can't see traffic between two wired stations on the same switch — ordinary Layer-2 switching never reaches pfSense/OPNsense at all. Fix requires switch-level Port Isolation (new hard requirement) to force that traffic to actually hairpin through the router first. | `fix/vlan40-peer-isolation` | Root cause confirmed by direct reasoning about switch/router L2-vs-L3 behavior; no physical switch available in this environment to test the Port Isolation config itself. |
| High | IPv6 was never addressed anywhere in this repo's policy — every rule is IPv4-only. Fix disables IPv6 in three independent layers (system-level, per-interface, explicit filter block) rather than mirroring the whole policy in IPv6. | `fix/disable-ipv6-player-vlans` | Documentation/config-only; no live pfSense instance to test against in this environment. |
| High | The DoT block only covered TCP/853 — DoQ (RFC 9250) rides UDP/853 and was completely unblocked. | `fix/block-doq-dns-bypass` | Documentation/config-only. |
| Medium-High | Firewall rules are split across 5+ independent XML fragments with no mechanical enforcement of import order — confirmed a concrete failure mode where importing fragments in the wrong sequence lets a later catch-all `pass` rule silently defeat an earlier-intended `block` rule. | `fix/master-rule-ordering-doc` | New `docs/firewall-rule-order.md` is the single source of truth; verified by direct inspection of each fragment's actual rule content and pfSense's documented first-match-wins evaluation order. |
| Medium | Wi-Fi encryption method (WPA2/WPA3 vs. open) was never specified anywhere. | `fix/specify-wifi-encryption` | Documentation-only. |
| Low | No DNS-rebinding protection — a player-controlled public domain could resolve to an internal RFC1918 address. | `fix/dns-rebinding-protection` | Documentation/config-only; explicitly verified by reasoning that Unbound's `private-address` check only applies to upstream-sourced answers, not local-zone/host-override entries, so it can't break `cei-labs-engine`'s own wildcard DNS routing. |

None of this repo's six fixes needed Docker at all — they're all
documentation and pfSense/OPNsense XML reference-fragment changes, so
none were affected by the Docker Desktop/WSL2 build-layer degradation
that blocked live verification on the other two repos (see those repos'
own status docs). The real remaining gap for all six is the same as
it's always been for this repo: nothing here is testable without actual
pfSense/OPNsense hardware, which this environment doesn't have. Every
fix includes a `verification-checklist.md` entry so it gets tested for
real the first time this is deployed to real hardware.

## Not done

`main` untouched — nothing merged. No PRs opened (left for you to
decide merge order/timing across the six branches, and whether to
merge them individually or combine some).
