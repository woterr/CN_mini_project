
# Multi-Client Chat Network — Protocol Specification

## Transport
- TCP sockets
- Chat server port: 5000
- One command per line, ending with newline (\n)
- Fields separated by spaces
- Usernames and room names cannot contain spaces
- The final message-text field may contain spaces

## Client-to-Server Commands

| Command | Format | Purpose |
|---|---|---|
| REGISTER | REGISTER <user> <pass> | Register an account |
| LOGIN | LOGIN <user> <pass> | Log in |
| CREATE | CREATE <room> | Create a room |
| JOIN | JOIN <room> | Join a room |
| LEAVE | LEAVE <room> | Leave a room |
| MSG | MSG <room> <text> | Send a room message |
| PM | PM <user> <text> | Send a private message |
| USERS | USERS | List online users |
| ROOMS | ROOMS | List rooms |
| QUIT | QUIT | Disconnect |

## Server-to-Client Responses
- OK <info>: successful command
- ERR <reason>: failed command
- ROOMMSG <room> <sender> <text>: room message
- PMSG <sender> <text>: private message
- INFO <text>: informational notice
- USERS <u1,u2,...>: online-user listing
- ROOMS <r1,r2,...>: room listing

## Error Reasons
BAD_COMMAND
NOT_LOGGED_IN
USER_EXISTS
BAD_CREDENTIALS
ALREADY_LOGGED_IN
ROOM_EXISTS
NO_SUCH_ROOM
NO_SUCH_USER
NOT_IN_ROOM

## Server-to-Controller Notifications
Separate TCP connection, proposed port 6000:

ROOM_JOIN <user_ip> <room>
ROOM_LEAVE <user_ip> <room>


## Rules

1. REGISTER creates an account but does not automatically log in the user.
2. Before login, only REGISTER and LOGIN are accepted.
3. A username can have only one active client connection.
4. CREATE fails if the room already exists.
5. JOIN fails if the room does not exist.
6. LEAVE fails if the room does not exist or the user is not a member.
7. MSG requires the sender to have joined the specified room.
8. Room messages are delivered to other online members, not echoed as ROOMMSG to the sender.
9. PM delivers a private message to an online user.
10. Unknown commands return ERR BAD_COMMAND.
11. Disconnected users are removed from the online-user list and all rooms.
12. Successful room joins and leaves trigger controller notification attempts.
13. Controller notifications use a separate TCP connection to port 6000.
14. Notification delivery is not guaranteed when the controller is unavailable.
15. User accounts and rooms are stored in memory and are lost when the server restarts.
