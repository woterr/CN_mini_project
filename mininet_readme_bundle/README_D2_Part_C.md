# D2 Part C — Baseline and Mininet Testing Evidence

This folder contains the screenshots supplied for the D2 Part C baseline/topology test run.
The screenshots are numbered `screenshot_14.png` onward so they can sit alongside the
existing `screenshot_01.png`–`screenshot_13.png` without overwriting them.

## Testing performed and evidence

| Test / check | Result shown in the supplied screenshots |
|---|---|
| Baseline controller startup | Ryu loads `controller/baseline_controller.py`; Switch 1 and Switch 2 connect. |
| Host connectivity (`pingall`) | PASS — 20/20 packets received; 0% dropped. The same successful result appears twice in the supplied document. |
| OpenFlow table on `s1` | Flow entries are displayed. This is baseline learning-switch forwarding evidence, not proof of Part B policy behaviour. |
| OpenFlow table on `s2` | Flow entries are displayed. This is baseline learning-switch forwarding evidence, not proof of Part B policy behaviour. |
| Mininet topology (`net`) | Shows clients `c1`–`c4` connected to `s1`, server connected to `s2`, and the inter-switch link. |
| Link status (`links`) | PASS — all listed host and switch links show `OK OK`. |
| Bottleneck-link class (`tc class show`) | Shows an HTB class with a 5 Mbit rate and 5 Mbit ceiling. |
| `c1` to server ping | PASS — 3 packets transmitted, 3 received, 0% packet loss. |
| `c4` to server ping | PASS in this run — 3 packets transmitted, 3 received, 0% packet loss. This does **not** demonstrate that `c4` is blocked. |

## Notes and limitations

- The supplied screenshots demonstrate baseline controller startup, topology structure,
  link status, basic reachability, and a 5 Mbit HTB class.
- The flow-table screenshots are from the baseline learning-switch run. They do not verify
  priority/normal queue classification, blocked-user enforcement, or dynamic room JOIN/LEAVE
  flow changes; those checks require Part B integration.
- A `tc qdisc` screenshot showing the configured 10 ms delay is not included in this
  particular Word document's embedded screenshots. The topology configuration may specify
  that delay, but this evidence set does not independently show the qdisc output.
- The `c4` ping succeeds, so do not describe this run as a blocked-client test.
- The earlier interrupted `iperf` attempt did not produce a valid throughput result; no
  throughput number is reported here.

## Screenshot index

- `screenshots/screenshot_14.png`
- `screenshots/screenshot_15.png`
- `screenshots/screenshot_16.png`
- `screenshots/screenshot_17.png`
- `screenshots/screenshot_18.png`
- `screenshots/screenshot_19.png`
- `screenshots/screenshot_20.png`
- `screenshots/screenshot_21.png`
- `screenshots/screenshot_22.png`
- `screenshots/screenshot_23.png`
