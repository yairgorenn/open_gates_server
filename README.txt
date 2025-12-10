===========================================================
 README — OpenGate Cloud System (Version 2.0, English)
===========================================================

OVERVIEW
--------
A cloud-based gate-opening system consisting of:
• Python Flask server hosted on Railway  
• Pushbullet for sending gate-open commands to a phone  
• Android phone + MacroDroid performing ONLY the physical action  
• All business logic runs on the server  
• No JSON files, no session IDs, no polling

The phone is a **dumb endpoint**:
1. Receives a Pushbullet note containing the gate name  
2. Activates a relay / app to open the gate  
3. Reports back to the server using /confirm with only:  
   - gate name  
   - status (“success” / “failed”)

FILE STRUCTURE
---------------
/app.py       — main server application  
/README.txt   — documentation  
/Dockerfile   — Railway deployment setup  

Gate/user data is defined **inside app.py** (not in external files).

DATA STRUCTURE (inside app.py)
------------------------------
USERS = [
    {"name": "Yair", "token": "482913", "allowed": "ALL"},
    {"name": "Miki", "token": "173025", "allowed": ["Main","Enter","Exit","Gay"]},
    {"name": "Raz",  "token": "650391", "allowed": ["Main","Enter","Exit","Gay"]},
    {"name": "Nofar","token": "902574", "allowed": "ALL"},
    {"name": "Liat", "token": "315760", "allowed": "ALL"},
    {"name": "Alon", "token": "768204", "allowed": "ALL"}
]

GATES = {
    "Main":      {"hours": ("00:00", "23:59")},
    "Gay":       {"hours": ("00:00", "23:59")},
    "Enter":     {"hours": ("05:20", "21:00")},
    "Exit":      {"hours": ("05:20", "21:00")},
    "EinCarmel": {"hours": ("00:00", "23:59")},
    "Almagor":   {"hours": ("00:00", "23:59")}
}

# Global device lock
DEVICE_BUSY = False



===========================================================
 API ENDPOINTS
===========================================================

1) HEALTH CHECK
---------------
GET /
Response:
{ "status": "ok" }


2) GET ALLOWED GATES
--------------------
GET /allowed_gates?token=XXXXX

If user has allowed="ALL", all gates are returned.

Response example:
{
  "allowed": ["Main","Enter","Exit","Gay","EinCarmel","Almagor"]
}


3) OPEN GATE (client → server → phone)
--------------------------------------
POST /open  
Body:
{
  "token": "XXXXXX",
  "gate": "Main"
}

Server flow:
✓ Validate token  
✓ Validate permissions  
✓ Validate gate exists  
✓ Validate time window  
✓ Validate DEVICE_BUSY == False  
✓ Set DEVICE_BUSY = True  
✓ Send Pushbullet message to the phone  

Response:
{ "status": "sent" }


4) PHONE CONFIRMATION
---------------------
POST /confirm  
Body:
{
  "gate": "Main",
  "status": "success"   // or "failed"
}

Server:
✓ Releases lock → DEVICE_BUSY = False  
✓ Returns:

{ "ok": true }



===========================================================
 DEVICE BUSY LOGIC
===========================================================

The Android device can open only ONE gate at a time.

Rules:
• Before sending a command, server checks DEVICE_BUSY  
• If busy → /open returns 409 (device busy)  
• When phone sends /confirm → DEVICE_BUSY = False  

Process:
1. Client calls /open  
2. Server sets DEVICE_BUSY = True  
3. Phone opens gate  
4. Phone sends /confirm  
5. Server sets DEVICE_BUSY = False  

No session IDs, no polling, no storage of state.



===========================================================
 ERROR CODES
===========================================================

400 — Bad request  
401 — Invalid token  
403 — Not allowed / Gate closed based on schedule  
409 — Device busy  
500 — Pushbullet or internal error  



===========================================================
 MACRODROID WORKFLOW (PHONE LOGIC)
===========================================================

Pushbullet sends a notification like:
gate=Main

Phone:
1. Reads the gate name  
2. Runs automation to open the gate  
3. Sends a POST request to the server:

POST /confirm
{
  "gate": "Main",
  "status": "success"
}

Phone does **not** use:
✗ sessions  
✗ timers  
✗ polling  
✗ history storage  



===========================================================
 FUTURE IMPROVEMENTS
===========================================================

• Add queue for multiple requests  
• Add analytics and logs  
• Cryptographic signing for secure phone-server communication  
• Support multiple devices  
• Admin dashboard  
• Automatic retry logic  

===========================================================
 END OF DOCUMENT
===========================================================
