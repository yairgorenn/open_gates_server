===========================================
 GATE OPENING SYSTEM - SERVER ARCHITECTURE
===========================================

Author: Yair  
Version: 1.1  
Last Update: 2025-12-09  

-------------------------------------------
 OVERVIEW
-------------------------------------------
This project provides a cloud-based gate-opening control system using:
 • Python Flask backend (Railway-hosted)
 • Pushbullet for sending gate-open commands to a local device
 • Android phone + MacroDroid for performing the physical gate opening
 • JSON files for user permissions, gate schedules, and device state

IMPORTANT:
The phone is NOT a logic unit.
It only:
 1) Receives an instruction via Pushbullet
 2) Opens the physical gate
 3) Reports success/failure back to the Railway server

All business logic takes place on the SERVER.


-------------------------------------------
 FILE STRUCTURE
-------------------------------------------
/gates.json          – Gate list, hours, schedules  
/users.json          – User list, tokens, allowed gates  
/device_status.json  – Device busy/pending-session tracking  
/app.py              – Main server application  
/README.txt          – This documentation  
/Dockerfile          – Railway deployment image  


-------------------------------------------
 API ENDPOINTS
-------------------------------------------

1) Health Check  
   GET /

   Response:
   { "status": "ok" }


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
     • Validate user permissions  
     • Validate gate active at this hour  
     • Validate device is not busy  
     • Create a session ID  
     • Mark device as busy  
     • Send Pushbullet notification to the phone  
     • Return immediately to client:
         {
           "status": "received",
           "session": "ABC123"
         }

   Client must poll:
     GET /status?id=ABC123


4) Phone Confirmation (MacroDroid)
   POST /confirm  
   JSON:
   {
     "session": "ABC123",
     "gate": "Main",
     "status": "opened"   (or "failed")
   }

   Server actions:
     • Match session  
     • Update session state  
     • Mark device not busy  
     • Store result


5) Client Session Poll  
   GET /status?id=ABC123

   Possible responses:
     { "status": "pending" }
     { "status": "opened" }
     { "status": "failed", "reason": "device_error" }
     { "status": "failed", "reason": "device_timeout" }


-------------------------------------------
 GATE SCHEDULE LOGIC
-------------------------------------------
If a gate has no schedule → open 24/7.

If gate has schedule (example: 05:20–21:00):
The server checks current time before allowing the request.  
If outside valid hours → request rejected.


-------------------------------------------
 USER PERMISSION LOGIC
-------------------------------------------
Each user entry contains:
 • name  
 • token (6-digit numeric)  
 • allowed_gates (list)

Example:
{
  "name": "Miki",
  "token": "184029",
  "allowed": ["Main", "Enter", "Exit", "Gay"]
}


-------------------------------------------
 SESSION HANDLING
-------------------------------------------
When a client requests to open a gate:

 • Server creates a session with state = "pending"  
 • Sends instruction to the phone  
 • Starts a 30-second timeout countdown  
 • If phone does not respond:
      session becomes "failed" with reason "device_timeout"
      device marked not busy


-------------------------------------------
 PHONE LOGIC (MACRODROID)
-------------------------------------------
Phone receives Pushbullet note containing:
   gate=Main;device=xxxx

Phone must:
 1) Parse gate name  
 2) Trigger local mechanism to open gate  
 3) POST back to server:

POST /confirm  
Payload:
{
  "session": "XYZ",
  "gate": "Main",
  "status": "opened"   // or failed
}

Phone does NOT wait for server response.  
Phone does NOT send unsolicited requests.  


-------------------------------------------
 FAILURE MODES
-------------------------------------------
1) User not authorized → 403  
2) Gate outside hours → 403  
3) Invalid token → 401  
4) Pushbullet delivery error → 500  
5) Device busy → 409 ("device is busy")  
6) Phone does not respond → "device_timeout"  
7) Gate or data missing → 400  


-------------------------------------------
 DEVICE EXECUTION LIMITATION
-------------------------------------------
The Android device can handle ONLY ONE operation at a time.

Tracking is done inside device_status.json:

{
  "busy": false,
  "session": null
}

Rules:
 • When a new request is accepted → busy=true  
 • No new requests allowed while busy=true  
 • When phone sends /confirm → busy=false  
 • If phone does not respond within 30 seconds:
      busy=false  
      session marked "timeout"

This guarantees:
 • No overlapping commands  
 • Predictable behavior  
 • Reliable system flow  


-------------------------------------------
 FUTURE IMPROVEMENTS
-------------------------------------------
 • Move JSON files into SQLite or MySQL  
 • Add encryption or signatures for MacroDroid payloads  
 • Add admin dashboard  
 • Add logging & monitoring  
 • Add support for multiple devices  
 • Queue system for redundant commands  
 • Add JWT-based authentication  

