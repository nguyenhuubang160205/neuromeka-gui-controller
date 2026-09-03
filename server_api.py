import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import logging

logger = logging.getLogger("RobotMasterAPI")


class OrderItem:
    def __init__(self, order_id, noodle_type="pho_bo_tai", dip_seconds=5.0, broth_seconds=3.5, table_id=1, customer_name=""):
        self.order_id = order_id or f"ORD_{int(time.time()*1000)%100000}"
        self.noodle_type = noodle_type
        self.dip_seconds = float(dip_seconds)
        self.broth_seconds = float(broth_seconds)
        self.table_id = table_id
        self.customer_name = customer_name
        self.status = "PENDING"  # PENDING, COOKING, COMPLETED, CANCELLED
        self.created_time = time.strftime("%H:%M:%S")
        self.finish_time = ""

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "noodle_type": self.noodle_type,
            "dip_seconds": self.dip_seconds,
            "broth_seconds": self.broth_seconds,
            "table_id": self.table_id,
            "customer_name": self.customer_name,
            "status": self.status,
            "created_time": self.created_time,
            "finish_time": self.finish_time
        }


class OrderQueueManager:
    """Quản lý hàng đợi đơn hàng nấu phở tự động cho PC Master"""
    def __init__(self):
        self.lock = threading.Lock()
        self.pending_queue = []
        self.current_order = None
        self.completed_history = []
        self.total_served_count = 0
        self.on_queue_change_cb = None

    def add_order(self, order: OrderItem) -> bool:
        with self.lock:
            self.pending_queue.append(order)
            logger.info(f"Đã nhận đơn hàng mới: {order.order_id} - {order.noodle_type} (Bàn {order.table_id})")
        if self.on_queue_change_cb:
            try: self.on_queue_change_cb()
            except Exception: pass
        return True

    def get_next_order(self) -> OrderItem:
        with self.lock:
            if not self.pending_queue:
                return None
            self.current_order = self.pending_queue.pop(0)
            self.current_order.status = "COOKING"
        if self.on_queue_change_cb:
            try: self.on_queue_change_cb()
            except Exception: pass
        return self.current_order

    def finish_current_order(self):
        with self.lock:
            if self.current_order:
                self.current_order.status = "COMPLETED"
                self.current_order.finish_time = time.strftime("%H:%M:%S")
                self.completed_history.insert(0, self.current_order)
                if len(self.completed_history) > 50:
                    self.completed_history.pop()
                self.total_served_count += 1
                self.current_order = None
        if self.on_queue_change_cb:
            try: self.on_queue_change_cb()
            except Exception: pass

    def get_queue_snapshot(self):
        with self.lock:
            return {
                "current": self.current_order.to_dict() if self.current_order else None,
                "pending": [o.to_dict() for o in self.pending_queue],
                "completed": [o.to_dict() for o in self.completed_history[:10]],
                "total_served": self.total_served_count,
                "pending_count": len(self.pending_queue)
            }


# Singleton Queue Manager
global_order_queue = OrderQueueManager()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server for Non-blocking API requests"""
    daemon_threads = True


class MasterAPIHandler(BaseHTTPRequestHandler):
    gui_instance = None  # Reference to IndyRobotGUI

    def _set_headers(self, status_code=200, content_type="application/json"):
        self.send_response(status_code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        url = self.path.split("?")[0]

        if url == "/" or url == "/api":
            self._set_headers(200, "text/html")
            html = """
            <html>
            <head><title>Neuromeka Conty Master IPC REST API</title></head>
            <body style='font-family:Segoe UI, sans-serif; background:#0f1015; color:#fff; padding:30px;'>
                <h1 style='color:#00d2ff;'>🤖 NEUROMEKA CONTY MASTER REST API</h1>
                <p>Hệ thống máy chủ điều khiển Robot Nấu Phở Tự Động sẵn sàng nhận lệnh từ Web / Mobile POS.</p>
                <ul>
                    <li><code>POST /api/order</code>: Gửi đơn hàng nấu phở mới</li>
                    <li><code>GET /api/status</code>: Trạng thái thời gian thực của Robot & Trạm Bếp</li>
                    <li><code>GET /api/queue</code>: Danh sách hàng đợi đơn hàng</li>
                    <li><code>POST /api/control</code>: Điều khiển Start / Pause / Resume / Stop</li>
                </ul>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
            return

        elif url == "/api/status":
            self._set_headers(200)
            status_data = {
                "system": "Neuromeka_Indy7_Pho_Master",
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "robot_connected": bool(self.gui_instance and self.gui_instance.robot_panel.is_connected),
                "machine_state": getattr(self.gui_instance, 'hmi_machine_state', 'UNKNOWN') if self.gui_instance else 'UNKNOWN',
                "sync_running": bool(self.gui_instance and self.gui_instance.sync_running),
                "sync_paused": bool(self.gui_instance and self.gui_instance.sync_paused),
                "pho_counter": getattr(self.gui_instance, 'pho_counter', 0) if self.gui_instance else 0,
                "order_queue": global_order_queue.get_queue_snapshot()
            }
            self.wfile.write(json.dumps(status_data, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        elif url == "/api/queue":
            self._set_headers(200)
            data = global_order_queue.get_queue_snapshot()
            self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def do_POST(self):
        url = self.path.split("?")[0]
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"

        try:
            body = json.loads(post_data) if post_data else {}
        except Exception:
            body = {}

        if url == "/api/order":
            # Nhận đơn hàng mới từ Web/Mobile App POS
            order_id = body.get("order_id") or f"P{int(time.time()*10)%10000:04d}"
            noodle_type = body.get("noodle_type", "pho_bo_tai")
            dip_seconds = float(body.get("dip_seconds", 5.0))
            broth_seconds = float(body.get("broth_seconds", 3.5))
            table_id = body.get("table_id", 1)
            customer_name = body.get("customer_name", "")

            order = OrderItem(order_id, noodle_type, dip_seconds, broth_seconds, table_id, customer_name)
            global_order_queue.add_order(order)

            # Nếu hệ thống đang rảnh (AUTO mode) và chưa chạy chu trình -> Tự động kích hoạt chu trình nấu
            if self.gui_instance and not self.gui_instance.sync_running:
                try:
                    self.gui_instance.root.after(100, self.gui_instance.process_next_order_auto)
                except Exception:
                    pass

            self._set_headers(200)
            res = {
                "success": True,
                "message": f"Đã tiếp nhận đơn hàng {order.order_id} thành công!",
                "order": order.to_dict(),
                "queue_position": len(global_order_queue.pending_queue)
            }
            self.wfile.write(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        elif url == "/api/control":
            # Điều khiển chu trình từ xa (Start / Pause / Resume / Stop / Emergency)
            action = str(body.get("action", "")).upper()
            success = False
            msg = ""

            if self.gui_instance:
                if action == "START":
                    self.gui_instance.root.after(0, self.gui_instance.start_pho_sequence)
                    success, msg = True, "Đã gửi lệnh START chu trình nấu phở"
                elif action == "PAUSE":
                    self.gui_instance.root.after(0, self.gui_instance.pause_pho_sequence)
                    success, msg = True, "Đã gửi lệnh PAUSE tạm dừng"
                elif action == "RESUME":
                    self.gui_instance.root.after(0, self.gui_instance.resume_pho_sequence)
                    success, msg = True, "Đã gửi lệnh RESUME tiếp tục"
                elif action == "STOP":
                    self.gui_instance.root.after(0, self.gui_instance.stop_pho_sequence)
                    success, msg = True, "Đã gửi lệnh STOP dừng chu trình"
                elif action == "EMERGENCY":
                    self.gui_instance.root.after(0, self.gui_instance.robot_panel.emergency_stop)
                    success, msg = True, "ĐÃ GỬI LỆNH EMERGENCY STOP KHẨN CẤP"
                else:
                    msg = f"Hành động không hợp lệ: {action}"
            else:
                msg = "GUI Instance chưa sẵn sàng"

            self._set_headers(200 if success else 400)
            self.wfile.write(json.dumps({"success": success, "message": msg}, ensure_ascii=False).encode("utf-8"))
            return

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def log_message(self, format, *args):
        # Ẩn log console mặc định để không làm rối terminal
        pass


class MasterAPIServer:
    """Quản lý vòng đời của Master REST API Server"""
    def __init__(self, host="0.0.0.0", port=8080, gui_instance=None):
        self.host = host
        self.port = port
        self.gui_instance = gui_instance
        self.server = None
        self.server_thread = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return
        MasterAPIHandler.gui_instance = self.gui_instance
        try:
            self.server = ThreadedHTTPServer((self.host, self.port), MasterAPIHandler)
            self.is_running = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            logger.info(f"🚀 Master IPC REST API Server đã khởi chạy tại http://localhost:{self.port}")
        except Exception as e:
            logger.error(f"Không thể mở Master REST API tại port {self.port}: {e}")

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        self.is_running = False
