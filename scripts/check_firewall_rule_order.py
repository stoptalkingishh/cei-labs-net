#!/usr/bin/env python3
"""Mechanically enforce the firewall rule-ordering invariant described in
docs/firewall-rule-order.md.

Firewall policy for this repo is split across several independent
pfSense/OPNsense XML "merge fragments" under config/pfsense/. Rule
evaluation on pfSense/OPNsense is first-match-wins, top-to-bottom, but
nothing in any individual fragment enforces where its rules land relative
to the others once imported. docs/firewall-rule-order.md is the
authoritative apply order and explicitly calls out (see "Verified failure
mode" and the pre-event checklist) the two rules whose relative position
has actually been found to matter and silently break if reversed:

  1. The player-peer-isolation block rule (own subnet -> own subnet)
     must sit above the final catch-all pass rule on its interface.
  2. The DoT/DoQ block rules (destination port 853) must sit above the
     final catch-all pass rule on their interface.

This script rebuilds the effective per-interface rule order by
concatenating the relevant XML fragments in the canonical apply order
documented in docs/firewall-rule-order.md, then asserts that both
invariants above hold. It intentionally does NOT try to re-derive or
enforce the full 10-step order table -- only the two relationships the
doc identifies as the ones a wrong import order was confirmed to defeat.
"""

from __future__ import annotations

import glob
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PFSENSE_DIR = REPO_ROOT / "config" / "pfsense"

# Canonical apply order across fragments, per docs/firewall-rule-order.md's
# "The order" table (rows 1-10). Only fragments that contribute <filter>
# <rule> elements relevant to the two invariants below need to be listed,
# but the full documented fragment order is kept here so the effective
# per-interface rule sequence this script reconstructs matches the doc,
# not just the two rules being checked.
CANONICAL_FRAGMENT_ORDER = [
    "player-peer-isolation.xml",  # row 1: player-isolation block
    "disable-ipv6.xml",  # row 2: IPv6 lockdown
    "block-dot-doh.xml",  # row 3: DoT/DoQ block
    "dns-redirect-nat.xml",  # row 4: DNS NAT redirect
    "wargame-reference-allowlist.xml",  # row 7 (allowlist pass, ahead of App-ID match)
    "qos-queues.xml",  # rows 5,6,8,9,10 (incl. the final catch-all pass)
]

INTERFACES = ["vlan30_player", "vlan40_player"]


def rule_text(rule: ET.Element, tag: str) -> str | None:
    el = rule.find(tag)
    if el is None:
        return None
    return (el.text or "").strip()


def network_of(rule: ET.Element, side: str) -> str | None:
    """Return the <network> value under <source>/<destination>, if any."""
    side_el = rule.find(side)
    if side_el is None:
        return None
    net = side_el.find("network")
    if net is None:
        return None
    return (net.text or "").strip()


def is_player_isolation_block(rule: ET.Element) -> bool:
    """type=block with source network == destination network (own subnet ->
    own subnet), matching docs/firewall-rule-order.md row 1's description."""
    if rule_text(rule, "type") != "block":
        return False
    src_net = network_of(rule, "source")
    dst_net = network_of(rule, "destination")
    return src_net is not None and dst_net is not None and src_net == dst_net


def is_dot_doq_block(rule: ET.Element) -> bool:
    """type=block targeting destination port 853 (DoT/DoQ), matching
    docs/firewall-rule-order.md row 3."""
    if rule_text(rule, "type") != "block":
        return False
    dest = rule.find("destination")
    if dest is None:
        return False
    port = dest.find("port")
    return port is not None and (port.text or "").strip() == "853"


def is_catch_all_pass(rule: ET.Element) -> bool:
    """The final catch-all pass rule docs/firewall-rule-order.md row 10
    describes: "pass any -> any ... wrapped in Player_Upload/
    Player_Download limiters". Identified structurally by the dnpipe/
    pdnpipe limiter attachment, which only appears on this rule."""
    if rule_text(rule, "type") != "pass":
        return False
    return rule.find("dnpipe") is not None and rule.find("pdnpipe") is not None


def load_fragment_rules(filename: str) -> list[ET.Element]:
    path = PFSENSE_DIR / filename
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    filter_el = root.find("filter")
    if filter_el is None:
        return []
    return list(filter_el.findall("rule"))


def build_effective_order() -> list[tuple[str, ET.Element]]:
    """Concatenate <filter><rule> elements from every known fragment, in
    the canonical documented apply order, preserving each fragment's own
    internal order. Returns (source_filename, rule) tuples."""
    effective: list[tuple[str, ET.Element]] = []
    for filename in CANONICAL_FRAGMENT_ORDER:
        for rule in load_fragment_rules(filename):
            effective.append((filename, rule))
    return effective


def check_interface(interface: str, effective_order: list[tuple[str, ET.Element]]) -> list[str]:
    errors: list[str] = []

    iface_rules = [
        (idx, filename, rule)
        for idx, (filename, rule) in enumerate(effective_order)
        if rule_text(rule, "interface") == interface
    ]

    isolation_positions = [
        idx for idx, filename, rule in iface_rules if is_player_isolation_block(rule)
    ]
    dot_positions = [idx for idx, filename, rule in iface_rules if is_dot_doq_block(rule)]
    catch_all_positions = [
        (idx, filename) for idx, filename, rule in iface_rules if is_catch_all_pass(rule)
    ]

    if not isolation_positions:
        errors.append(
            f"[{interface}] no player-peer-isolation block rule found "
            f"(expected in player-peer-isolation.xml) -- cannot verify "
            f"docs/firewall-rule-order.md row 1's ordering requirement."
        )
    if not dot_positions:
        errors.append(
            f"[{interface}] no DoT/DoQ block rule (destination port 853) "
            f"found (expected in block-dot-doh.xml) -- cannot verify "
            f"docs/firewall-rule-order.md row 3's ordering requirement."
        )
    if not catch_all_positions:
        errors.append(
            f"[{interface}] no catch-all pass rule found (expected in "
            f"qos-queues.xml, the 'Default player egress' rule wrapped in "
            f"Player_Upload/Player_Download) -- cannot verify anything is "
            f"required to precede it."
        )

    if not (isolation_positions and dot_positions and catch_all_positions):
        return errors

    catch_all_idx, catch_all_file = min(catch_all_positions, key=lambda pair: pair[0])

    for idx in isolation_positions:
        if idx > catch_all_idx:
            errors.append(
                f"[{interface}] player-peer-isolation block rule (from "
                f"player-peer-isolation.xml) is ordered AFTER the catch-all "
                f"pass rule (from {catch_all_file}). Per "
                f"docs/firewall-rule-order.md, this rule must be evaluated "
                f"before the catch-all or same-VLAN peer traffic silently "
                f"passes instead of being blocked."
            )

    for idx in dot_positions:
        if idx > catch_all_idx:
            errors.append(
                f"[{interface}] DoT/DoQ block rule (from block-dot-doh.xml) "
                f"is ordered AFTER the catch-all pass rule (from "
                f"{catch_all_file}). Per docs/firewall-rule-order.md's "
                f"'Verified failure mode', this is exactly the ordering bug "
                f"that silently defeats the DoT/DoQ block -- the catch-all "
                f"matches first and the block rule below it never gets "
                f"evaluated."
            )

    return errors


def main() -> int:
    xml_files = sorted(glob.glob(str(PFSENSE_DIR / "*.xml")))
    if not xml_files:
        print(f"error: no XML fragments found under {PFSENSE_DIR}", file=sys.stderr)
        return 1

    effective_order = build_effective_order()

    all_errors: list[str] = []
    for interface in INTERFACES:
        all_errors.extend(check_interface(interface, effective_order))

    if all_errors:
        print(
            "Firewall rule ordering check FAILED "
            "(see docs/firewall-rule-order.md):\n",
            file=sys.stderr,
        )
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "Firewall rule ordering OK: player-peer-isolation and DoT/DoQ "
        "block rules precede the catch-all pass rule on "
        f"{', '.join(INTERFACES)}, matching docs/firewall-rule-order.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
