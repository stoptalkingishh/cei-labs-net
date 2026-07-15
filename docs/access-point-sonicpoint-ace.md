# SonicWall SonicPoint ACe OpenWrt access-point plan

## Decision and scope

The selected event access-point platform is the **SonicWall SonicPoint ACe,
model APL26-0AE**, running a stable OpenWrt release. The OpenWrt hardware
record is the source of truth for device support and firmware links:

- <https://openwrt.org/toh/hwdata/sonicwall/sonicwall_sonicpoint-ace>

The hardware page is not itself a firmware image. At preparation time, follow
its stable-release link, record the exact image filename, release, SHA-256
checksum, and installation operator in the event inventory. Do not deploy an
unversioned snapshot to event APs.

OpenWrt lists this device as an `ath79/generic` target with a 720 MHz
QCA9550 CPU, 256 MB RAM, 32 MB flash, two Gigabit Ethernet ports, 802.1Q VLAN
support, LAN1 PoE input, and dual 3x3 radios: 2.4 GHz 802.11b/g/n (`ath9k`)
and 5 GHz 802.11a/n/ac (`ath10k-ct`). It requires 802.3at PoE when powered
from the switch.

## Effect on the event plan

The ACe is Wi-Fi 5, not the generic Wi-Fi 6 minimum previously listed in the
README. It can implement the required SSID/VLAN/security design, but it must
not be assumed to support 80 active participants until the room layout,
channel plan, and concurrent-client test pass. The expected inventory is two
units, normally connected to switch ports 2 and 3; ports 4 and 5 remain spare
for an added or replacement AP.

With all 80 participants on Wi-Fi, two units imply approximately 40
participants per AP before counting phones, VMs, or other secondary devices.
That is a planning ratio, not an accepted capacity figure. Prefer one
participant laptop per Wi-Fi admission, provide wired overflow seats, and do
not advertise wireless capacity until a representative rehearsal passes.
Two units also provide no proven full-capacity failover: losing one AP may
require moving participants to wired seats or pausing admission.

Treat these as release gates:

1. Flash and recover one spare/pilot AP before touching the event inventory.
2. Pin one stable OpenWrt release and checksum for every AP.
3. Complete a site survey and non-overlapping channel plan.
4. Prove VLAN tagging, management isolation, same-AP and cross-AP client
   isolation, roaming, and failure recovery.
5. Run the expected concurrent-client and traffic workload. Add APs, reduce
   radio cell size, or provide more wired seats if utilization, retries,
   latency, or disconnects exceed the acceptance thresholds.
6. Exercise loss of one AP and document the reduced-capacity operating plan;
   do not assume the remaining unit can serve the full event.

## Required logical configuration

Each AP is a bridge-only device. pfSense/OPNsense remains the only router,
DHCP server, DNS resolver, and firewall. Disable DHCP, DNS forwarding, NAT,
UPnP, and WAN routing on every AP.

| Function | VLAN | OpenWrt requirement |
| :--- | :---: | :--- |
| AP management | 10 | Static/reserved address; SSH/LuCI reachable only from authorized management/staff sources |
| Player SSID | 30 | Tagged bridge, WPA2-Personal/AES, event-specific key, client isolation enabled |
| Staff SSID | 50 | Tagged bridge, separate WPA2-Personal/AES key, client isolation enabled |

Do not trunk VLAN 20 or VLAN 40 to an AP. Do not expose an untagged player
network or an OpenWrt management SSID. WPA3 may be enabled only after the
installed OpenWrt/wpad build and expected clients pass compatibility tests;
WPA2-Personal with AES/CCMP is the conservative baseline for this older
platform.

Do not copy interface names from another device blindly. After the pilot AP
boots, retain the output of `ubus call system board`, `ip -br link`,
`bridge vlan show`, `uci show network`, and `uci show wireless`. Use that
evidence to create the final device-specific UCI backup and a redacted
golden configuration.

## Layer-2 isolation across multiple APs

OpenWrt wireless client isolation prevents direct peer traffic on a single
BSS. It does not, by itself, prove that a player on AP-1 cannot reach a player
on AP-2 through the core switch.

Configure switch ports 2-5 as protected/isolated trunk ports that may forward
to the router uplink on port 1 but not to one another. Verify that the chosen
switch applies port isolation to tagged traffic on VLAN 30. If it cannot,
use a distinct player VLAN/subnet per AP and block those VLANs from one
another at pfSense/OPNsense. A same-subnet firewall rule alone cannot stop
ordinary Layer-2 traffic.

## Radio plan

- Set the correct regulatory country; never leave the radio at an undefined
  world domain or select a country that does not match the venue.
- Prefer 5 GHz for participant laptops. Use fixed, surveyed channels rather
  than allowing every AP to auto-select during the event.
- With two APs, assign distinct surveyed 5 GHz channels and distinct 2.4 GHz
  channels. Do not place both units on the same channel unless the survey
  demonstrates that this is unavoidable and the capacity test still passes.
- Start with 20 or 40 MHz 5 GHz channels in a dense room; use 80 MHz only if
  the survey proves sufficient clean spectrum.
- On 2.4 GHz, use 20 MHz and only non-overlapping channels 1, 6, and 11 in
  the United States. Disable legacy rates only after compatibility testing.
- Keep transmit power no higher than needed. More power can increase
  co-channel interference and produce clients that hear the AP but cannot
  transmit back reliably.
- Record BSSID, radio MAC, channel, width, power, switch port, PoE source,
  management IP, physical location, and firmware checksum for every AP.

## Capacity and acceptance evidence

At minimum, retain the following during the AP rehearsal and event smoke
test:

- associated stations per radio and AP;
- channel utilization, noise, signal, retry/failure counters, and negotiated
  rates (`iw dev`, `iwinfo`, and OpenWrt status output);
- DHCP success and roaming/reassociation time;
- latency and packet loss to the VLAN 30 gateway and CTFd under load;
- aggregate and per-client throughput while the configured limiters are
  active;
- CPU, memory, thermal, interface-error, and PoE stability observations;
- same-AP and cross-AP peer-isolation results;
- one AP power-loss/reboot recovery result.
- results at the expected two-AP client load and the documented degraded
  behavior with one AP unavailable.

The wireless layer is accepted only when the full expected client count can
join, retain leases, reach CTFd/challenges, remain isolated, and sustain the
event workload without repeated disconnects or unacceptable latency.
