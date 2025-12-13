============================================================
 README — OpenGate Cloud System (Version 2.3, English)
============================================================

OVERVIEW
--------
A lightweight cloud-based gate-opening system designed for very low traffic
(only a few operations per day), with maximum reliability and minimal complexity.

Main components:
• Python Flask server hosted on Railway
• Android phone running MacroDroid
• Optional Pushbullet notifications (monitoring / alerts only)
• All logic, permissions, and scheduling handled by the server
• No database, no sessions, no background workers

The phone acts as a CONTROLLED EXECUTOR:
• It never decides what to do
• It polls the server and executes tasks
• It reports results back to the server


============================================================
 CORE DESIGN PRINCIPLES
============================================================

• Server is stateless beyond in-memory variables
• Single device, single task at a time
• Polling instead of inbound connections (no IP/VPN issues)
• Everything works over HTTPS (TLS)
• Secrets are stored only as Railway environment variables
• Designed for 5–10 gate openings per week


============================================================
 FILE STRUCTURE
============================================================

/app.py        — main Flask server
/README.txt    — documentation
/Dockerfile    — Railway deployment

No user or gate data files are stored in Git.


============================================================
 CONFIGURATION (ENV VARIABLES)
============================================================

All sensitive data is stored in Railway Environment Variables:

USERS_JSON
----------
JSON array defining users and permissions:

Example:
[
  {"name":"Yair","token":"482913","allowed_gates":"ALL"},
  {"name":"Miki","token":"173025","allowed_gates":["Main","Enter","Exit","Gay"]},
  {"name":"Raz","token":"650391","allowed_gates":["Main","Enter","Exit","Gay"]},
  {"name":"Nofar","token":"902574","allowed_gates":"ALL"}
]

DEVICE_SECRET
-------------
Shared secret between server and phone.
Used to authenticate:
• /phone_task
• /confirm

PUSHBULLET_API_KEY
------------------
Optional.
Used only for alerts (e.g. phone offline).


============================================================
 GATES DEFINITION (inside app.py)
============================================================

Each gate is defined in one place with:
• Name
• Phone number (for dial-based opening)
• Allowed time window

Example:
[
  {
    "name": "Main",
    "phone_number": "972505471743",
    "open_hours": [{"from":"00:00","to":"23:59"}]
  },
  {
    "name": "Enter",
    "phone_number": "972503924081",
    "open_hours": [{"from":"05:20","to":"21:00"}]
  }
]


============================================================
 INTERNAL SERVER STATE (IN-MEMORY)
============================================================

DEVICE_BUSY        — True while phone is executing a task
CURRENT_TASK       — Current task sent to phone
TASK_TIMESTAMP     — When the task was created
LAST_RESULT        — Last execution result for the client
LAST_PHONE_SEEN    — Last time the phone contacted the server
PB_ALERT_SENT      — Prevents duplicate alerts

No state is persisted across restarts.


============================================================
 API ENDPOINTS
============================================================

1) HEALTH CHECK
---------------
GET /

Response:
{ "status": "ok" }

Used only for manual testing.


2) GET ALLOWED GATES (Client → Server)
-------------------------------------
GET /allowed_gates?token=XXXX

Response:
{
  "allowed": ["Main","Gay","Enter","Exit","EinCarmel","Almagor"]
}


3) CREATE TASK (Client → Server)
--------------------------------
POST /open

Body:
{
  "token": "XXXXXX",
  "gate": "Enter"
}

Server flow:
✓ Validate token
✓ Validate user permissions
✓ Validate gate schedule
✓ Ensure device is not busy
✓ Create CURRENT_TASK
✓ Lock device

Response:
{ "status": "task_created" }


4) PHONE POLLING (Phone → Server)
---------------------------------
GET /phone_task?device_secret=XXXXX

Responses:
• Task available:
{
  "task": "open",
  "gate": "Enter",
  "phone_number": "972503924081"
}

• No task:
{ "task": "none" }

Phone polls every 2–10 seconds (dynamic).


5) CONFIRM RESULT (Phone → Server)
----------------------------------
POST /confirm

Body:
{
  "gate": "Enter",
  "status": "success",
  "device_secret": "XXXXX"
}

Server:
✓ Stores LAST_RESULT
✓ Releases device lock


6) CLIENT STATUS (Client → Server)
----------------------------------
GET /status

Responses:
{ "status": "pending" }
{ "status": "opened", "gate": "Enter" }
{ "status": "failed", "gate": "Enter" }
{ "status": "ready" }

Results are returned ONCE and then cleared.


============================================================
 TIMEOUT & SAFETY LOGIC
============================================================

Task timeout:
• If phone does not execute task within TASK_TIMEOUT (e.g. 20s)
→ task is discarded, device released

Phone heartbeat monitoring:
• LAST_PHONE_SEEN updated on every phone request
• If phone silent for > 10 minutes:
→ Pushbullet alert is sent once

This logic is triggered opportunistically
(only when server receives any request).


============================================================
 PUSHBULLET ROLE (CURRENT)
============================================================

Pushbullet is NOT used to open gates.

It is used ONLY for:
• Alerts when phone stops polling
• Future admin notifications

If Pushbullet fails, system continues to operate.


============================================================
 MACRODROID ROLE (PHONE)
============================================================

The phone:
• Polls /phone_task
• Executes exactly one task at a time
• Opens gate via app UI or phone call
• Sends /confirm with result
• Does NOT queue, retry, or decide


============================================================
 SCALING & LIMITATIONS
============================================================

This system is intentionally:
• Single-device
• Single-task
• In-memory only

It is NOT designed for:
• High traffic
• Multiple phones
• Guaranteed delivery after restart

Given the real usage (few operations per week),
this design is optimal and safe.


============================================================
 FUTURE IMPROVEMENTS (OPTIONAL)
============================================================

• Task queue
• Multi-device support
• Admin UI
• Persistent logs
• Signed payloads (HMAC)
• Replace MacroDroid with native Android app


============================================================
 END OF DOCUMENT
============================================================
