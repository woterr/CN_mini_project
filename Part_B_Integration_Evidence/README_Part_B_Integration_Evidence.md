# Part B + Part C Integration Evidence

This folder contains the integration-test evidence extracted from the uploaded `testing.docx`.

## Screenshot 37 — Integration test evidence

The screenshot collage shows:

1. Mininet `pingall` output, with c4 unable to reach the other hosts.
2. A successful TCP connectivity check to the chat server at `10.0.0.10:5000`.
3. Chat client registration and login, creation of the `vip` room, and successful joining.
4. Ryu receiving `ROOM_JOIN 10.0.0.1 vip` and assigning c1 to priority queue 1.
5. Switch policy installation, including the blocked policy for `10.0.0.4` that drops IPv4 traffic.

**Evidence note:** The collage demonstrates that the blocked rule was installed on the switch. It does not, by itself, show a separate c4 chat-client connection attempt being rejected.

## Included file

- `screenshots/screenshot_37.png` — original embedded evidence image, extracted without redesigning or changing its contents.
