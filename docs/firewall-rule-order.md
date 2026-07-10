# Firewall Rule Import Order (Master Reference)

Security audit finding: this repo's firewall configuration is split
across five (soon more) independent XML "merge fragments" under
`config/pfsense/`, each documented and applied separately in
`security-qos-policy.md`. Rule evaluation on pfSense/OPNsense is
**first-match-wins, top-to-bottom** — the actual order rules end up in
(inside Firewall → Rules for each interface) depends on the order they
were created/imported in, and **nothing in any individual fragment's
own file enforces where it lands relative to the others**. Following
each fragment's own header instructions in isolation, in the wrong
overall sequence, can silently produce a working-looking configuration
that doesn't actually enforce what this repo claims it does — e.g. a
later-imported catch-all `pass` rule matching before an earlier-intended
`block` rule ever gets a chance to.

**This document is the single authoritative apply-order across every
fragment.** Individual sections in `security-qos-policy.md` and
`network-topology.md` describe *what* each control does and *why*; this
document is *the order to actually build them in*, once, top to bottom,
per player VLAN interface (`vlan30_player`, `vlan40_player`).

## The order

| # | Fragment / step | Source doc | Why it must be here |
|---|---|---|---|
| 1 | Player-isolation block rule (own subnet → own subnet) | `security-qos-policy.md` §5 (pending — see note below) | Must be evaluated before literally anything else; nothing later should ever get a chance to pass this traffic first. |
| 2 | IPv6 lockdown (system-level disable + interface config + explicit block) | `security-qos-policy.md` §0 (pending — see note below) | Prerequisite to the rest of this list being meaningful at all — none of rules 3+ have any IPv6 equivalent, so IPv6 must be fully dealt with independently, not interleaved. |
| 3 | DoT/DoH/DoQ block (TCP **and** UDP 853) | `security-qos-policy.md` §2 | Must precede the DNS NAT redirect and the general allow rule — this is exactly the rule a wrong import order was found to silently defeat (see "Verified failure mode" below). |
| 4 | DNS NAT redirect (port 53 → local Unbound) | `security-qos-policy.md` §1 | Must precede the general allow rule so port-53 traffic never has a chance to leave the VLAN unredirected. |
| 5 | ICMP → `qHigh` | `security-qos-policy.md` §4.1 | Ordering relative to 6-8 doesn't matter for correctness (none of them overlap in match criteria), but keep it here to match `qos-queues.xml`'s own internal ordering. |
| 6 | Scoreboard/CTF-Infra (`10.10.20.0/24`) → `qHigh` | `security-qos-policy.md` §4.1 | Same as above. |
| 7 | `Wargame_Reference_Sites` alias → `qInteractive` | `security-qos-policy.md` §4.4 | Must precede rule 9 (App-ID/Zenarmor match) — this is the rule this repo's own `qos-queues.xml` header comment already calls out as needing to sit above the App-ID rule; listed here so it's not just documented in isolation. |
| 8 | SSH / VLAN 20 challenge ports → `qInteractive` | `security-qos-policy.md` §4.1 | Ordering relative to 7 and 9 doesn't matter (distinct match criteria), grouped here to match `qos-queues.xml`. |
| 9 | App-ID/Zenarmor match → `Heavy_Traffic_Throttle` | `security-qos-policy.md` §4.3 | Must come after rule 7, or wargame reference sites risk a false-positive bulk-traffic match. |
| 10 | Default allow → `qDefault`, wrapped in `Player_Upload`/`Player_Download` limiters | `security-qos-policy.md` §3, §4.1 | Must be **last** — this is the catch-all every rule above exists to be evaluated before. |

**Pending fragments not yet on `main`:** rules 1 and 2 above
(`config/pfsense/player-peer-isolation.xml`,
`config/pfsense/disable-ipv6.xml`) ship in separate, not-yet-merged
branches from this same audit pass (`fix/vlan40-peer-isolation`,
`fix/disable-ipv6-player-vlans`). This document assumes all of this
audit's firewall-related branches land together — if only some are
merged, treat any row referencing a not-yet-present fragment as **not
yet applicable**, not as something to skip permanently.

## Verified failure mode (why this document exists)

Confirmed by direct inspection, not hypothetical: `qos-queues.xml`'s own
final rule is a catch-all `pass any → any` (rule 10 above). If
`block-dot-doh.xml` (rule 3) is imported **after** `qos-queues.xml`
instead of before it, that catch-all is already in place and evaluated
first — pfSense/OPNsense's first-match-wins semantics mean DoT/DoQ
traffic matches the catch-all `pass` rule before the DoT/DoQ `block`
rule further down the list ever gets evaluated. The resulting
configuration looks complete (every fragment successfully imported, no
errors) while silently not blocking DoT/DoQ at all. The same risk
applies to every other "must be above X" note scattered across the
individual fragment headers — this table exists so there's one place
that shows the *complete* required order at once, not just each
fragment's relationship to its immediate neighbor.

## After applying every fragment: verify the actual order, not just the intent

Following this table produces the correct order **if followed exactly
and rules are never later reordered**. Both are real risks — a rule
added months later during troubleshooting, or a GUI drag-and-drop
reorder during unrelated work, can silently violate this order without
any error or warning. Before every event, as part of
`verification-checklist.md`'s existing pass:

- [ ] Open **Firewall → Rules** for `vlan30_player` and, separately,
      `vlan40_player`. Confirm the rules appear top-to-bottom in the
      same relative order as the table above (exact rule *numbers*
      don't matter, only relative order between the numbered categories
      above).
- [ ] Specifically confirm the player-isolation block (row 1) and the
      DoT/DoQ block (row 3) both sit above the final catch-all (row
      10) — these are the two rules a wrong import order was found to
      silently defeat.
- [ ] If any rule was added or reordered since the last verification
      pass (check the firewall's own change log if available), re-walk
      this entire table rather than assuming only the new rule needs
      checking — a single misplaced rule can change what's evaluated
      before it.
