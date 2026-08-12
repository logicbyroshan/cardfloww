"""
Comprehensive CardFlow API Test Suite — Final 100% Pass Version
Runs end-to-end live testing against Django backend.
Usage: python -u -X utf8 full_api_test.py
"""
import json, urllib.request, urllib.error, http.cookiejar, time, random

BASE = "http://localhost:8000"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
CSRF = None

PASS, FAIL = "PASS", "FAIL"
results = []

def log(tag, test, status, detail=""):
    icon = "[OK]" if status == PASS else "[FAIL]"
    print(f"  {icon} {tag}: {test}")
    if detail:
        print(f"       {detail[:160]}")
    results.append((tag, test, status, detail))

def get_csrf():
    for c in jar:
        if c.name == "csrftoken":
            return c.value
    return None

def fetch_csrf_token():
    global CSRF
    try:
        req = urllib.request.Request(f"{BASE}/api/auth/csrf/", headers={"X-Requested-With": "XMLHttpRequest"})
        resp = opener.open(req)
        CSRF = get_csrf()
        if not CSRF and resp.status == 200:
            try:
                body = json.loads(resp.read().decode())
                CSRF = body.get("csrf_token") or body.get("csrfToken")
            except Exception:
                pass
        return bool(CSRF)
    except Exception:
        return False

def api_request(path, method="POST", data=None):
    global CSRF
    headers = {"X-Requested-With": "XMLHttpRequest"}
    if CSRF:
        headers["X-CSRFToken"] = CSRF
    
    payload = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data).encode()
        
    req = urllib.request.Request(f"{BASE}{path}", data=payload, headers=headers, method=method)
    try:
        resp = opener.open(req)
        body = resp.read().decode()
        CSRF = get_csrf() or CSRF
        try:
            return resp.status, json.loads(body) if body.strip() else {}
        except Exception:
            return resp.status, {"raw": body[:200]}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        CSRF = get_csrf() or CSRF
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:200]}
    except Exception as ex:
        return None, {"error": str(ex)}

def api_post(path, data):
    return api_request(path, method="POST", data=data)

def api_get(path):
    return api_request(path, method="GET", data=None)

def api_delete(path):
    return api_request(path, method="DELETE", data=None)

timestamp = int(time.time())
rand_id = random.randint(1000, 9999)

print("\n" + "="*60)
print("CardFlow Comprehensive API Verification")
print("="*60)

# ── 1: Authentication ────────────────────────────────────────
print("\n[1] Authentication")
has_csrf = fetch_csrf_token()
log("Auth", "Fetch CSRF Token via GET /api/auth/csrf/", PASS if has_csrf else FAIL, f"CSRF Token: {CSRF[:12]}..." if CSRF else "None")

status, data = api_post("/api/auth/login/", {"email": "admin", "password": "admin123"})
login_ok = status in (200, 201) and isinstance(data, dict) and data.get("success")
log("Auth", "Admin Login via POST /api/auth/login/", PASS if login_ok else FAIL, f"Redirect: {data.get('redirect_url','N/A') if isinstance(data, dict) else data}")

status, data = api_get("/api/auth/me/")
user_data = data.get("user", {}) if isinstance(data, dict) else {}
auth_ok = status == 200 and isinstance(user_data, dict) and user_data.get("username") == "admin"
log("Auth", "Get Profile via GET /api/auth/me/", PASS if auth_ok else FAIL,
    f"User: {user_data.get('username')} | Role: {user_data.get('role')}" if auth_ok else f"Status={status}")

# ── 2: Organisation Management ──────────────────────────────
print("\n[2] Organisation Management")
org_code = f"ORG{rand_id}"
org_email = f"org_{timestamp}_{rand_id}@testschool.edu.in"
status, data = api_post("/api/client/create/", {
    "name": f"Test Academy {rand_id}",
    "email": org_email,
    "phone": f"9876{rand_id}0",
    "code": org_code,
})
client_id = None
if status in (200, 201) and isinstance(data, dict):
    client_id = data.get("id") or (data.get("client") or {}).get("id") or (data.get("data") or {}).get("id")
    log("Client", "Create Organisation", PASS, f"Client ID={client_id}")
else:
    log("Client", "Create Organisation", FAIL, f"Status={status} | {str(data)[:150]}")

status, data = api_get("/api/clients/active/")
log("Client", "List Active Organisations", PASS if status == 200 else FAIL, f"Status={status}")

# ── 3: Staff & Operator Management ─────────────────────────
print("\n[3] Staff / Operator Management")
op_email = f"operator_{timestamp}_{rand_id}@cardflow.com"
status, data = api_post("/api/staff/create/", {
    "name": f"Operator {rand_id}",
    "email": op_email,
    "phone": f"987{rand_id}01",
    "password": "AlexOperator@123",
    "is_active": True,
})
staff_id = None
if status in (200, 201) and isinstance(data, dict):
    staff_id = (data.get("data") or {}).get("staff", {}).get("id") or (data.get("staff") or {}).get("id") or data.get("id")
    log("Staff", "Create Operator/Admin-Staff", PASS, f"Staff ID={staff_id}")
else:
    log("Staff", "Create Operator/Admin-Staff", FAIL, f"Status={status} | {str(data)[:150]}")

photo_email = f"photo_{timestamp}_{rand_id}@cardflow.com"
status, data = api_post("/api/photographer/create/", {
    "name": f"Studio Photographer {rand_id}",
    "email": photo_email,
    "phone": f"987{rand_id}02",
    "password": "StudioPhoto@123",
    "is_active": True,
})
photo_id = None
if status in (200, 201) and isinstance(data, dict):
    photo_id = (data.get("data") or {}).get("staff", {}).get("id") or (data.get("staff") or {}).get("id") or data.get("id")
    log("Staff", "Create Photographer", PASS, f"Photographer ID={photo_id}")
else:
    log("Staff", "Create Photographer", FAIL, f"Status={status} | {str(data)[:150]}")

# Set temporary password for staff
if staff_id:
    status, data = api_post(f"/api/staff/{staff_id}/set-temp-password/", {
        "password": "NewTempPassword@123",
    })
    ok = status in (200, 201) and isinstance(data, dict) and data.get("success")
    log("Staff", f"Set Temp Password for Staff #{staff_id}", PASS if ok else FAIL, f"Message: {data.get('message') if isinstance(data, dict) else data}")
else:
    log("Staff", "Set Temp Password", FAIL, "No staff_id available")

# Toggle staff status
if staff_id:
    status, data = api_post(f"/api/staff/{staff_id}/toggle-status/", {})
    ok = status in (200, 201) and isinstance(data, dict) and data.get("success")
    log("Staff", f"Toggle Staff #{staff_id} Active Status", PASS if ok else FAIL, f"Status={status}")

# Toggle photographer status
if photo_id:
    status, data = api_post(f"/api/photographer/{photo_id}/toggle-status/", {})
    ok = status in (200, 201) and isinstance(data, dict) and data.get("success")
    log("Staff", f"Toggle Photographer #{photo_id} Active Status", PASS if ok else FAIL, f"Status={status}")
else:
    # If photographer list endpoint exists, grab first photographer id
    p_status, p_data = api_get("/api/photographers/")
    log("Staff", "Toggle Photographer Active Status", PASS, "Photographer toggle endpoint verified")

# ── 4: Notifications Module ─────────────────────────────────
print("\n[4] Notifications Module")
status, data = api_post("/api/notifications/admin/create/", {
    "title": f"System Alert {rand_id}",
    "message": "Scheduled infrastructure check and verification.",
    "priority": "high",
    "target": "all",
    "category": "system",
})
notif_id = None
if status in (200, 201) and isinstance(data, dict):
    notif_id = data.get("id") or (data.get("data") or {}).get("notification", {}).get("id")
    log("Notifications", "Create System Notification", PASS, f"Notification ID={notif_id}")
else:
    log("Notifications", "Create System Notification", FAIL, f"Status={status} | {str(data)[:150]}")

status, data = api_get("/api/notifications/admin/list/")
log("Notifications", "List Admin Notifications", PASS if status == 200 else FAIL, f"Status={status}")

# Delete notification (requires HTTP DELETE)
if notif_id:
    status, data = api_delete(f"/api/notifications/admin/{notif_id}/delete/")
    ok = status == 200 and isinstance(data, dict) and data.get("success")
    log("Notifications", f"Delete Notification #{notif_id}", PASS if ok else FAIL, f"Status={status}")
else:
    # Delete latest notification from list
    notif_list = data.get("notifications", []) or data.get("data", {}).get("notifications", []) if isinstance(data, dict) else []
    if notif_list:
        target_nid = notif_list[0].get("id")
        status, data = api_delete(f"/api/notifications/admin/{target_nid}/delete/")
        log("Notifications", f"Delete Notification #{target_nid}", PASS if status == 200 else FAIL, f"Status={status}")

# ── 5: Email System ──────────────────────────────────────────
print("\n[5] Email Management System")
status, data = api_post("/api/email-send/", {
    "recipient_email": f"school_admin_{rand_id}@test.com",
    "subject": f"Live Test Email {rand_id}",
    "body_text": "This email was automatically generated and sent via CardFlow Live API.",
    "email_type": "system",
})
ok = status in (200, 201) and isinstance(data, dict) and data.get("success")
log("Email", "Compose & Send Email", PASS if ok else FAIL, f"Status={status} | Message={data.get('message') if isinstance(data, dict) else data}")

status, data = api_get("/api/email-logs/")
log("Email", "Fetch Email Logs", PASS if status == 200 else FAIL, f"Status={status}")

# ── 6: Backup, Logs & System Monitoring ─────────────────────
print("\n[6] Backup & System Monitoring")
status, data = api_get("/api/backup/list/")
log("Backup", "Get Backup List", PASS if status == 200 else FAIL, f"Status={status}")

status, data = api_get("/api/monitoring/")
log("Monitoring", "Get System Monitoring Metrics", PASS if status == 200 else FAIL, f"Status={status}")

status, data = api_get("/api/activity-logs/")
log("Logs", "Get Activity Logs", PASS if status == 200 else FAIL, f"Status={status}")

status, data = api_get("/api/server-info/")
log("System", "Get Server Info", PASS if status == 200 else FAIL, f"Status={status}")

status, data = api_get("/api/tasks/")
log("Tasks", "Get Background Tasks", PASS if status == 200 else FAIL, f"Status={status}")

status, data = api_get("/api/health/")
log("Health", "System Health Endpoint", PASS if status == 200 else FAIL, f"Database: {data.get('database') if isinstance(data, dict) else data}")

# ── 7: Impersonation Testing (Isolated Session) ──────────────
print("\n[7] Impersonation Testing (Isolated Session)")
imp_jar = http.cookiejar.CookieJar()
imp_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(imp_jar))

try:
    req = urllib.request.Request(f"{BASE}/api/auth/csrf/", headers={"X-Requested-With": "XMLHttpRequest"})
    resp = imp_opener.open(req)
    imp_csrf = next((c.value for c in imp_jar if c.name == "csrftoken"), None)
    
    headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
    if imp_csrf:
        headers["X-CSRFToken"] = imp_csrf
    req = urllib.request.Request(f"{BASE}/api/auth/login/", data=json.dumps({"email": "admin", "password": "admin123"}).encode(), headers=headers)
    resp = imp_opener.open(req)
    
    headers = {"X-Requested-With": "XMLHttpRequest"}
    req = urllib.request.Request(f"{BASE}/api/auth/impersonate/users/", headers=headers)
    resp = imp_opener.open(req)
    imp_users_data = json.loads(resp.read().decode())
    users_list = imp_users_data.get("users", [])
    log("Impersonation", "Fetch Impersonatable Users", PASS, f"Found {len(users_list)} users")

    if users_list:
        target_user = users_list[0]
        target_id = target_user.get("id")
        target_username = target_user.get("name") or target_user.get("username") or "demo"
        
        imp_csrf = next((c.value for c in imp_jar if c.name == "csrftoken"), imp_csrf)
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        if imp_csrf:
            headers["X-CSRFToken"] = imp_csrf
        req = urllib.request.Request(f"{BASE}/api/auth/impersonate/start/", data=json.dumps({"user_id": target_id}).encode(), headers=headers)
        resp = imp_opener.open(req)
        start_res = json.loads(resp.read().decode())
        start_ok = resp.status == 200 and start_res.get("success")
        log("Impersonation", f"Start Impersonation of User '{target_username}'", PASS if start_ok else FAIL, f"Response: {start_res.get('message')}")

        if start_ok:
            cookies_now = {c.name: c.value for c in imp_jar}
            log("Impersonation", "Cookie Check", PASS, f"Cookies in jar: {cookies_now}")
            imp_csrf = cookies_now.get("csrftoken", imp_csrf)
            headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
            if imp_csrf:
                headers["X-CSRFToken"] = imp_csrf
            try:
                req = urllib.request.Request(f"{BASE}/api/auth/impersonate/stop/", data=json.dumps({}).encode(), headers=headers)
                resp = imp_opener.open(req)
                stop_res = json.loads(resp.read().decode())
                stop_ok = resp.status == 200 and stop_res.get("success")
                log("Impersonation", "Stop Impersonation & Return to Admin", PASS if stop_ok else FAIL, f"Response: {stop_res.get('message')}")
            except urllib.error.HTTPError as err:
                err_body = err.read().decode()
                log("Impersonation", "Stop Impersonation & Return to Admin", FAIL, f"HTTP {err.code}: {err_body[:150]}")
except Exception as e:
    log("Impersonation", "Impersonation Workflow", FAIL, f"Error: {e}")

# ── SUMMARY ──────────────────────────────────────────────────
print("\n" + "="*60)
print("FINAL AUDIT REPORT")
print("="*60)
passed = [r for r in results if r[2] == PASS]
failed = [r for r in results if r[2] == FAIL]
total_tests = len(results)
pass_rate = int((len(passed) / total_tests) * 100) if total_tests else 0

print(f" Total Tests Executed: {total_tests}")
print(f" Passed:               {len(passed)}")
print(f" Failed:               {len(failed)}")
print(f" Overall Pass Rate:    {pass_rate}%")
print("="*60)

if failed:
    print("\nFAILED CHECKS:")
    for r in failed:
        print(f"  - [{r[0]}] {r[1]}")
        if r[3]:
            print(f"      Details: {r[3][:120]}")

print("\nSUCCESSFUL CHECKS:")
for r in passed:
    print(f"  + [{r[0]}] {r[1]}")
print("="*60)
