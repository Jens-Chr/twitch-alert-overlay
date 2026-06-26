#!/usr/bin/env python3
import base64
import hashlib
import hmac
import html
import json
import mimetypes
import os
import queue
import tempfile
import threading
import time
import uuid
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT_DIR / "public"
ALERTS_DIR = Path(os.environ.get("ALERTS_DIR", ROOT_DIR / "alerts")).resolve()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("OBS_OVERLAY_PORT", "3000")))
MAX_BODY_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
MAX_MESSAGE_CHARS = 240
UPLOAD_CHUNK_BYTES = 64 * 1024
OVERLAY_PATH = "/overlay/alerts"
ASSET_PATH = f"{OVERLAY_PATH}/assets"
EVENTS_PATH = f"{OVERLAY_PATH}/events"
MEDIA_PATH = f"{OVERLAY_PATH}/media"
API_FILES_PATH = f"{OVERLAY_PATH}/api/files"
HEALTH_PATH = f"{OVERLAY_PATH}/health"
WEBHOOK_PATH = f"{OVERLAY_PATH}/webhook"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
TRUST_AUTHENTIK_HEADERS = os.environ.get("TRUST_AUTHENTIK_HEADERS", "").lower() in {"1", "true", "yes", "on"}
AUTHENTIK_REQUIRED_GROUP = os.environ.get("AUTHENTIK_REQUIRED_GROUP", "").strip()
ADMIN_BASE_PATH = "/admin/alerts"
ADMIN_LOGIN_PATH = f"{ADMIN_BASE_PATH}/login"
ADMIN_LOGOUT_PATH = f"{ADMIN_BASE_PATH}/logout"
ADMIN_AUTH_DEBUG_PATH = f"{ADMIN_BASE_PATH}/api/auth/debug"
ADMIN_API_FILES_PATH = f"{ADMIN_BASE_PATH}/api/files"
ADMIN_API_TRIGGER_PATH = f"{ADMIN_BASE_PATH}/api/trigger"
ADMIN_LOGIN_BODY_BYTES = 4 * 1024
ADMIN_SESSION_COOKIE = "twitch_alert_overlay_admin"
ADMIN_SESSION_COOKIE_KEY = "twitch-alert-overlay-admin-v1"

ADMIN_PAGE = """<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sali-H&uuml;pft Alert Admin</title>
    <link rel="stylesheet" href="/overlay/alerts/assets/admin.css">
  </head>
  <body>
    <div class="stream-admin-layout">
      <aside class="stream-admin-nav-panel" aria-label="Stream Admin Navigation">
        <div class="stream-admin-nav-brand">
          <strong>Stream Admin</strong>
          <span>Sali-H&uuml;pft</span>
        </div>
        <nav class="stream-admin-nav" aria-label="Admin-Anwendungen">
          <a class="stream-admin-nav-link" href="/admin/console/">Admin Console</a>
          <a class="stream-admin-nav-link" href="/admin/markdown">Markdown Overlay</a>
          <a class="stream-admin-nav-link" href="/admin/alerts" aria-current="page">Alert Overlay</a>
          <a class="stream-admin-nav-link" href="/grafana" target="_blank" rel="noopener noreferrer">Monitoring</a>
        </nav>
      </aside>

      <div class="stream-admin-main">
    <header class="topbar">
      <div class="brand">
        <strong>Sali-H&uuml;pft Admin</strong>
        <span>Alert WebM-Dateien</span>
      </div>
      {{LOGOUT_FORM}}
    </header>

    <main class="admin-shell">
      <aside class="sidebar panel" aria-label="WebM-Dateien">
        <div class="panel-header">
          <h1>WebM-Dateien</h1>
          <button id="uploadButton" class="icon-button" type="button" title="Hochladen" aria-label="Hochladen">+</button>
        </div>
        <div id="dropZone" class="drop-zone" tabindex="0">
          <input id="fileInput" type="file" accept="video/webm,.webm" multiple hidden>
          <strong>WebM ablegen</strong>
          <span id="uploadStatus">Bereit</span>
        </div>
        <div class="file-filters">
          <label for="searchInput">Suche
            <input id="searchInput" type="text" autocomplete="off" spellcheck="false">
          </label>
        </div>
        <div id="fileList" class="file-list"></div>
      </aside>

      <section class="editor panel" aria-label="Datei">
        <div class="panel-header">
          <h2>Datei</h2>
        </div>
        <form class="editor-form">
          <label for="nameInput">Name
            <input id="nameInput" type="text" readonly>
          </label>
          <div class="field-row">
            <label for="sizeInput">Groesse
              <input id="sizeInput" type="text" readonly>
            </label>
            <label for="modifiedInput">Geaendert
              <input id="modifiedInput" type="text" readonly>
            </label>
          </div>
          <label for="urlInput">OBS/Webhook-Datei
            <input id="urlInput" type="text" readonly>
          </label>
          <div id="selectedInfo" class="last-modified" hidden></div>
          <label for="messageInput">Message im Overlay
            <textarea id="messageInput" maxlength="240" rows="4" spellcheck="true"></textarea>
          </label>
          <div id="messageCount" class="char-count">0 / 240</div>
          <div class="actions">
            <div class="action-group">
              <button id="triggerButton" type="button" disabled>Im Overlay abspielen</button>
              <button id="refreshButton" class="secondary" type="button">Neu laden</button>
              <button id="deleteButton" class="danger" type="button" disabled>Loeschen</button>
            </div>
            <a id="openLink" class="button secondary is-disabled" href="#" target="_blank" rel="noreferrer">Oeffnen</a>
          </div>
        </form>
      </section>

      <section class="preview-shell" aria-label="Preview">
        <div class="panel-header">
          <h2>Preview</h2>
        </div>
        <div class="preview-stage">
          <video id="previewVideo" class="preview-video" controls playsinline preload="metadata" hidden></video>
          <div id="emptyPreview" class="empty-state">Keine Datei ausgewaehlt</div>
        </div>
      </section>
    </main>

    <div id="toast" class="toast" hidden></div>
    <script src="/overlay/alerts/assets/admin.js"></script>
      </div>
    </div>
  </body>
</html>
"""

ADMIN_LOGIN_PAGE = """<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sali-H&uuml;pft Alert Admin Login</title>
    <link rel="stylesheet" href="/overlay/alerts/assets/admin.css">
  </head>
  <body class="login-body">
    <main class="login-panel">
      <h1>Sali-H&uuml;pft Admin</h1>
      <p>Alert WebM-Dateien</p>
      {{MESSAGE_BLOCK}}
      <form method="post" action="/admin/alerts/login">
        <label for="password">Passwort
          <input id="password" name="password" type="password" autocomplete="current-password" autofocus required>
        </label>
        <button type="submit">Login</button>
      </form>
    </main>
  </body>
</html>
"""

clients = set()
clients_lock = threading.Lock()


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler, status, message):
    json_response(handler, status, {"ok": False, "error": message})


def redirect(handler, location):
    handler.send_response(HTTPStatus.FOUND)
    handler.send_header("Location", location)
    handler.end_headers()


def see_other(handler, location):
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)


def method_not_allowed(handler, *methods):
    body = json.dumps({"ok": False, "error": "Method not allowed."}).encode("utf-8")
    handler.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
    handler.send_header("Allow", ", ".join(methods))
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def safe_webm_name(value):
    if not isinstance(value, str):
        return None

    name = value.strip()
    if not name or name != Path(name).name:
        return None

    if Path(name).suffix.lower() != ".webm":
        return None

    return name


def resolve_alert_file(value):
    name = safe_webm_name(value)
    if not name:
        return None

    file_path = (ALERTS_DIR / name).resolve()
    try:
        file_path.relative_to(ALERTS_DIR)
    except ValueError:
        return None

    return name, file_path


def list_alert_files():
    if not ALERTS_DIR.exists():
        return []

    return sorted(
        entry.name
        for entry in ALERTS_DIR.iterdir()
        if entry.is_file() and entry.suffix.lower() == ".webm"
    )


def alert_file_detail(name):
    resolved = resolve_alert_file(name)
    if not resolved:
        return None

    safe_name, file_path = resolved
    if not file_path.exists() or not file_path.is_file():
        return None

    stat = file_path.stat()
    return {
        "name": safe_name,
        "size": stat.st_size,
        "modifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
        "url": f"{MEDIA_PATH}/{quote(safe_name)}",
    }


def list_alert_file_details():
    return [
        detail
        for detail in (alert_file_detail(name) for name in list_alert_files())
        if detail is not None
    ]


def normalize_alert_message(value):
    if not isinstance(value, str):
        return ""

    message = " ".join(value.split())
    return message[:MAX_MESSAGE_CHARS]


def broadcast(event_type, payload):
    message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
    encoded = message.encode("utf-8")

    with clients_lock:
        targets = list(clients)

    for client in targets:
        try:
            client.put_nowait(encoded)
        except queue.Full:
            with clients_lock:
                clients.discard(client)


def heartbeat():
    while True:
        time.sleep(25)
        broadcast("ping", {"now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


class OverlayHandler(BaseHTTPRequestHandler):
    server_version = "TwitchAlertOverlay/0.1"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            redirect(self, OVERLAY_PATH)
            return

        if path == ADMIN_BASE_PATH or path.startswith(f"{ADMIN_BASE_PATH}/"):
            self.handle_admin(parsed)
            return

        if path in ("/health", HEALTH_PATH):
            json_response(self, HTTPStatus.OK, {"ok": True})
            return

        if path in ("/api/files", API_FILES_PATH):
            json_response(self, HTTPStatus.OK, {"ok": True, "files": list_alert_files()})
            return

        if path == OVERLAY_PATH:
            self.serve_public_file(PUBLIC_DIR / "overlay.html")
            return

        if path == EVENTS_PATH:
            self.handle_events()
            return

        if path.startswith(f"{MEDIA_PATH}/"):
            self.serve_alert(path)
            return

        if path.startswith(f"{ASSET_PATH}/"):
            self.serve_asset(path)
            return

        error_response(self, HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == ADMIN_BASE_PATH or path.startswith(f"{ADMIN_BASE_PATH}/"):
            self.handle_admin(parsed)
            return

        if path not in ("/webhook", WEBHOOK_PATH):
            error_response(self, HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return

        self.handle_webhook()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == ADMIN_BASE_PATH or path.startswith(f"{ADMIN_BASE_PATH}/"):
            self.handle_admin(parsed)
            return

        error_response(self, HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def handle_admin(self, parsed):
        path = parsed.path.rstrip("/") or "/"

        if path == ADMIN_BASE_PATH:
            self.handle_admin_page()
            return

        if path == ADMIN_LOGIN_PATH:
            self.handle_admin_login()
            return

        if path == ADMIN_LOGOUT_PATH:
            self.handle_admin_logout()
            return

        if path == ADMIN_AUTH_DEBUG_PATH:
            self.handle_admin_auth_debug()
            return

        if path == ADMIN_API_TRIGGER_PATH:
            self.handle_admin_trigger()
            return

        if path == ADMIN_API_FILES_PATH or path.startswith(f"{ADMIN_API_FILES_PATH}/"):
            self.handle_admin_files(path)
            return

        error_response(self, HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def handle_admin_page(self):
        if self.command != "GET":
            method_not_allowed(self, "GET")
            return

        if not self.admin_authorized():
            self.render_admin_login(HTTPStatus.OK, "")
            return

        logout_form = ""
        if ADMIN_PASSWORD and not self.authentik_authorized():
            logout_form = (
                '<form method="post" action="/admin/alerts/logout">'
                '<button class="secondary" type="submit">Logout</button>'
                "</form>"
            )

        self.render_admin_html(ADMIN_PAGE.replace("{{LOGOUT_FORM}}", logout_form))

    def handle_admin_login(self):
        if not ADMIN_PASSWORD:
            see_other(self, ADMIN_BASE_PATH)
            self.end_headers()
            return

        if self.command == "GET":
            if self.admin_authorized():
                see_other(self, ADMIN_BASE_PATH)
                self.end_headers()
                return
            self.render_admin_login(HTTPStatus.OK, "")
            return

        if self.command != "POST":
            method_not_allowed(self, "GET", "POST")
            return

        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "0")
        except ValueError:
            self.render_admin_login(HTTPStatus.BAD_REQUEST, "Login konnte nicht gelesen werden.")
            return

        if length > ADMIN_LOGIN_BODY_BYTES:
            self.render_admin_login(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Login ist zu gross.")
            return

        fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        password = fields.get("password", [""])[0]
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            self.render_admin_login(HTTPStatus.UNAUTHORIZED, "Passwort stimmt nicht.")
            return

        see_other(self, ADMIN_BASE_PATH)
        self.send_admin_session_cookie()
        self.end_headers()

    def handle_admin_logout(self):
        if self.command != "POST":
            method_not_allowed(self, "POST")
            return

        see_other(self, ADMIN_BASE_PATH)
        self.clear_admin_session_cookie()
        self.end_headers()

    def handle_admin_auth_debug(self):
        if self.command != "GET":
            method_not_allowed(self, "GET")
            return

        if not self.admin_authorized():
            error_response(self, HTTPStatus.UNAUTHORIZED, "Admin login required.")
            return

        json_response(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "authenticated": True,
                "trustedAuthentikHeaders": TRUST_AUTHENTIK_HEADERS,
                "requiredGroup": AUTHENTIK_REQUIRED_GROUP,
                "authentik": self.authentik_user(),
            },
        )

    def handle_admin_files(self, path):
        if not self.admin_authorized():
            error_response(self, HTTPStatus.UNAUTHORIZED, "Admin login required.")
            return

        if path == ADMIN_API_FILES_PATH:
            if self.command != "GET":
                method_not_allowed(self, "GET")
                return
            json_response(self, HTTPStatus.OK, {"ok": True, "files": list_alert_file_details()})
            return

        name = unquote(path.removeprefix(f"{ADMIN_API_FILES_PATH}/"))
        resolved = resolve_alert_file(name)
        if not resolved:
            error_response(self, HTTPStatus.BAD_REQUEST, "Only local .webm file names are allowed.")
            return

        safe_name, file_path = resolved
        if self.command == "GET":
            detail = alert_file_detail(safe_name)
            if not detail:
                error_response(self, HTTPStatus.NOT_FOUND, "File not found.")
                return
            json_response(self, HTTPStatus.OK, {"ok": True, "file": detail})
            return

        if self.command == "POST":
            self.handle_admin_upload(safe_name, file_path)
            return

        if self.command == "DELETE":
            self.handle_admin_delete(safe_name, file_path)
            return

        method_not_allowed(self, "GET", "POST", "DELETE")

    def handle_admin_trigger(self):
        if not self.admin_authorized():
            error_response(self, HTTPStatus.UNAUTHORIZED, "Admin login required.")
            return

        if self.command != "POST":
            method_not_allowed(self, "POST")
            return

        payload = self.read_json_body()
        if payload is None:
            return

        self.send_alert(payload)

    def handle_admin_upload(self, name, file_path):
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "0")
        except ValueError:
            error_response(self, HTTPStatus.BAD_REQUEST, "Invalid Content-Length.")
            return

        if length <= 0:
            error_response(self, HTTPStatus.BAD_REQUEST, "Upload body is empty.")
            return

        if length > MAX_UPLOAD_BYTES:
            error_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Uploaded file is too large.")
            return

        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=ALERTS_DIR, prefix=".upload-", suffix=".tmp", delete=False) as target:
                temp_path = Path(target.name)
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise OSError("upload ended before Content-Length bytes were read")
                    target.write(chunk)
                    remaining -= len(chunk)

            os.replace(temp_path, file_path)
        except OSError as error:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            error_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, "Could not save uploaded file.")
            self.log_message("upload %s failed: %s", name, error)
            return

        self.log_message("uploaded %s (%s bytes)", name, length)
        json_response(self, HTTPStatus.CREATED, {"ok": True, "file": alert_file_detail(name)})

    def handle_admin_delete(self, name, file_path):
        if not file_path.exists() or not file_path.is_file():
            error_response(self, HTTPStatus.NOT_FOUND, "File not found.")
            return

        try:
            file_path.unlink()
        except OSError as error:
            error_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, "Could not delete file.")
            self.log_message("delete %s failed: %s", name, error)
            return

        self.log_message("deleted %s", name)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def render_admin_login(self, status, message):
        message_block = ""
        if message:
            message_block = f'<div class="message">{html.escape(message)}</div>'
        self.render_admin_html(ADMIN_LOGIN_PAGE.replace("{{MESSAGE_BLOCK}}", message_block), status)

    def render_admin_html(self, body, status=HTTPStatus.OK):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "media-src 'self' blob:; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'self'; form-action 'self'",
        )
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def admin_authorized(self):
        if self.authentik_authorized():
            return True

        if not ADMIN_PASSWORD:
            return True

        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except Exception:
            return False

        cookie = cookies.get(ADMIN_SESSION_COOKIE)
        if not cookie:
            return False

        return hmac.compare_digest(cookie.value, self.admin_session_value())

    def authentik_authorized(self):
        if not TRUST_AUTHENTIK_HEADERS:
            return False

        user = self.authentik_user()
        if not user["username"]:
            return False

        if not AUTHENTIK_REQUIRED_GROUP:
            return True

        return authentik_groups_contain(user["groups"], AUTHENTIK_REQUIRED_GROUP)

    def authentik_user(self):
        return {
            "username": self.headers.get("X-authentik-username", "").strip(),
            "name": self.headers.get("X-authentik-name", "").strip(),
            "email": self.headers.get("X-authentik-email", "").strip(),
            "groups": self.headers.get("X-authentik-groups", "").strip(),
        }

    def admin_session_value(self):
        digest = hmac.new(
            ADMIN_PASSWORD.encode("utf-8"),
            ADMIN_SESSION_COOKIE_KEY.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return "v1." + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def send_admin_session_cookie(self):
        cookie = (
            f"{ADMIN_SESSION_COOKIE}={self.admin_session_value()}; "
            f"Path={ADMIN_BASE_PATH}; HttpOnly; SameSite=Lax"
        )
        if self.secure_request():
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def clear_admin_session_cookie(self):
        cookie = f"{ADMIN_SESSION_COOKIE}=; Path={ADMIN_BASE_PATH}; Max-Age=0; HttpOnly; SameSite=Lax"
        if self.secure_request():
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def secure_request(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def handle_events(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        client = queue.Queue(maxsize=100)
        with clients_lock:
            clients.add(client)

        client.put(b'event: ready\ndata: {"ok": true}\n\n')

        try:
            while True:
                self.wfile.write(client.get())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with clients_lock:
                clients.discard(client)

    def read_json_body(self):
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "0")
        except ValueError:
            error_response(self, HTTPStatus.BAD_REQUEST, "Invalid Content-Length.")
            return None

        if length > MAX_BODY_BYTES:
            error_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
            return None

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            error_response(self, HTTPStatus.BAD_REQUEST, "Invalid JSON body.")
            return None

        if not isinstance(payload, dict):
            error_response(self, HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
            return None

        return payload

    def handle_webhook(self):
        payload = self.read_json_body()
        if payload is None:
            return

        self.send_alert(payload)

    def send_alert(self, payload):
        resolved = resolve_alert_file(payload.get("file") or payload.get("filename") or payload.get("name"))
        if not resolved:
            error_response(
                self,
                HTTPStatus.BAD_REQUEST,
                'JSON body must contain "file", "filename", or "name" with a local .webm file name.',
            )
            return

        name, file_path = resolved
        if not file_path.exists() or not file_path.is_file():
            error_response(self, HTTPStatus.NOT_FOUND, f'Alert file "{name}" does not exist in {ALERTS_DIR}.')
            return
        message = normalize_alert_message(payload.get("message") or payload.get("text") or payload.get("caption"))

        alert = {
            "id": str(uuid.uuid4()),
            "file": name,
            "url": f"{MEDIA_PATH}/{quote(name)}",
            "receivedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if message:
            alert["message"] = message

        broadcast("alert", alert)
        with clients_lock:
            listener_count = len(clients)
        json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "alert": alert, "listeners": listener_count})

    def serve_asset(self, request_path):
        relative = request_path.removeprefix(f"{ASSET_PATH}/")
        file_path = (PUBLIC_DIR / unquote(relative)).resolve()
        self.serve_file_from_base(file_path, PUBLIC_DIR)

    def serve_public_file(self, file_path):
        self.serve_file_from_base(file_path.resolve(), PUBLIC_DIR)

    def serve_alert(self, request_path):
        encoded_name = request_path.removeprefix(f"{MEDIA_PATH}/")
        name = unquote(encoded_name)
        resolved = resolve_alert_file(name)

        if not resolved:
            error_response(self, HTTPStatus.BAD_REQUEST, "Only local .webm file names are allowed.")
            return

        _, file_path = resolved
        self.serve_file_from_base(file_path, ALERTS_DIR, "video/webm")

    def serve_file_from_base(self, file_path, base_dir, content_type=None):
        try:
            file_path.relative_to(base_dir)
        except ValueError:
            error_response(self, HTTPStatus.FORBIDDEN, "Forbidden.")
            return

        if not file_path.exists() or not file_path.is_file():
            error_response(self, HTTPStatus.NOT_FOUND, "File not found.")
            return

        file_size = file_path.stat().st_size
        content_type = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        range_header = self.headers.get("Range")

        if range_header:
            parsed_range = self.parse_range(range_header, file_size)
            if not parsed_range:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return

            start, end = parsed_range
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with file_path.open("rb") as file:
                file.seek(start)
                self.wfile.write(file.read(end - start + 1))
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.end_headers()
        with file_path.open("rb") as file:
            self.wfile.write(file.read())

    def parse_range(self, range_header, file_size):
        if not range_header.startswith("bytes=") or "-" not in range_header:
            return None

        start_value, end_value = range_header.removeprefix("bytes=").split("-", 1)
        try:
            start = int(start_value) if start_value else 0
            end = int(end_value) if end_value else file_size - 1
        except ValueError:
            return None

        if start < 0 or end >= file_size or start > end:
            return None

        return start, end


def authentik_groups_contain(groups, required):
    return any(
        group.strip() == required
        for group in groups.replace(";", "|").replace(",", "|").split("|")
    )


def main():
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=heartbeat, daemon=True).start()

    server = ThreadingHTTPServer((HOST, PORT), OverlayHandler)
    print(f"OBS overlay: http://localhost:{PORT}{OVERLAY_PATH}")
    print(f"Admin UI:    http://localhost:{PORT}{ADMIN_BASE_PATH}")
    print(f"Webhook:     http://localhost:{PORT}{WEBHOOK_PATH}")
    print(f"Webhook alt: http://localhost:{PORT}/webhook")
    print(f"Alert files: {ALERTS_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
