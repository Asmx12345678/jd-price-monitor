#!/usr/bin/env python3
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from monitor.config import Settings
from monitor.scanner import Scanner
from monitor.storage import Storage


ROOT = Path(__file__).resolve().parent
SETTINGS = Settings.from_env(ROOT)
STORAGE = Storage(SETTINGS.database_path)
SCANNER = Scanner(SETTINGS, STORAGE)
RESCHEDULE = threading.Event()


def configured_threshold():
    value = STORAGE.get_state("drop_threshold_percent")
    return float(value) if value is not None else SETTINGS.drop_threshold_percent


def configured_interval():
    value = STORAGE.get_state("scan_interval_minutes")
    return int(value) if value is not None else SETTINGS.scan_interval_minutes


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "JDDealRadar/0.1"

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/deals":
            self._send(200, json_bytes({"items": STORAGE.deals()}))
            return
        if path == "/api/status":
            mode = "live" if SETTINGS.live_ready else "demo"
            self._send(200, json_bytes({
                "mode": mode,
                "configured": SETTINGS.live_ready,
                "running": SCANNER.running,
                "last_scan": STORAGE.get_state("last_scan"),
                "last_error": STORAGE.get_state("last_error") or "",
                "snapshot_count": STORAGE.snapshot_count(),
                "tracked_count": STORAGE.tracked_count(),
                "last_scan_count": int(STORAGE.get_state("last_scan_count") or "0"),
                "last_new_count": int(STORAGE.get_state("last_new_count") or "0"),
                "last_scan_page": int(STORAGE.get_state("last_scan_page") or "1"),
                "page_cycle": SETTINGS.discovery_pages,
                "channel_count": 13,
                "material_channel_count": 2,
                "source_warnings": STORAGE.get_state("source_warnings") or "",
                "activity_error": STORAGE.get_state("activity_error") or "",
                "site_id_configured": bool(SETTINGS.site_id),
                "position_id_configured": bool(SETTINGS.position_id),
                "capabilities": {
                    "jingfen": "enabled", "material": "enabled", "activity": "enabled",
                    "bigfield": "available", "rank": "needs_parameters",
                    # common.get only accepts website/app media. This project
                    # currently uses a social-shopping media position; product
                    # discovery responses already contain valid landing URLs.
                    "promotion_link": "social_media_unsupported" if (
                        SETTINGS.site_id and SETTINGS.position_id
                    ) else "needs_position_id",
                    "goods_query": "permission_missing", "coupon_query": "permission_missing",
                    "promotion_intelligence": "permission_missing",
                    "combination_query": "permission_missing",
                    "account_checkout": "not_public_api",
                },
                "interval_minutes": configured_interval(),
                "threshold_percent": configured_threshold(),
                "auto_scan": True,
                "public_read_only": SETTINGS.public_read_only,
                "price_model": "history_v2",
                "extreme_drop_confirmations": 2,
            }))
            return
        if path == "/api/activities":
            try:
                activities = json.loads(STORAGE.get_state("activities") or "[]")
            except json.JSONDecodeError:
                activities = []
            self._send(200, json_bytes({"items": activities}))
            return

        relative = "index.html" if path == "/" else path.lstrip("/")
        static_root = (ROOT / "static").resolve()
        target = (static_root / relative).resolve()
        if static_root not in target.parents and target != static_root:
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return
        if not target.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))

    def do_POST(self):
        path = urlparse(self.path).path
        if SETTINGS.public_read_only:
            self._send(403, json_bytes({
                "ok": False,
                "message": "公网展示站为只读模式，扫描规则只能由管理员在服务器端修改。",
            }))
            return
        if path == "/api/settings":
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 4096)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                threshold = float(body.get("threshold_percent"))
                interval = int(body.get("interval_minutes"))
                if not 0 <= threshold <= 100:
                    raise ValueError("降价阈值必须在 0% 到 100% 之间")
                if not 1 <= interval <= 1440:
                    raise ValueError("扫描间隔必须在 1 到 1440 分钟之间")
                STORAGE.set_state("drop_threshold_percent", str(threshold))
                STORAGE.set_state("scan_interval_minutes", str(interval))
                result = SCANNER.scan()
                RESCHEDULE.set()
                self._send(200 if result.get("ok") else 500, json_bytes({
                    **result,
                    "threshold_percent": threshold,
                    "interval_minutes": interval,
                }))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, json_bytes({"ok": False, "message": str(exc)}))
            return
        if path != "/api/scan":
            self._send(404, json_bytes({"ok": False, "message": "Not found"}))
            return
        result = SCANNER.scan()
        self._send(200 if result.get("ok") else 500, json_bytes(result))

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def scheduler():
    while True:
        changed = RESCHEDULE.wait(configured_interval() * 60)
        RESCHEDULE.clear()
        if changed:
            continue
        result = SCANNER.scan()
        print(f"自动扫描：{result}")


if __name__ == "__main__":
    first = SCANNER.scan()
    print(f"首次扫描：{first}")
    thread = threading.Thread(target=scheduler, daemon=True, name="deal-scanner")
    thread.start()
    server = ThreadingHTTPServer((SETTINGS.host, SETTINGS.port), Handler)
    print(f"京东超市降价雷达已启动：http://{SETTINGS.host}:{SETTINGS.port}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()

