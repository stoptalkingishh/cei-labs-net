# OPNsense: Zenarmor Free → Traffic Shaper Integration Notes

OPNsense doesn't need a manual "App-ID alias" bridge the way pfSense/Snort
does — Zenarmor plugs directly into the native OPNsense Shaper. Steps:

## 1. Install Zenarmor Free

`System → Firmware → Plugins → os-sensei` → install → follow the setup
wizard and select the **Free** tier (no license cost, sufficient
category/app signatures for this use case).

## 2. Enable the categories we care about

`Zenarmor → Policies → Application Control` (or `Cloud Application
Control`, depending on version) — enable detection for:

- Peer-to-Peer / File Sharing → **BitTorrent**
- Gaming Platforms → **Steam** (downloads/updates)
- Streaming Media → **Netflix**, **YouTube**
- Software / OS Updates → **Windows Update** and equivalent
  macOS/Linux package-manager signatures if present in your Zenarmor build

## 3. Create the throttle policy

`Zenarmor → Policies → New Policy`:

| Field | Value |
| :--- | :--- |
| Name | `Heavy_Traffic_Throttle_Policy` |
| Source | VLAN30 (Player Wi-Fi), VLAN40 (Player Wired) |
| Match | The categories/apps enabled in step 2 |
| Action | Allow + **Shape** |
| Shaper pipe | `Heavy_Traffic_Throttle` (create under `Firewall → Shaper → Pipes` first — 256 Kbit/s, mask on source address, matching `config/pfsense/limiters.xml`'s pfSense equivalent) |

Zenarmor evaluates policies top-down like firewall rules — keep this policy
**below** the DNS/ICMP/Scoreboard high-priority allow rules but **above**
the generic player-egress allow rule, so matched flows get shaped instead
of falling through to the default `Player_Upload`/`Player_Download`
limiters.

## 4. Verify

`Zenarmor → Reports → Application Usage` will show live matches; confirm
BitTorrent/Steam/Netflix/YouTube/Update flows are landing in the throttle
pipe by generating test traffic from a player-VLAN test client and watching
`Firewall → Shaper → Pipes → Heavy_Traffic_Throttle` traffic counters climb
while `Player_Download` stays idle for that flow.
