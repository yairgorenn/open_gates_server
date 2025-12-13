============================================================
README — OpenGate Cloud System (Redis-based, Stable Flow)
============================================================

OVERVIEW
--------
OpenGate is a low-traffic, highly reliable gate-opening system.
It is designed for real-world usage (5–10 openings per week),
with clear responsibility separation and deterministic behavior.

Core components:
• Flask server (Railway)
• Redis (state & TTL handling)
• Android phone running MacroDroid
• Client (CLI now, mobile app later)

The phone is a passive executor.
The server owns the logic.
The client owns the lifecycle.

============================================================
DESIGN PRINCIPLES
============================================================

• No background workers
• No long-running processes
• No server-side loops
• Polling-based architecture
• Redis handles timeouts & cleanup
• One task at a time (by design)
• Clear task lifecycle with timestamps

============================================================
HIGH-LEVEL FLOW
============================================================

1. Client requests gate opening
2. Server creates a task in Redis
3. Phone polls and executes task
4. Phone reports success/failure
5. Client polls status
6. Client closes the task by reading the result

If anything disappears — TTL cleans it safely.

============================================================
TASK LIFECYCLE (VERY IMPORTANT)
============================================================

A task can be closed ONLY by one of the following:

1) Client reads SUCCESS result
2) Client reads FAILED result
3) Redis TTL (20s) expires (both phone & client died)

The PHONE:
• NEVER deletes a task
• NEVER releases locks
• ONLY reports status

The CLIENT:
• Is responsible for reading the result
• By reading the result, it finalizes the task

============================================================
TIMEOUT LOGIC
============================================================

Two independent timers exist:

A) Execution window (10 seconds)
--------------------------------
Measured from task creation time.

If:
• Phone does not report success/failure
• Client polls /status
• Now - task_created_at > 10 seconds

Then:
→ Server returns FAILED to client
→ Task is deleted
→ Lock is released

B) Absolute safety TTL (20 seconds)
-----------------------------------
Handled by Redis TTL.

If:
• Client disappears
• Phone disappears
• Nobody polls

Then:
→ Redis deletes task automatically
→ System returns to READY state

============================================================
REDIS KEYS
============================================================

gate:lock
---------
Purpose:
• Prevents parallel gate openings
TTL:
• 20 seconds

gate:task
---------
Purpose:
• Current task for the phone
Content:
{
  "task": "open",
  "gate": "Enter",
  "phone_number": "9725XXXXXX",
  "created_at": 1710000000
}
TTL:
• 20 seconds

gate:result
-----------
Purpose:
• Result waiting for client to read
Content:
{
  "status": "opened" | "failed",
  "gate": "Enter",
  "reason": "timeout" (optional)
}
TTL:
• 10 seconds

============================================================
API ENDPOINTS
============================================================

1) GET /
--------
Health check only.

Response:
{ "status": "ok" }

------------------------------------------------------------

2) GET /allowed_gates
---------------------
Client → Server

Params:
• token

Response:
{
  "allowed": ["Main","Enter","Exit"]
}

------------------------------------------------------------

3) POST /open
-------------
Client → Server

Body:
{
  "token": "XXXX",
  "gate": "Enter"
}

Server actions:
✓ Validate token
✓ Validate permissions
✓ Validate time window
✓ Acquire Redis lock
✓ Create task with created_at

Response:
{ "status": "task_created" }

------------------------------------------------------------

4) GET /phone_task
------------------
Phone → Server

Params:
• device_secret

Responses:
• Task exists:
{
  "task": "open",
  "gate": "Enter",
  "phone_number": "9725XXXXXX"
}

• No task:
{ "task": "none" }

------------------------------------------------------------

5) POST /confirm
----------------
Phone → Server

Body:
{
  "gate": "Enter",
  "status": "success" | "failed",
  "device_secret": "XXXXX"
}

Server actions:
✓ Store result in Redis
✓ DOES NOT delete task
✓ DOES NOT release lock

------------------------------------------------------------

6) GET /status
--------------
Client → Server

Logic order:
1) If result exists → return it (and delete task+lock)
2) If task exists and < 10s → pending
3) If task exists and > 10s → failed + cleanup
4) Else → ready

Responses:
{ "status": "pending" }
{ "status": "opened", "gate": "Enter" }
{ "status": "failed", "gate": "Enter", "reason": "timeout" }
{ "status": "ready" }

============================================================
SECURITY
============================================================

• HTTPS (TLS)
• Tokens identify users
• DEVICE_SECRET authenticates phone
• Secrets stored only in Railway ENV
• No secrets in Git

============================================================
WHY THIS WORKS
============================================================

• Server does not “remember users”
• Redis is the single source of truth
• TTL guarantees cleanup
• No stuck states
• No DEVICE_BUSY forever bugs
• Predictable, testable behavior

============================================================
INTENDED USAGE
============================================================

• Very low traffic
• One physical phone
• One gate action at a time
• High reliability preferred over scale

============================================================
FUTURE EXTENSIONS (OPTIONAL)
============================================================

• Multiple phones
• Task queue
• Admin UI
• Native Android app
• HMAC-signed payloads
• Audit logs

============================================================
END OF DOCUMENT
============================================================
