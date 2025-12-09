===========================================
 GATE OPENING SYSTEM - SERVER ARCHITECTURE
===========================================

Author: Yair  
Version: 1.0  
Last Update: 2025-12-08  

-------------------------------------------
 OVERVIEW
-------------------------------------------
This project provides a cloud-based gate-opening control system using:
 • Python Flask backend (hosted on Railway)
 • Pushbullet for sending gate-open commands to a local phone
 • Local Android phone + MacroDroid for performing the physical gate opening
 • JSON files for user permissions and gate schedules

The phone is NOT a logic unit.  
It only:
 1) Receives an instruction via Pushbullet
 2) Opens the physical gate
 3) Reports success/failure back to the Railway server

All business logic takes place on the SERVER.

-------------------------------------------
 FILE STRUCTURE
-------------------------------------------
/gates.json      – Gate list, opening hours  
/users.json      – User list, tokens, allowed gates  
/app.py          – Server application  
/README.txt      – This documentation  
/Dockerfile      – Railway deployment image  

-------------------------------------------
 API ENDPOINTS
-------------------------------------------

1) Health Check  
   GET /
   Response: {"status":"ok"}

2) Get Allowed Gates  
   GET /allowed_gates?token=XXXXXX  
   Server validates token and returns:  
   {
     "allowed": ["Main", "Enter", "Exit"]
   }

3) Open Gate  
   POST /open  
   JSON:
   {
     "token": "123456",
     "gate": "Main"
   }

   Server actions:
     • Validate token  
     • Validate gate exists  
     • Validate user allowed  
     • Validate gate active at this hour  
     • Create a session ID  
     • Send Pushbullet notification to the phone  
     • Return immediately to client:
         { "status":"received", "session":"ABC123" }

   Client should start polling session:
     GET /status?id=ABC123

4) Phone Confirmation (MacroDroid)
   POST /confirm
   JSON:
   {
     "session": "ABC123",
     "gate": "Main",
     "status": "opened"   (or "failed")
   }

   Server stores result:
     session: opened/failed

5) Client Poll
   GET /status?id=ABC123

   Possible answers:
     { "status":"pending" }
     { "status":"opened" }
     { "status":"failed", "reason":"no response from device" }

-------------------------------------------
 GATE SCHEDULE LOGIC
-------------------------------------------
If gate has no schedule → open 24/7  
If gate has schedule (e.g. 05:20–21:00):
   Server checks current time before allowing the request.

-------------------------------------------
 USER PERMISSION LOGIC
-------------------------------------------
Each user has:
 • name
 • token (6-digit numeric)
 • allowed_gates (list)

Example user:
{
  "name": "Miki",
  "token": "184029",
  "allowed": ["Main","Enter","Exit","Gay"]
}

-------------------------------------------
 SESSION HANDLING
-------------------------------------------
When a client requests to open a gate:
 • Server creates a session with state "pending"
 • Sends instruction to phone via Pushbullet
 • Starts a 30-second timer
 • If phone does not confirm → session becomes "failed"

-------------------------------------------
 PHONE LOGIC (MACRODROID)
-------------------------------------------
Phone receives Pushbullet note with content:
   gate=Main;device=xxxx

Phone must:
 • Parse gate name
 • Execute gate open command (local hardware)
 • Immediately POST back to server:
     /confirm
     payload: {"session":"XYZ","gate":"Main","status":"opened"}

-------------------------------------------
 FAILURE MODES
-------------------------------------------
1) User not authorized → server returns 403  
2) Gate outside hours → server returns 403  
3) Pushbullet error → server returns 500  
4) Phone not responding → session=failed after 30 seconds  
5) Invalid token → server returns 401  

-------------------------------------------
 FUTURE IMPROVEMENTS
-------------------------------------------
 • Add rate limiting  
 • Add logging (optional)  
 • Add admin dashboard  
 • Switch JSON → SQLite/MySQL  
 • Add JWT tokens  


-------------------------------------------
 DEVICE EXECUTION LIMITATION
-------------------------------------------
The Android device can handle ONLY ONE gate-opening
operation at a time.

The server enforces this by using device_status.json:

{
  "busy": false,
  "session": null
}

Rules:
• When a gate request is accepted, server sets busy=true.
• No new requests are allowed while busy=true.
• When the phone reports back (/confirm), busy=false.
• If the phone does not respond within 30 seconds:
     busy=false and session marked as "timeout".

This ensures the phone never receives overlapping commands
and guarantees consistent system behavior.
