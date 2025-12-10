============================================================
 README — OpenGate Cloud System (Version 2.1, English)
============================================================

OVERVIEW
--------
A lightweight cloud-based gate-opening system consisting of:

• Python Flask server hosted on Railway  
• Pushbullet for delivering gate-open commands to a phone  
• Android phone + MacroDroid acting ONLY as a hardware trigger  
• All decision-making and permissions handled by the server  
• No JSON storage, no session IDs, no polling loops on the server  

The phone is a **dumb endpoint**:
1. Receives a Pushbullet note with the gate name  
2. Executes the physical opening  
3. Reports back using `/confirm` with:
   - gate name  
   - status (“success” / “failed”)

All state is held **in memory** on the server.


FILE STRUCTURE
---------------
/app.py       — main server application  
/README.txt   — documentation  
/Dockerfile   — Railway deployment setup  

Gate and user definitions are embedded **inside app.py**.


DATA STRUCTURE (inside app.py)
------------------------------
### Users:
```python
USERS = [
    {"name": "Yair", "token": "482913", "allowed_gates": "ALL"},
    {"name": "Miki", "token": "173025", "allowed_gates": ["Main","Enter","Exit","Gay"]},
    {"name": "Raz",  "token": "650391", "allowed_gates": ["Main","Enter","Exit","Gay"]},
    {"name": "Nofar","token": "902574", "allowed_gates": "ALL"},
    {"name": "Liat", "token": "315760", "allowed_gates": "ALL"},
    {"name": "Alon", "token": "768204", "allowed_gates": "ALL"}
]
```

### Gates:
```python
GATES = {
    "Main":      {"hours": ("00:00", "23:59")},
    "Gay":       {"hours": ("00:00", "23:59")},
    "Enter":     {"hours": ("05:20", "21:00")},
    "Exit":      {"hours": ("05:20", "21:00")},
    "EinCarmel": {"hours": ("00:00", "23:59")},
    "Almagor":   {"hours": ("00:00", "23:59")}
}
```

### Global device state:
```python
DEVICE_BUSY = False
LAST_GATE = None
LAST_STATUS = None   # NEW — stores "opened", "failed", or None
DEVICE_TIMESTAMP = 0
```


============================================================
 API ENDPOINTS
============================================================

1) HEALTH CHECK
---------------
GET /

Response:
```json
{ "status": "ok" }
```


2) GET ALLOWED GATES
--------------------
GET /allowed_gates?token=XXXXX

If user has `"allowed_gates": "ALL"`, the server returns all gates.

Response example:
```json
{
  "allowed": ["Main","Enter","Exit","Gay","EinCarmel","Almagor"]
}
```


3) OPEN GATE (client → server → phone)
--------------------------------------
POST /open  
Body:
```json
{
  "token": "XXXXXX",
  "gate": "Main"
}
```

Server flow:
✓ Validate token  
✓ Validate permissions  
✓ Validate gate exists  
✓ Validate time window  
✓ Ensure device is NOT busy  
✓ Mark device busy  
✓ Save LAST_GATE  
✓ Clear LAST_STATUS  
✓ Send Pushbullet message to the phone  

Response:
```json
{ "status": "sent" }
```


4) PHONE CONFIRMATION
---------------------
POST /confirm  
Body:
```json
{
  "gate": "Main",
  "status": "success"
}
```

Server behavior:
✓ Saves LAST_STATUS (“opened” or “failed”)  
✓ Releases device lock  
✓ Returns:
```json
{ "ok": true }
```


5) CLIENT STATUS CHECK (new simplified model)
---------------------------------------------
GET /status

Server responses:
```json
{ "status": "pending" }       // device busy
{ "status": "opened", "gate": "Main" }
{ "status": "failed", "gate": "Main" }
{ "status": "ready" }         // idle and no result waiting
```

Right after the client consumes “opened”/“failed”,  
the server resets `LAST_STATUS = None`.


============================================================
 DEVICE BUSY & RESULT LOGIC
============================================================

The Android device can open only **one gate at a time**.

Server rules:
• Before /open: check `DEVICE_BUSY`  
• During operation: `DEVICE_BUSY = True`  
• When phone calls /confirm → `DEVICE_BUSY = False`  
• The open-result is stored in `LAST_STATUS`  
• Client reads it using /status  
• After client reads → server clears the result  

This ensures:
✓ No race conditions  
✓ No memory leaks  
✓ No session IDs needed  
✓ Works with one device reliably  


============================================================
 ERROR CODES
============================================================

400 — Missing fields  
401 — Invalid token  
403 — Not allowed / Gate closed  
409 — Device busy  
500 — Pushbullet failure or internal error  


============================================================
 MACRODROID LOGIC (PHONE SIDE)
============================================================

Pushbullet sends the body:
```
gate=Main
```

MacroDroid does:
1. Extract gate name  
2. Trigger the relay or app to open the gate  
3. Send:
```
POST /confirm
{
  "gate": "Main",
  "status": "success"
}
```

The phone does **not**:
✗ manage sessions  
✗ store history  
✗ retry  
✗ poll  
✗ hold any state  


============================================================
 FUTURE IMPROVEMENTS
============================================================

• Add queue to support multiple requests  
• Add admin dashboard  
• Add rate limiting per user  
• Add analytics (success/failure logs)  
• Add optional encryption/signature for phone callbacks  
• Add multi-device support  


============================================================
 END OF DOCUMENT
============================================================
