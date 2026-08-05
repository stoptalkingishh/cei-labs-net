# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
This repo predates this file (27 commits as of 2026-07-15) — entries below
are a milestone summary, not a commit-by-commit history. See `git log` for
the full record.

## [Unreleased]

- Add an OPNsense end-state runbook for the live CEI-Labs box based on
  authenticated router discovery: `em0` LAN/CTF infra, `ue0` WAN, and `ue1`
  dedicated Player-WiFi with the `10.10.32.0/22` DHCP scope.
- Record devices visible from the OPNsense box, including the operator
  laptop, a Dell LAN device, and two NETGEAR devices on Player-WiFi.
- Document that the prior five-VLAN design is stale for this deployment and
  that leftover VLAN interfaces `vlan01`-`vlan05` still need cleanup if the
  simplified two-network topology remains final.

## Milestones before this file existed

- Router-on-a-stick network design: single pfSense/OPNsense box, five
  VLANs (Management/CTF-Infrastructure/Player-Wi-Fi/Player-Wired/Staff)
  trunked through a managed switch.
- Security audit: six findings fixed, all documentation/config-only
  (no live pfSense hardware available in this environment to test
  against — every fix carries a `verification-checklist.md` entry for
  first real-hardware deployment):
  - **Critical**: same-switch wired-station traffic never reaches the
    firewall at all (ordinary Layer-2 switching) — requires switch-level
    Port Isolation to force a routed hairpin.
  - **High**: IPv6 was completely unaddressed by the policy — disabled in
    three independent layers instead.
  - **High**: DNS-over-QUIC (UDP/853) bypassed the existing DoT block.
  - **Medium-High**: firewall rule fragments had no enforced import
    order, allowing a later catch-all `pass` to silently defeat an
    earlier `block`.
  - **Medium**: Wi-Fi encryption method was never specified anywhere —
    now requires WPA2/WPA3-Personal on every SSID, no open networks.
  - **Low**: no DNS-rebinding protection.

**This repo's design is essentially untested against real hardware** —
that remains the single largest gap in the whole CEI Labs production-
readiness tracker (`cei-labs-event/TRACKER.md` §4/§5). See
`docs/security-audit-status.md` and `docs/verification-checklist.md`.
