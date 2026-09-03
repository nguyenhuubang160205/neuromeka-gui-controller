import os
import sys
import time
import json
import threading
import csv
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from client import UnifiedIndyClient

ZONE_DATA_LIST = [
    "fine (Dừng chính xác)",
    "z1 (1mm)",
    "z5 (5mm)",
    "z10 (10mm)",
    "z30 (30mm)",
    "z50 (50mm)",
    "z100 (100mm)",
    "z200 (200mm)"
]

def parse_zone_data(zone_str):
    if "z1 (" in zone_str or zone_str == "z1": return True, 1.0, "z1"
    if "z5 (" in zone_str or zone_str == "z5": return True, 5.0, "z5"
    if "z10 (" in zone_str or zone_str == "z10": return True, 10.0, "z10"
    if "z30 (" in zone_str or zone_str == "z30": return True, 30.0, "z30"
    if "z50 (" in zone_str or zone_str == "z50": return True, 50.0, "z50"
    if "z100 (" in zone_str or zone_str == "z100": return True, 100.0, "z100"
    if "z200 (" in zone_str or zone_str == "z200": return True, 200.0, "z200"
    return False, 0.0, "fine"

def get_zone_label(is_fillet, radius):
    if not is_fillet or radius <= 0: return "fine"
    if radius <= 2: return "z1"
    if radius <= 7: return "z5"
    if radius <= 20: return "z10"
    if radius <= 40: return "z30"
    if radius <= 75: return "z50"
    if radius <= 150: return "z100"
    return "z200"


def build_jog_delta(mode, axis_label, direction, speed=200.0, step_size=None):
    """
    Tạo vector Jog theo quy ước nội bộ:
    Joint/rotation dùng độ; Task X/Y/Z dùng mét (UI nhập và hiển thị mm).
    """
    direction = -1 if direction < 0 else 1
    labels = (
        ["J1", "J2", "J3", "J4", "J5", "J6"]
        if mode == "joint"
        else ["X", "Y", "Z", "Rx", "Ry", "Rz"]
    )
    index = labels.index(axis_label) if axis_label in labels else 0

    if step_size is None:
        if mode == "task" and axis_label in ("X", "Y", "Z"):
            value = (1.0 + (float(speed) / 900.0) * 4.0) / 1000.0
        else:
            value = 0.5 + (float(speed) / 900.0) * 1.5
    else:
        value = abs(float(step_size))
        if mode == "task" and axis_label in ("X", "Y", "Z"):
            value /= 1000.0

    delta = [0.0] * 6
    delta[index] = value * direction
    return delta


class RobotControlPanel(tk.Frame):
    def __init__(self, parent, panel_name, default_ip):
        super().__init__(parent)
        self.panel_name = panel_name
        self.robot_name = panel_name
        self.default_ip = default_ip
        
        # Cấu hình màu sắc Dark Mode đồng nhất
        self.bg_color = "#1e1e24"
        self.card_color = "#2a2b36"
        self.text_color = "#ffffff"
        self.accent_blue = "#007acc"
        self.accent_green = "#28a745"
        self.accent_red = "#dc3545"
        self.accent_orange = "#fd7e14"
        self.accent_gray = "#4e5166"
        
        self.configure(bg=self.bg_color)
        
        # Giới hạn khớp của Indy7
        self.joint_limits = [
            (-175.0, 175.0),
            (-145.0, 145.0),
            (-145.0, 145.0),
            (-175.0, 175.0),
            (-175.0, 175.0),
            (-175.0, 175.0)
        ]
        
        self.limit_canvases = []
        self.limit_pointers = []
        self.limit_fill_rects = []
        self.limit_labels = []
        
        # Biến điều khiển
        self.indy = None
        self.is_connected = False
        self.selected_joint = tk.StringVar(value="J1")
        self.step_size = tk.DoubleVar(value=5.0)
        self.payload_mass = tk.DoubleVar(value=2.0)
        self.payload_cog_x = tk.DoubleVar(value=0.0)
        self.payload_cog_y = tk.DoubleVar(value=0.0)
        self.payload_cog_z = tk.DoubleVar(value=50.0)
        self.friction_comp_levels = [tk.IntVar(value=3) for _ in range(6)]
        self.dt_friction_comp_levels = [tk.IntVar(value=v) for v in [3, 3, 3, 0, 0, 0]]
        self.wrist_hold_var = tk.BooleanVar(value=True)
        self.jog_active = False
        self.jog_holding = False
        self.jog_direction = 0
        self.jog_type = tk.StringVar(value="continuous")
        self.collision_level_var = tk.StringVar(value="1 - Rộng nhất (Khuyên dùng)")
        self.jog_thread = None
        self._jog_stop_event = threading.Event()
        self._jog_generation = 0
        self._jog_lock = threading.Lock()
        self._speed_lock = threading.Lock()
        self._speed_pending = None
        self._speed_worker_running = False
        self.saved_targets = []
        self.use_fillet = tk.BooleanVar(value=False)
        self.cycle_running = False
        self.status_cache = {'ready': 0, 'emergency': 0, 'collision': 0, 'error': 0, 'busy': 0}
        self.status_cache_time = 0.0

        # Tkinter không thread-safe. Worker chỉ đẩy callback vào queue; queue
        # được rút duy nhất bởi main loop để không gọi widget từ background.
        self._ui_queue = queue.SimpleQueue()
        self._ui_dispatcher_closed = False
        
        self.canvas = tk.Canvas(self, bg=self.bg_color, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.container_frame = tk.Frame(self.canvas, bg=self.bg_color)

        self.container_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.container_frame, anchor="nw")

        def _on_canvas_config(event):
            req_h = self.container_frame.winfo_reqheight()
            new_h = max(event.height, req_h)
            self.canvas.itemconfig(self.canvas_window, width=event.width, height=new_h)

        self.canvas.bind("<Configure>", _on_canvas_config)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Hỗ trợ cuộn chuột (Mousewheel) trên Laptop
        def _on_mw(event):
            try:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.canvas.bind("<MouseWheel>", _on_mw)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Tạo giao diện Left & Right bên trong container_frame
        self.left_frame = tk.Frame(self.container_frame, bg=self.bg_color)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(10, 5))
        
        self.right_frame = tk.Frame(self.container_frame, bg=self.bg_color)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)
        
        self.create_widgets()
        self._auto_load_targets()
        self.after(25, self._drain_ui_queue)
        
        # Luồng cập nhật trạng thái tự động cho panel này
        self.running = True
        self.status_thread = threading.Thread(target=self.update_status_loop, daemon=True)
        self.status_thread.start()

    def _post_ui(self, callback):
        if not self._ui_dispatcher_closed:
            self._ui_queue.put(callback)

    def _drain_ui_queue(self):
        if self._ui_dispatcher_closed:
            return
        for _ in range(32):
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except tk.TclError:
                self._ui_dispatcher_closed = True
                return
            except Exception as exc:
                print(f"Lỗi cập nhật UI {self.panel_name}: {exc}")
        self.after(25, self._drain_ui_queue)

    def create_widgets(self):
        # 1. TIÊU ĐỀ BẢNG ĐIỀU KHIỂN
        title_label = tk.Label(self.left_frame, text=f"BẢNG ĐIỀU KHIỂN - {self.panel_name.upper()}", font=("Segoe UI", 14, "bold"),
                               bg=self.bg_color, fg=self.text_color)
        title_label.pack(pady=10)
        
        # 2. KHUNG KẾT NỐI (Connection Box)
        conn_frame = tk.LabelFrame(self.left_frame, text=" Cấu hình kết nối ", font=("Segoe UI", 10, "bold"),
                                   bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        conn_frame.pack(padx=20, fill="x", pady=5)
        
        tk.Label(conn_frame, text="IP Robot:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 10)).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.ip_entry = tk.Entry(conn_frame, font=("Segoe UI", 10), bg="#1e1e24", fg="#ffffff", insertbackground="white", width=14)
        self.ip_entry.insert(0, self.default_ip)
        self.ip_entry.grid(row=0, column=1, padx=3, pady=10)
        
        self.btn_auto_ip = tk.Button(conn_frame, text="🔍 Dò IP", font=("Segoe UI", 8, "bold"), bg="#8e44ad", fg="white",
                                     command=self.auto_detect_neuromeka_ip)
        self.btn_auto_ip.grid(row=0, column=2, padx=3, pady=10)

        self.btn_connect = tk.Button(conn_frame, text="Connect", font=("Segoe UI", 9, "bold"), bg=self.accent_blue, fg="white",
                                     width=9, command=self.connect_robot, activebackground="#005999", activeforeground="white")
        self.btn_connect.grid(row=0, column=3, padx=3, pady=10)
        
        self.btn_disconnect = tk.Button(conn_frame, text="Disconnect", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                                        width=9, command=self.disconnect_robot, state="disabled")
        self.btn_disconnect.grid(row=0, column=4, padx=3, pady=10)
        
        self.lbl_status = tk.Label(conn_frame, text="DISCONNECTED", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg=self.accent_red)
        self.lbl_status.grid(row=0, column=5, padx=8, pady=10)
        
        # 3. TRẠNG THÁI HỆ THỐNG
        status_frame = tk.LabelFrame(self.left_frame, text=" Trạng thái hệ thống ", font=("Segoe UI", 10, "bold"),
                                     bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        status_frame.pack(padx=20, fill="x", pady=5)
        
        self.badge_ready = tk.Label(status_frame, text="READY: NO", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white", width=12, height=1)
        self.badge_ready.grid(row=0, column=0, padx=10, pady=10)
        
        self.badge_emg = tk.Label(status_frame, text="EMG: NORMAL", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white", width=12, height=1)
        self.badge_emg.grid(row=0, column=1, padx=10, pady=10)
        
        self.badge_col = tk.Label(status_frame, text="COLLISION: NO", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white", width=12, height=1)
        self.badge_col.grid(row=0, column=2, padx=10, pady=10)
        
        self.badge_err = tk.Label(status_frame, text="ERROR: NO", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white", width=12, height=1, cursor="hand2")
        self.badge_err.grid(row=0, column=3, padx=10, pady=10)
        self.badge_err.bind("<Button-1>", lambda e: self.open_error_details_dialog())

        self.lbl_error_info = tk.Label(status_frame, text="✓ Trạng thái: Hệ thống bình thường", 
                                       font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.accent_green, anchor="w", justify="left")
        self.lbl_error_info.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="we")

        self.btn_err_detail = tk.Button(status_frame, text="🔍 Chi tiết lỗi", font=("Segoe UI", 8, "bold"),
                                        bg=self.accent_blue, fg="white", command=self.open_error_details_dialog)
        self.btn_err_detail.grid(row=1, column=3, padx=10, pady=(0, 8), sticky="e")
        
        # 4. TỌA ĐỘ HIỆN TẠI (Joint & TCP)
        pos_frame = tk.LabelFrame(self.left_frame, text=" Tọa độ Robot (Joint & TCP) ", font=("Segoe UI", 10, "bold"),
                                  bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        pos_frame.pack(padx=20, fill="x", pady=5)
        
        self.angle_labels = []
        for i in range(6):
            lbl = tk.Label(pos_frame, text=f"J{i+1}: 0.00°", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg="#f1c40f")
            lbl.grid(row=i//3, column=i%3, padx=15, pady=8, sticky="w")
            self.angle_labels.append(lbl)
            
        separator = ttk.Separator(pos_frame, orient="horizontal")
        separator.grid(row=2, column=0, columnspan=3, sticky="we", pady=5)
        
        self.tcp_labels = []
        tcp_names = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
        for i in range(6):
            unit = "mm" if i < 3 else "°"
            lbl = tk.Label(pos_frame, text=f"{tcp_names[i]}: 0.00 {unit}", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg="#3498db")
            lbl.grid(row=3 + i//3, column=i%3, padx=15, pady=8, sticky="w")
            self.tcp_labels.append(lbl)

        calib_btn_frame = tk.Frame(pos_frame, bg=self.card_color)
        calib_btn_frame.grid(row=5, column=0, columnspan=6, padx=5, pady=6, sticky="we")

        self.btn_tcp_calib = tk.Button(calib_btn_frame, text="🎯 Hiệu Chuẩn TCP (4 Điểm)", font=("Segoe UI", 9, "bold"),
                                       bg=self.accent_blue, fg="white", command=self.open_tcp_calib_dialog, state="disabled")
        self.btn_tcp_calib.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_ref_frame_calib = tk.Button(calib_btn_frame, text="📐 Dựng Hệ Trục Ref Frame (3 Điểm)", font=("Segoe UI", 9, "bold"),
                                             bg="#8e44ad", fg="white", command=self.open_ref_frame_calib_dialog, state="disabled")
        self.btn_ref_frame_calib.pack(side="right", fill="x", expand=True, padx=(3, 0))

        # 5. BẢNG ĐIỀU KHIỂN THỦ CÔNG & JOG
        ctrl_frame = tk.LabelFrame(self.left_frame, text=" Bảng điều khiển (Nhấn giữ để Jog liên tục) ", font=("Segoe UI", 10, "bold"),
                                   bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        ctrl_frame.pack(padx=20, fill="both", expand=True, pady=5)
        
        tk.Label(ctrl_frame, text="Hệ thống:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.btn_servo_on = tk.Button(ctrl_frame, text="SERVO ON", font=("Segoe UI", 9, "bold"), bg=self.accent_green, fg="white",
                                      width=12, command=self.servo_on, state="disabled")
        self.btn_servo_on.grid(row=0, column=1, padx=5, pady=5)
        
        self.btn_servo_off = tk.Button(ctrl_frame, text="SERVO OFF", font=("Segoe UI", 9, "bold"), bg=self.accent_red, fg="white",
                                       width=12, command=self.servo_off, state="disabled")
        self.btn_servo_off.grid(row=0, column=2, padx=5, pady=5)
        
        self.btn_reset_robot = tk.Button(ctrl_frame, text="RESET", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                                         width=8, command=self.reset_robot, state="disabled")
        self.btn_reset_robot.grid(row=0, column=3, padx=5, pady=5)
        
        self.btn_emg = tk.Button(ctrl_frame, text="EMG", font=("Segoe UI", 9, "bold"), bg=self.accent_red, fg="white",
                                 width=6, command=self.emergency_stop, state="disabled")
        self.btn_emg.grid(row=0, column=4, padx=5, pady=5)
        
        tk.Label(ctrl_frame, text="Trạng thái:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.lbl_servo_status = tk.Label(ctrl_frame, text="Servo: OFF", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.accent_gray)
        self.lbl_servo_status.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="w")
        
        tk.Label(ctrl_frame, text="Thả lỏng (Cầm tay):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        
        self.btn_teach_on = tk.Button(ctrl_frame, text="BẬT CHẾ ĐỘ CẦM TAY", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                                      command=lambda: self.toggle_teach_mode(True), state="disabled")
        self.btn_teach_on.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="we")
        
        self.btn_teach_off = tk.Button(ctrl_frame, text="TẮT (KHÓA LẠI)", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                                       command=lambda: self.toggle_teach_mode(False), state="disabled")
        self.btn_teach_off.grid(row=2, column=3, columnspan=2, padx=5, pady=5, sticky="we")
        
        tk.Label(ctrl_frame, text="Chế độ Jog:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.jog_mode = tk.StringVar(value="joint")
        self.rad_joint = tk.Radiobutton(ctrl_frame, text="Khớp (Joint)", variable=self.jog_mode, value="joint", bg=self.card_color, fg=self.text_color, selectcolor=self.bg_color, font=("Segoe UI", 9), command=self.on_jog_mode_change)
        self.rad_joint.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.rad_task = tk.Radiobutton(ctrl_frame, text="Tọa độ (Task)", variable=self.jog_mode, value="task", bg=self.card_color, fg=self.text_color, selectcolor=self.bg_color, font=("Segoe UI", 9), command=self.on_jog_mode_change)
        self.rad_task.grid(row=3, column=2, padx=5, pady=5, sticky="w")

        self.rad_cont = tk.Radiobutton(ctrl_frame, text="Liên tục (Hold)", variable=self.jog_type, value="continuous", bg=self.card_color, fg=self.text_color, selectcolor=self.bg_color, font=("Segoe UI", 9, "bold"))
        self.rad_cont.grid(row=3, column=3, padx=5, pady=5, sticky="w")
        self.rad_step = tk.Radiobutton(ctrl_frame, text="Bước ngắn (Step)", variable=self.jog_type, value="step", bg=self.card_color, fg=self.text_color, selectcolor=self.bg_color, font=("Segoe UI", 9))
        self.rad_step.grid(row=3, column=4, padx=5, pady=5, sticky="w")
        
        self.lbl_joint_select = tk.Label(ctrl_frame, text="Chọn Khớp:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9))
        self.lbl_joint_select.grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.joint_select_menu = ttk.Combobox(ctrl_frame, textvariable=self.selected_joint, values=["J1", "J2", "J3", "J4", "J5", "J6"], width=5, state="readonly")
        self.joint_select_menu.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        self.joint_select_menu.bind("<<ComboboxSelected>>", self.on_joint_select_change)
        
        self.lbl_max_step = tk.Label(ctrl_frame, text="Góc/Bước (độ/mm):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9))
        self.lbl_max_step.grid(row=4, column=2, padx=5, pady=5, sticky="e")
        self.step_entry = tk.Entry(ctrl_frame, textvariable=self.step_size, width=8, font=("Segoe UI", 9), bg="#1e1e24", fg="#ffffff", insertbackground="white")
        self.step_entry.grid(row=4, column=3, padx=5, pady=5, sticky="w")
        
        tk.Label(ctrl_frame, text="Điều hướng Jog:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=5, column=0, padx=10, pady=5, sticky="w")
        
        self.btn_jog_neg = tk.Button(ctrl_frame, text="◀ JOG -", font=("Segoe UI", 10, "bold"), bg="#f39c12", fg="white", width=12, activebackground="#e67e22")
        self.btn_jog_neg.grid(row=5, column=1, columnspan=2, padx=5, pady=5, sticky="we")
        self.btn_jog_neg.bind("<ButtonPress-1>", lambda e: self.on_jog_press(-1))
        self.btn_jog_neg.bind("<ButtonRelease-1>", self.on_jog_release)
        self.btn_jog_neg.config(state="disabled")
        
        self.btn_jog_pos = tk.Button(ctrl_frame, text="JOG + ▶", font=("Segoe UI", 10, "bold"), bg="#f39c12", fg="white", width=12, activebackground="#e67e22")
        self.btn_jog_pos.grid(row=5, column=3, columnspan=2, padx=5, pady=5, sticky="we")
        self.btn_jog_pos.bind("<ButtonPress-1>", lambda e: self.on_jog_press(1))
        self.btn_jog_pos.bind("<ButtonRelease-1>", self.on_jog_release)
        self.btn_jog_pos.config(state="disabled")

        self.bind_all("<ButtonRelease-1>", self._on_global_button_release, add="+")
        
        tk.Label(ctrl_frame, text="Tốc độ (mm/s):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=6, column=0, padx=10, pady=5, sticky="w")
        self.speed_slider = tk.Scale(ctrl_frame, from_=50, to=900, resolution=10, orient="horizontal", bg=self.card_color, fg=self.text_color,
                                     highlightbackground=self.card_color, troughcolor=self.accent_gray, activebackground=self.accent_blue)
        self.speed_slider.set(200)
        self.speed_slider.bind("<ButtonRelease-1>", lambda e: self.update_speed(self.speed_slider.get()))
        self.speed_slider.grid(row=6, column=1, columnspan=3, padx=5, pady=5, sticky="we")
        
        self.btn_apply_all_speed = tk.Button(ctrl_frame, text="Áp Dụng Hết", font=("Segoe UI", 8, "bold"), bg=self.accent_blue, fg="white",
                                             command=self.apply_general_speed_to_all, state="disabled")
        self.btn_apply_all_speed.grid(row=6, column=4, padx=5, pady=5, sticky="we")

        tk.Label(ctrl_frame, text="Nhạy va chạm:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=7, column=0, padx=10, pady=5, sticky="w")
        self.collision_combo = ttk.Combobox(
            ctrl_frame,
            textvariable=self.collision_level_var,
            values=[
                "1 - Rộng nhất (Khuyên dùng)",
                "2 - Tiêu chuẩn",
                "3 - Trung bình",
                "4 - Nhạy",
                "5 - Rất nhạy"
            ],
            width=25,
            state="readonly"
        )
        self.collision_combo.grid(row=7, column=1, columnspan=4, padx=5, pady=5, sticky="we")
        self.collision_combo.bind("<<ComboboxSelected>>", self.on_collision_level_change)

        # 6. DIGITAL OUTPUT PANEL (Gripper)
        do_frame = tk.LabelFrame(self.left_frame, text=" Digital I/O (Gripper) ", font=("Segoe UI", 10, "bold"),
                                bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        do_frame.pack(padx=20, fill="x", pady=5)
        
        tk.Label(do_frame, text="DO 0 (Kẹp):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.btn_do_on = tk.Button(do_frame, text="BẬT (ON)", font=("Segoe UI", 9, "bold"), bg=self.accent_green, fg="white",
                                   width=10, command=lambda: self.set_gripper_io(0, True), state="disabled")
        self.btn_do_on.grid(row=0, column=1, padx=5, pady=5)
        
        self.btn_do_off = tk.Button(do_frame, text="TẮT (OFF)", font=("Segoe UI", 9, "bold"), bg=self.accent_red, fg="white",
                                    width=10, command=lambda: self.set_gripper_io(0, False), state="disabled")
        self.btn_do_off.grid(row=0, column=2, padx=5, pady=5)

        # 7. CẢNH BÁO GIỚI HẠN KHỚP (RIGHT FRAME) - Dạng 2 cột tiết kiệm chiều cao màn hình Laptop
        limit_frame = tk.LabelFrame(self.right_frame, text=" Cảnh báo Giới hạn khớp ", font=("Segoe UI", 10, "bold"),
                                    bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        limit_frame.pack(fill="x", pady=5)

        col0_frame = tk.Frame(limit_frame, bg=self.card_color)
        col0_frame.pack(side="left", fill="both", expand=True, padx=5, pady=2)

        col1_frame = tk.Frame(limit_frame, bg=self.card_color)
        col1_frame.pack(side="right", fill="both", expand=True, padx=5, pady=2)

        for i in range(6):
            target_col = col0_frame if i < 3 else col1_frame
            lbl_title = tk.Label(target_col, text=f"J{i+1}: 0.00° ({self.joint_limits[i][0]}° ~ {self.joint_limits[i][1]}°)",
                                 font=("Segoe UI", 8, "bold"), bg=self.card_color, fg=self.text_color)
            lbl_title.pack(anchor="w", padx=5, pady=(2, 0))
            self.limit_labels.append(lbl_title)

            canvas = tk.Canvas(target_col, height=18, bg=self.card_color, highlightthickness=0)
            canvas.pack(fill="x", padx=5, pady=(0, 2))

            canvas.create_rectangle(10, 7, 210, 11, fill="#34495e", outline="", tags="bg_bar")

            pointer = canvas.create_oval(104, 3, 116, 15, fill=self.accent_green, outline="#ffffff", width=1.5)
            self.limit_pointers.append(pointer)
            self.limit_fill_rects.append(None)

            self.limit_canvases.append(canvas)

        # 8. LƯU ĐIỂM & CHẠY CHU TRÌNH
        points_frame = tk.LabelFrame(self.right_frame, text=" Chu trình Robot (Lưu Điểm & Chạy) ", font=("Segoe UI", 10, "bold"),
                                     bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        points_frame.pack(fill="both", expand=True, pady=5)
        
        self.target_listbox = tk.Listbox(points_frame, bg="#1e1e24", fg="#ffffff", selectbackground=self.accent_blue,
                                         selectforeground="white", font=("Segoe UI", 9), bd=0, selectmode=tk.EXTENDED)
        self.target_listbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        btn_grid_frame = tk.Frame(points_frame, bg=self.card_color)
        btn_grid_frame.pack(fill="x", padx=10, pady=5)
        
        self.motion_type = tk.StringVar(value="MoveJ")
        self.motion_menu = ttk.Combobox(btn_grid_frame, textvariable=self.motion_type, values=["MoveJ", "MoveL"], width=7, state="readonly")
        self.motion_menu.grid(row=0, column=0, padx=2, pady=2)
        
        self.btn_save_point = tk.Button(btn_grid_frame, text="Lưu Điểm", font=("Segoe UI", 9, "bold"), bg=self.accent_green, fg="white",
                                        command=self.save_current_target, state="disabled")
        self.btn_save_point.grid(row=0, column=1, padx=2, pady=2, sticky="we")
        
        self.btn_update_point = tk.Button(btn_grid_frame, text="Sửa Điểm", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                                          command=self.update_selected_target, state="disabled")
        self.btn_update_point.grid(row=0, column=2, padx=2, pady=2, sticky="we")
        
        self.btn_delete_point = tk.Button(btn_grid_frame, text="Xóa Điểm", font=("Segoe UI", 9, "bold"), bg=self.accent_red, fg="white",
                                          command=self.delete_selected_target, state="disabled")
        self.btn_delete_point.grid(row=0, column=3, padx=2, pady=2, sticky="we")
        
        self.btn_move_to_point = tk.Button(btn_grid_frame, text="Đi Tới Điểm", font=("Segoe UI", 9, "bold"), bg="#8e44ad", fg="white",
                                           command=self.move_to_selected_target, state="disabled")
        self.btn_move_to_point.grid(row=0, column=4, padx=2, pady=2, sticky="we")
        
        self.btn_clear_points = tk.Button(btn_grid_frame, text="Xóa Hết", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                                          command=self.clear_all_targets, state="disabled")
        self.btn_clear_points.grid(row=0, column=5, padx=2, pady=2, sticky="we")
        
        self.btn_run_cycle = tk.Button(btn_grid_frame, text="Chạy Chu Trình", font=("Segoe UI", 9, "bold"), bg=self.accent_blue, fg="white",
                                       command=self.run_cycle, state="disabled")
        self.btn_run_cycle.grid(row=0, column=6, padx=2, pady=2, sticky="we")
        
        # Thêm thanh tốc độ chạy điểm riêng biệt
        tk.Label(btn_grid_frame, text="Tốc độ điểm (mm/s):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=1, column=0, padx=2, pady=2, sticky="w")
        self.point_speed_slider = tk.Scale(btn_grid_frame, from_=50, to=900, resolution=10, orient="horizontal", bg=self.card_color, fg=self.text_color,
                                           highlightbackground=self.card_color, troughcolor=self.accent_gray, activebackground=self.accent_blue)
        self.point_speed_slider.set(200)
        self.point_speed_slider.grid(row=1, column=1, columnspan=6, padx=2, pady=2, sticky="we")

        # Cấu hình Vùng bo góc (Fillet) cho từng điểm cụ thể
        fillet_ctrl_frame = tk.Frame(btn_grid_frame, bg=self.card_color)
        fillet_ctrl_frame.grid(row=2, column=0, columnspan=7, padx=2, pady=3, sticky="we")

        self.use_fillet_var = tk.BooleanVar(value=True)
        self.chk_fillet = tk.Checkbutton(fillet_ctrl_frame, text="Tự Động Bo Góc (Fillet)", variable=self.use_fillet_var,
                                         font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.accent_green, selectcolor="#1e1e24")
        self.chk_fillet.pack(side="left", padx=5)

        self.btn_apply_zone = tk.Button(fillet_ctrl_frame, text="* BẬT / TẮT Fillet Cho Các Điểm Chọn (Ctrl/Shift)", font=("Segoe UI", 9, "bold"),
                                        bg=self.accent_blue, fg="white", command=self.apply_zone_to_selected_targets)
        self.btn_apply_zone.pack(side="left", padx=8)
        
        self.btn_stop_cycle = tk.Button(points_frame, text="DỪNG CHU TRÌNH", font=("Segoe UI", 10, "bold"), bg=self.accent_red, fg="white",
                                        command=self.stop_cycle, state="disabled")
        self.btn_stop_cycle.pack(fill="x", padx=10, pady=2)
        
        file_actions_frame = tk.Frame(points_frame, bg=self.card_color)
        file_actions_frame.pack(fill="x", padx=10, pady=5)
        
        btn_export = tk.Button(file_actions_frame, text="💾 Lưu File Điểm (.json / .csv)", font=("Segoe UI", 9, "bold"), bg="#27ae60", fg="white",
                               command=self.export_targets)
        btn_export.pack(side="left", fill="x", expand=True, padx=2)
        
        btn_import = tk.Button(file_actions_frame, text="📂 Tải File Điểm (.json / .csv)", font=("Segoe UI", 9, "bold"), bg="#2980b9", fg="white",
                               command=self.import_targets)
        btn_import.pack(side="right", fill="x", expand=True, padx=2)

        # Nút Calib Gốc Zero Encoder
        calib_zero_frame = tk.Frame(points_frame, bg=self.card_color)
        calib_zero_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.btn_calib_zero = tk.Button(calib_zero_frame, text="🎯 Calib Gốc Zero Encoder (Reset Joint Home)", font=("Segoe UI", 9, "bold"),
                                        bg="#d35400", fg="white", command=self.calib_zero_encoder, state="disabled")
        self.btn_calib_zero.pack(fill="x", padx=2)

    def auto_detect_neuromeka_ip(self):
        """Tự động tìm IP của Robot Neuromeka trong mạng dựa trên địa chỉ MAC của hãng (00-e0-4c-68-04-78)."""
        import subprocess, re
        self.btn_auto_ip.config(state="disabled", text="Đang dò...")

        def run_scan():
            detected_ip = None
            error = None
            try:
                out = subprocess.check_output("arp -a", shell=True, timeout=2.0).decode('utf-8', errors='ignore')
                for line in out.splitlines():
                    if "00-e0-4c-68-04-78" in line.lower() or "00:e0:4c:68:04:78" in line.lower():
                        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if match:
                            detected_ip = match.group(1)
                            break
            except Exception as exc:
                error = exc

            def finish_scan():
                self.btn_auto_ip.config(state="normal", text="🔍 Dò IP")
                if detected_ip:
                    self.ip_entry.delete(0, tk.END)
                    self.ip_entry.insert(0, detected_ip)
                    messagebox.showinfo("Dò IP Tự Động", f"Đã phát hiện IP Robot: {detected_ip}")
                else:
                    if error:
                        print(f"Lỗi dò IP tự động: {error}")
                    messagebox.showwarning(
                        "Dò IP Tự Động",
                        "Không tìm thấy thiết bị Robot Neuromeka trong bảng ARP hiện tại."
                    )

            self._post_ui(finish_scan)

        threading.Thread(target=run_scan, daemon=True, name=f"{self.panel_name}-arp").start()

    def connect_robot(self):
        ip = self.ip_entry.get().strip()
        self.btn_connect.config(state="disabled", text="Connecting...")
        
        def run_conn():
            nonlocal ip
            try:
                self.indy = UnifiedIndyClient(ip)
                if not self.indy.connect():
                    try:
                        import subprocess, re
                        out = subprocess.check_output("arp -a", shell=True, timeout=2.0).decode('utf-8', errors='ignore')
                        for line in out.splitlines():
                            if "00-e0-4c-68-04-78" in line.lower() or "00:e0:4c:68:04:78" in line.lower():
                                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                                if m and m.group(1) != ip:
                                    detected = m.group(1)
                                    print(f"Tự động phát hiện IP mới: {detected}, thử kết nối lại...")
                                    ip = detected
                                    self._post_ui(lambda d=detected: (self.ip_entry.delete(0, tk.END), self.ip_entry.insert(0, d)))
                                    self.indy = UnifiedIndyClient(ip)
                                    self.indy.connect()
                                    break
                    except Exception:
                        pass

                if self.indy and self.indy.client:
                    self.is_connected = True
                    try:
                        self.servo_on()
                        self.indy.set_collision_level(2)
                    except Exception:
                        pass
                    def ui_success():
                        self.lbl_status.config(text=f"CONNECTED (v{self.indy.version})", fg=self.accent_green)
                        self.btn_connect.config(state="disabled", text="Connected")
                        self.btn_disconnect.config(state="normal", bg=self.accent_red)
                        self.btn_servo_on.config(state="normal")
                        self.btn_servo_off.config(state="normal")
                        self.btn_reset_robot.config(state="normal")
                        self.btn_jog_neg.config(state="normal")
                        self.btn_jog_pos.config(state="normal")
                        self.btn_save_point.config(state="normal")
                        self.btn_update_point.config(state="normal")
                        self.btn_run_cycle.config(state="normal")
                        self.btn_stop_cycle.config(state="normal")
                        self.btn_do_on.config(state="normal")
                        self.btn_do_off.config(state="normal")
                        self.btn_teach_on.config(state="normal")
                        self.btn_teach_off.config(state="normal")
                        self.btn_emg.config(state="normal")
                        self.btn_clear_points.config(state="normal")
                        self.btn_calib_zero.config(state="normal")
                        self.btn_delete_point.config(state="normal")
                        self.point_speed_slider.config(state="normal")
                        self.btn_move_to_point.config(state="normal")
                        self.btn_apply_all_speed.config(state="normal")
                        self.btn_tcp_calib.config(state="normal")
                        self.btn_ref_frame_calib.config(state="normal")
                        
                        self.update_speed(self.speed_slider.get())
                    self._post_ui(ui_success)
                else:
                    self.is_connected = False
                    def ui_fail():
                        messagebox.showerror("Lỗi kết nối", f"Không thể kết nối tới Robot tại IP: {ip}\n(Vui lòng kiểm tra dây mạng và địa chỉ IP)")
                        self.btn_connect.config(state="normal", text="Connect")
                    self._post_ui(ui_fail)
            except Exception as e:
                self.is_connected = False
                def ui_err(e=e):
                    messagebox.showerror("Lỗi hệ thống", f"Đã xảy ra lỗi: {e}")
                    self.btn_connect.config(state="normal", text="Connect")
                self._post_ui(ui_err)
                
        threading.Thread(target=run_conn, daemon=True).start()

    def destroy_panel(self):
        self.running = False
        self._ui_dispatcher_closed = True
        self.disconnect_robot()

    def disconnect_robot(self):
        self.on_jog_release()
        self.is_connected = False
        self.cycle_running = False
        client = self.indy
        self.indy = None
        
        def run_disconn():
            if client:
                try:
                    client.stop_motion()
                except Exception:
                    pass
                try:
                    client.set_servo([False] * 6)
                except Exception:
                    pass
                try:
                    client.disconnect()
                except Exception:
                    pass
            
            def ui_reset():
                self.lbl_status.config(text="DISCONNECTED", fg=self.accent_red)
                self.lbl_servo_status.config(text="Servo: OFF", fg=self.accent_gray)
                
                # Reset badges
                self.badge_ready.config(text="READY: NO", bg=self.accent_gray)
                self.badge_emg.config(text="EMG: NORMAL", bg=self.accent_gray)
                self.badge_col.config(text="COLLISION: NO", bg=self.accent_gray)
                self.badge_err.config(text="ERROR: NO", bg=self.accent_gray)
                
                self.btn_connect.config(state="normal", text="Connect")
                self.btn_disconnect.config(state="disabled", bg=self.accent_gray)
                self.btn_servo_on.config(state="disabled")
                self.btn_servo_off.config(state="disabled")
                self.btn_reset_robot.config(state="disabled")
                self.btn_jog_neg.config(state="disabled")
                self.btn_jog_pos.config(state="disabled")
                self.btn_save_point.config(state="disabled")
                self.btn_update_point.config(state="disabled")
                self.btn_run_cycle.config(state="disabled")
                self.btn_stop_cycle.config(state="disabled")
                self.btn_do_on.config(state="disabled")
                self.btn_do_off.config(state="disabled")
                self.btn_teach_on.config(state="disabled")
                self.btn_teach_off.config(state="disabled")
                self.btn_emg.config(state="disabled")
                self.btn_tcp_calib.config(state="disabled")
                self.btn_ref_frame_calib.config(state="disabled")
                self.btn_calib_zero.config(state="disabled")
                
                # Reset nhãn hiển thị góc khớp
                for i in range(6):
                    self.angle_labels[i].config(text=f"J{i+1}: 0.00°")
                for i in range(6):
                    unit = "mm" if i < 3 else "°"
                    tcp_names = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
                    self.tcp_labels[i].config(text=f"{tcp_names[i]}: 0.00 {unit}")
            self._post_ui(ui_reset)
                
        threading.Thread(target=run_disconn, daemon=True).start()

    def servo_on(self):
        if not self.is_connected or not self.indy:
            return
        def run():
            try:
                self.indy.set_servo([True] * 6)
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi", f"Không thể bật Servo: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def servo_off(self):
        self.cycle_running = False
        if not self.is_connected or not self.indy:
            return
        def run():
            try:
                self.indy.stop_motion()
                self.indy.set_servo([False] * 6)
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi", f"Không thể tắt Servo: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def reset_robot(self):
        if not self.is_connected or not self.indy:
            return
        def run():
            try:
                self.indy.reset_robot()
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi", f"Không thể Reset Robot: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def calib_zero_encoder(self):
        if not self.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối!")
            return
        answer = messagebox.askyesno("Xác Nhận Calib Zero Encoder",
                                     "⚠️ CẢNH BÁO AN TOÀN:\n\n"
                                     "Thao tác này sẽ thiết lập vị trí hiện tại của Robot làm GỐC CHUẨN (0° cho cả 6 khớp).\n\n"
                                     "Vui lòng đảm bảo Robot đang ở tư thế thẳng đứng gốc chuẩn cơ khí trước khi thực hiện.\n\n"
                                     "Bạn có chắc chắn muốn thiết lập lại Gốc Zero Encoder không?")
        if answer:
            client = self.indy
            self.btn_calib_zero.config(state="disabled")

            def run_calibration():
                success = client.set_home_zero() if client else False

                def finish_calibration():
                    self.btn_calib_zero.config(state="normal" if self.is_connected else "disabled")
                    if success:
                        messagebox.showinfo("Thành công", f"Đã lưu Gốc Zero Encoder cho {self.robot_name}!")
                    else:
                        messagebox.showerror("Lỗi", "Controller không chấp nhận lệnh reset Gốc Zero Encoder!")

                self._post_ui(finish_calibration)

            threading.Thread(
                target=run_calibration,
                daemon=True,
                name=f"{self.panel_name}-calib-zero"
            ).start()

    def emergency_stop(self):
        if not self.is_connected or not self.indy:
            return
        self.cycle_running = False
        def run():
            try:
                self.indy.emergency_stop()
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi", f"Lỗi dừng khẩn cấp: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def toggle_teach_mode(self, enabled):
        if not self.is_connected or not self.indy:
            return
        def run():
            try:
                if enabled:
                    self.indy.set_servo([True] * 6)
                    time.sleep(0.15)
                res = self.indy.set_direct_teaching(enabled)
                def ui_update():
                    if enabled:
                        self.lbl_servo_status.config(text="Cầm Tay: BẬT", fg=self.accent_orange)
                        messagebox.showinfo("Thành công", f"Đã BẬT Chế độ Cầm tay cho {self.robot_name}!\n\nBạn có thể di chuyển Robot đến vị trí mong muốn.")
                    else:
                        self.lbl_servo_status.config(text="Servo: ON", fg=self.accent_green)
                        messagebox.showinfo("Thành công", f"Đã TẮT Chế độ Cầm tay (Khóa vị trí) cho {self.robot_name}.")
                self._post_ui(ui_update)
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi", f"Lỗi chuyển Chế độ Cầm tay: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def update_speed(self, val):
        if not self.is_connected or not self.indy:
            return
        # Coalesce nhiều thay đổi slider: tại mọi thời điểm chỉ có một worker
        # gửi tốc độ, giá trị mới nhất sẽ thay thế giá trị cũ chưa gửi.
        try:
            speed_val = float(val)
        except Exception:
            speed_val = 200.0

        with self._speed_lock:
            self._speed_pending = speed_val
            if self._speed_worker_running:
                return
            self._speed_worker_running = True

        def run_speed_worker():
            try:
                while self.running:
                    with self._speed_lock:
                        pending = self._speed_pending
                        self._speed_pending = None
                    if pending is None:
                        break
                    self._apply_speed_now(pending)
            finally:
                with self._speed_lock:
                    self._speed_worker_running = False
                    restart = self._speed_pending is not None and self.running
                if restart:
                    self.update_speed(self._speed_pending)

        threading.Thread(target=run_speed_worker, daemon=True, name=f"{self.panel_name}-speed").start()

    def _apply_speed_now(self, speed_val):
        if not self.is_connected or not self.indy:
            return False
        speed_level = 1.0 + (float(speed_val) - 50.0) * 8.0 / 850.0
        speed_level = max(1, min(9, int(round(speed_level))))
        try:
            self.indy.set_joint_vel_level(speed_level)
            self.indy.set_task_vel_level(speed_level)
            return True
        except Exception as e:
            print(f"Lỗi đặt tốc độ: {e}")
            return False

    def set_gripper_io(self, pin, state):
        if not self.is_connected or not self.indy:
            return
        def run():
            try:
                self.indy.set_digital_output(pin, state)
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi Gripper", f"Không thể bật/tắt thiết bị kẹp: {e}")
                self._post_ui(ui_err)
        threading.Thread(target=run, daemon=True).start()

    def on_collision_level_change(self, event=None):
        if not self.is_connected or not self.indy:
            return
        text = self.collision_level_var.get()
        try:
            level = int(text.split()[0])
        except Exception:
            level = 1
        def run():
            try:
                self.indy.set_collision_level(level)
                print(f"Đã cập nhật Độ nhạy va chạm -> Mức {level}")
            except Exception as e:
                print(f"Lỗi set collision level: {e}")
        threading.Thread(target=run, daemon=True, name=f"{self.panel_name}-col-lvl").start()

    def on_jog_press(self, direction):
        if not self.is_connected or not self.indy:
            return

        # Chỉ dùng cache để UI thread không bao giờ chờ socket.
        cached = getattr(self, 'status_cache', {})
        if (cached.get('emergency', 0) == 1 or cached.get('error', 0) == 1
                or cached.get('collision', 0) == 1):
            messagebox.showwarning(
                "Cảnh báo Jog",
                "Robot đang Lỗi/EMG/Collision. Hãy xử lý nguyên nhân và RESET trước khi Jog."
            )
            return
        if cached.get('ready', 0) != 1:
            messagebox.showwarning(
                "Cảnh báo Jog",
                "Robot chưa READY. Hãy bật SERVO và tắt chế độ Cầm tay trước khi Jog."
            )
            return

        # Visual Feedback phản hồi thị giác tức thì khi nhấn
        if direction < 0:
            self.btn_jog_neg.config(bg="#e67e22", relief="sunken")
        else:
            self.btn_jog_pos.config(bg="#e67e22", relief="sunken")

        jog_type = getattr(self, 'jog_type', None)
        is_continuous = (jog_type is None or jog_type.get() == "continuous")

        if not is_continuous:
            self.start_jog_step(direction)
            return

        with self._jog_lock:
            if self.jog_holding:
                return
            self._jog_generation += 1
            generation = self._jog_generation
            self._jog_stop_event = threading.Event()
            stop_event = self._jog_stop_event
            self.jog_holding = True
            self.jog_direction = direction
            self.jog_active = True

        mode = self.jog_mode.get()
        val_str = self.selected_joint.get()

        try:
            speed = float(self.speed_slider.get())
        except Exception:
            speed = 200.0

        def run_continuous_stream():
            failure_message = None
            try:
                self._apply_speed_now(speed)
                time.sleep(0.02)

                delta = [0.0] * 6
                if mode == "joint":
                    labels = ["J1", "J2", "J3", "J4", "J5", "J6"]
                    idx = labels.index(val_str) if val_str in labels else 0
                    min_lim, max_lim = self.joint_limits[idx]

                    # Đọc góc hiện tại để tính delta tới sát biên giới hạn
                    cur_angles = self.indy.get_joint_pos()
                    cur_q = cur_angles[idx] if (cur_angles and len(cur_angles) > idx) else 0.0

                    if direction > 0:
                        target_dist = min(30.0, max(0.0, max_lim - 1.5 - cur_q))
                    else:
                        target_dist = max(-30.0, min(0.0, min_lim + 1.5 - cur_q))

                    if abs(target_dist) < 0.2:
                        failure_message = f"Khớp {val_str} đã ở sát giới hạn hành trình ({cur_q:.2f}°)."
                        return

                    delta[idx] = target_dist
                    accepted = self.indy.joint_move_by(delta)
                else:
                    labels = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
                    idx = labels.index(val_str) if val_str in labels else 0

                    if idx < 3:
                        target_dist = 0.20 * (1.0 if direction > 0 else -1.0)  # 0.2m = 200mm (Tối đa 200mm)
                    else:
                        target_dist = 30.0 * (1.0 if direction > 0 else -1.0)  # Tối đa 30 độ

                    delta[idx] = target_dist
                    accepted = self.indy.task_move_by(delta)

                if not accepted:
                    failure_message = "Controller từ chối lệnh Jog. Kiểm tra READY và giới hạn."
                    return

                # Duy trì 100% chuyển động liên tục (1 hình thang duy nhất) trong suốt thời gian nhấn giữ
                while (not stop_event.is_set() and self.is_connected
                       and self.indy and generation == self._jog_generation):
                    stop_event.wait(0.05)
                    st = self.indy.get_robot_status()
                    if isinstance(st, dict):
                        self.status_cache = st
                        self.status_cache_time = time.monotonic()
                        if st.get('emergency', 0) == 1 or st.get('error', 0) == 1 or st.get('collision', 0) == 1:
                            failure_message = "Jog dừng vì Controller báo Lỗi/EMG/Collision."
                            break

            except Exception as e:
                print(f"Lỗi continuous jog: {e}")
                failure_message = f"Lỗi truyền thông khi Jog: {e}"
            finally:
                with self._jog_lock:
                    if generation == self._jog_generation:
                        self.jog_holding = False
                        self.jog_active = False
                if failure_message and not stop_event.is_set() and self.running:
                    self._post_ui(lambda msg=failure_message: messagebox.showwarning("Jog đã dừng", msg))

        self.jog_thread = threading.Thread(
            target=run_continuous_stream,
            daemon=True,
            name=f"{self.panel_name}-jog"
        )
        self.jog_thread.start()

    def on_jog_release(self, event=None):
        """Dừng Jog Hold. Jog Step không bị tự hủy bởi ButtonRelease."""
        try:
            self.btn_jog_neg.config(bg="#f39c12", relief="raised")
            self.btn_jog_pos.config(bg="#f39c12", relief="raised")
        except Exception:
            pass

        if self.jog_type.get() != "continuous":
            return

        with self._jog_lock:
            was_holding = self.jog_holding
            self.jog_holding = False
            self.jog_active = False
            self._jog_generation += 1
            self._jog_stop_event.set()
            client = self.indy

        if was_holding and client:
            def run_stop():
                try:
                    client.stop_motion_light()
                except Exception as exc:
                    print(f"Lỗi dừng Jog: {exc}")

            threading.Thread(
                target=run_stop,
                daemon=True,
                name=f"{self.panel_name}-jog-stop"
            ).start()

    def _on_jog_pointer_leave(self, event=None):
        if self.jog_holding:
            self.on_jog_release(event)

    def _on_global_button_release(self, event=None):
        if self.jog_holding:
            self.on_jog_release(event)

    def start_jog_step(self, direction):
        if not self.is_connected or not self.indy or self.jog_active:
            return

        self.jog_active = True
        mode = self.jog_mode.get()
        val_str = self.selected_joint.get()

        try:
            speed = float(self.speed_slider.get())
        except Exception:
            speed = 200.0

        try:
            raw_step = str(self.step_size.get()).replace("'", "").replace('"', '').strip()
            step = float(raw_step)
        except Exception:
            step = 1.0
        delta = build_jog_delta(mode, val_str, direction, speed=speed, step_size=step)

        def run_step():
            try:
                self._apply_speed_now(speed)
                if mode == "joint":
                    accepted = self.indy.joint_move_by(delta)
                elif mode == "task":
                    accepted = self.indy.task_move_by(delta)
                else:
                    accepted = False
                if not accepted:
                    raise RuntimeError("Controller từ chối lệnh (Robot chưa READY hoặc bước vượt giới hạn).")
            except Exception as e:
                def ui_err(e=e): messagebox.showerror("Lỗi Jog Step", f"Nhích bước Jog thất bại: {e}")
                self._post_ui(ui_err)
            finally:
                self.jog_active = False

        threading.Thread(
            target=run_step,
            daemon=True,
            name=f"{self.panel_name}-jog-step"
        ).start()

    def start_jog(self, direction):
        """Hàm duy trì tương thích backward compatibility"""
        self.on_jog_press(direction)

    def on_jog_mode_change(self):
        mode = self.jog_mode.get()
        if mode == "joint":
            self.lbl_joint_select.config(text="Chọn Khớp:")
            self.joint_select_menu.config(values=["J1", "J2", "J3", "J4", "J5", "J6"])
            self.selected_joint.set("J1")
        else:
            self.lbl_joint_select.config(text="Chọn Trục:")
            self.joint_select_menu.config(values=["X", "Y", "Z", "Rx", "Ry", "Rz"])
            self.selected_joint.set("X")
        self.on_joint_select_change()

    def on_joint_select_change(self, event=None):
        mode = self.jog_mode.get()
        val_str = self.selected_joint.get()
        if mode == "joint":
            self.lbl_max_step.config(text="Góc/Bước (độ/mm):")
        else:
            if val_str in ["X", "Y", "Z"]:
                self.lbl_max_step.config(text="Góc/Bước (độ/mm):")
            else:
                self.lbl_max_step.config(text="Góc/Bước (độ/mm):")

    def stop_jog(self):
        self.on_jog_release()

    def save_target(self):
        self.save_current_target()

    @staticmethod
    def _format_target_label(index, target):
        mtype = target['type']
        speed = target.get('speed', 200)
        zone = target.get('zone', "fine (0mm)")
        label = f"[{mtype}] P{index}: "
        if mtype == "MoveJ":
            label += "J[" + ", ".join([f"{a:.1f}" for a in target['joint'][:3]]) + "...]"
        else:
            label += "T[" + ", ".join([f"{x * 1000.0:.1f}" for x in target['tcp'][:3]]) + "...]"
        return label + f" - V:{speed:.0f}mm/s [{zone}]"

    def _auto_save_targets(self):
        """Tự động lưu danh sách điểm dạy ra file JSON và CSV để không bao giờ bị mất khi tắt app."""
        try:
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(cur_dir, "taught_points.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.saved_targets, f, indent=2, ensure_ascii=False)
            csv_path = os.path.join(cur_dir, "targets_custom.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Type", "J1", "J2", "J3", "J4", "J5", "J6", "X", "Y", "Z", "Rx", "Ry", "Rz", "Speed", "Fillet", "Radius"])
                for t in self.saved_targets:
                    fillet_str = "1" if t.get('fillet', False) else "0"
                    radius_val = t.get('radius', 0.0)
                    writer.writerow([t['type']] + t['joint'] + t['tcp'] + [t.get('speed', 200), fillet_str, radius_val])
        except Exception as e:
            print(f"Lỗi _auto_save_targets: {e}")

    def _auto_load_targets(self):
        """Tự động nạp lại danh sách điểm dạy từ file JSON khi khởi động app."""
        try:
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(cur_dir, "taught_points.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    self.saved_targets = json.load(f)
                if hasattr(self, 'target_listbox'):
                    self.target_listbox.delete(0, tk.END)
                    for idx, t in enumerate(self.saved_targets):
                        self.target_listbox.insert(
                            tk.END, self._format_target_label(idx + 1, t)
                        )
                print(f"✓ Đã tự động nạp {len(self.saved_targets)} điểm dạy từ {json_path}")
        except Exception as e:
            print(f"Lỗi _auto_load_targets: {e}")

    def save_current_target(self):
        if not self.is_connected or not self.indy:
            return
        client = self.indy
        mtype = self.motion_type.get()
        speed = float(self.point_speed_slider.get())
        is_fillet = bool(self.use_fillet_var.get())
        self.btn_save_point.config(state="disabled")

        def read_position():
            try:
                angles = client.get_joint_pos()
                tcp = client.get_task_pos()
                target = {
                    'type': mtype,
                    'joint': angles,
                    'tcp': tcp,
                    'speed': speed,
                    'fillet': is_fillet,
                    'radius': 10.0 if is_fillet else 0.0,
                    'zone': "z10 (10mm)" if is_fillet else "fine (0mm)"
                }

                def add_target():
                    self.saved_targets.append(target)
                    self._auto_save_targets()
                    self.target_listbox.insert(
                        tk.END, self._format_target_label(len(self.saved_targets), target)
                    )
                    self.btn_save_point.config(state="normal" if self.is_connected else "disabled")

                self._post_ui(add_target)
            except Exception as exc:
                def show_error(exc=exc):
                    self.btn_save_point.config(state="normal" if self.is_connected else "disabled")
                    messagebox.showerror("Lỗi", f"Không thể lấy vị trí hiện tại: {exc}")
                self._post_ui(show_error)

        threading.Thread(
            target=read_position,
            daemon=True,
            name=f"{self.panel_name}-save-point"
        ).start()

    def update_selected_target(self):
        if not self.is_connected or not self.indy:
            return
        selected = self.target_listbox.curselection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một điểm trong danh sách để sửa (ghi đè).")
            return
        idx = selected[0]
        client = self.indy
        mtype = self.motion_type.get()
        speed = float(self.point_speed_slider.get())
        is_fillet = bool(self.use_fillet_var.get())
        self.btn_update_point.config(state="disabled")

        def read_position():
            try:
                target = {
                    'type': mtype,
                    'joint': client.get_joint_pos(),
                    'tcp': client.get_task_pos(),
                    'speed': speed,
                    'fillet': is_fillet,
                    'radius': 10.0 if is_fillet else 0.0,
                    'zone': "z10 (10mm)" if is_fillet else "fine (0mm)"
                }

                def apply_update():
                    if idx < len(self.saved_targets):
                        self.saved_targets[idx] = target
                        self._auto_save_targets()
                        self.target_listbox.delete(idx)
                        self.target_listbox.insert(idx, self._format_target_label(idx + 1, target))
                        self.target_listbox.selection_set(idx)
                        messagebox.showinfo("Thông báo", f"Đã sửa điểm P{idx + 1} thành công.")
                    self.btn_update_point.config(state="normal" if self.is_connected else "disabled")

                self._post_ui(apply_update)
            except Exception as exc:
                def show_error(exc=exc):
                    self.btn_update_point.config(state="normal" if self.is_connected else "disabled")
                    messagebox.showerror("Lỗi", f"Không thể cập nhật điểm: {exc}")
                self._post_ui(show_error)

        threading.Thread(
            target=read_position,
            daemon=True,
            name=f"{self.panel_name}-update-point"
        ).start()

    def apply_zone_to_selected_targets(self):
        selected_indices = self.target_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn/phủ ít nhất một điểm trong danh sách (dùng phím Ctrl hoặc Shift) để cài đặt Fillet.")
            return

        is_fillet = self.use_fillet_var.get()
        radius = 10.0 if is_fillet else 0.0
        f_tag = "z10 (10mm)" if is_fillet else "fine (0mm)"

        for idx in selected_indices:
            if idx < len(self.saved_targets):
                self.saved_targets[idx]['fillet'] = is_fillet
                self.saved_targets[idx]['radius'] = radius
                self.saved_targets[idx]['zone'] = f_tag

                t = self.saved_targets[idx]
                mtype = t['type']
                speed = t.get('speed', 200)
                pt_name = f"[{mtype}] P{idx+1}: "
                if mtype == "MoveJ":
                    pt_name += "J[" + ", ".join([f"{a:.1f}" for a in t['joint'][:3]]) + "...]"
                else:
                    pt_name += "T[" + ", ".join([f"{x*1000.0:.1f}" for x in t['tcp'][:3]]) + "...]"
                pt_name += f" - V:{speed:.0f}mm/s [{f_tag}]"

                self.target_listbox.delete(idx)
                self.target_listbox.insert(idx, pt_name)

        # Giữ lại các vị trí được chọn
        for idx in selected_indices:
            self.target_listbox.selection_set(idx)

        self._auto_save_targets()
        messagebox.showinfo("Thành công", f"Đã cập nhật trạng thái [{f_tag}] cho {len(selected_indices)} điểm được chọn!")

    def delete_selected_target(self):
        selected = self.target_listbox.curselection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất một điểm trong danh sách để xóa.")
            return
        
        # Xóa các điểm được chọn từ cuối về đầu để tránh sai chỉ số index
        for idx in sorted(selected, reverse=True):
            if idx < len(self.saved_targets):
                self.saved_targets.pop(idx)
        
        self._auto_save_targets()
        # Làm mới lại danh sách
        self.target_listbox.delete(0, tk.END)
        for i, t in enumerate(self.saved_targets):
            mtype = t['type']
            speed = t.get('speed', 200)
            is_fillet = t.get('fillet', True)
            f_tag = "z10 (10mm)" if is_fillet else "fine (0mm)"
            pt_name = f"[{mtype}] P{i+1}: "
            if mtype == "MoveJ":
                pt_name += "J[" + ", ".join([f"{a:.1f}" for a in t['joint'][:3]]) + "...]"
            else:
                pt_name += "T[" + ", ".join([f"{x*1000.0:.1f}" for x in t['tcp'][:3]]) + "...]"
            pt_name += f" - V:{speed:.0f}mm/s [{f_tag}]"
            self.target_listbox.insert(tk.END, pt_name)
        messagebox.showinfo("Thông báo", f"Đã xóa {len(selected)} điểm và tự động cập nhật lại số thứ tự P1, P2...")

    def clear_all_targets(self):
        self.saved_targets.clear()
        self._auto_save_targets()
        self.target_listbox.delete(0, tk.END)

    def move_to_selected_target(self):
        if not self.is_connected or not self.indy:
            return
        selected = self.target_listbox.curselection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một điểm trong danh sách để di chuyển tới.")
            return
        idx = selected[0]
        target = self.saved_targets[idx]
        
        client = self.indy
        def run():
            try:
                status = client.get_robot_status()
                if status.get('ready', 0) != 1:
                    self._post_ui(lambda: messagebox.showwarning(
                        "Cảnh báo",
                        "Robot chưa READY. Hãy bật SERVO và tắt chế độ Cầm tay trước khi di chuyển."
                    ))
                    return
                point_speed = target.get('speed', 200)
                self._apply_speed_now(point_speed)
                
                mtype = target['type']
                if mtype == "MoveJ":
                    client.joint_move_to(target['joint'])
                elif mtype == "MoveL":
                    client.task_move_to(target['tcp'])
            except Exception as e:
                def show_err(e=e): messagebox.showerror("Lỗi", f"Lỗi di chuyển tới điểm: {e}")
                self._post_ui(show_err)
                
        threading.Thread(target=run, daemon=True).start()

    def apply_general_speed_to_all(self):
        if not self.saved_targets:
            messagebox.showwarning("Cảnh báo", "Danh sách điểm đang trống.")
            return
        speed = self.speed_slider.get()
        for t in self.saved_targets:
            t['speed'] = speed
            
        self._auto_save_targets()
        self.target_listbox.delete(0, tk.END)
        for i, t in enumerate(self.saved_targets):
            mtype = t['type']
            is_fillet = t.get('fillet', False)
            radius = t.get('radius', 0.0)
            z_tag = get_zone_label(is_fillet, radius)
            pt_name = f"[{mtype}] P{i+1}: "
            if mtype == "MoveJ":
                pt_name += "J[" + ", ".join([f"{a:.1f}" for a in t['joint'][:3]]) + "...]"
            else:
                pt_name += "T[" + ", ".join([f"{x*1000.0:.1f}" for x in t['tcp'][:3]]) + "...]"
            pt_name += f" - V:{speed:.0f}mm/s [{z_tag}]"
            self.target_listbox.insert(tk.END, pt_name)
            
        messagebox.showinfo("Thông báo", f"Đã áp dụng tốc độ {speed} mm/s cho tất cả {len(self.saved_targets)} điểm.")

    def export_targets(self):
        if not self.saved_targets:
            messagebox.showwarning("Cảnh báo", "Danh sách điểm trống, không thể xuất file.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu Danh Sách Điểm",
            defaultextension=".json",
            filetypes=[("JSON Files (*.json)", "*.json"), ("CSV Files (*.csv)", "*.csv"), ("Tất cả (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            if path.endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Type", "J1", "J2", "J3", "J4", "J5", "J6", "X", "Y", "Z", "Rx", "Ry", "Rz", "Speed", "Fillet", "Radius"])
                    for t in self.saved_targets:
                        fillet_str = "1" if t.get('fillet', False) else "0"
                        radius_val = t.get('radius', 0.0)
                        writer.writerow([t['type']] + t['joint'] + t['tcp'] + [t.get('speed', 200), fillet_str, radius_val])
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.saved_targets, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Thành công", f"Đã xuất {len(self.saved_targets)} điểm ra file:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi file: {e}")

    def import_targets(self):
        path = filedialog.askopenfilename(
            title="Tải Danh Sách Điểm",
            filetypes=[("JSON / CSV Files", "*.json;*.csv"), ("JSON Files (*.json)", "*.json"), ("CSV Files (*.csv)", "*.csv"), ("Tất cả (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            new_targets = []
            if path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    new_targets = json.load(f)
            else:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    for row in reader:
                        if not row: continue
                        speed = float(row[13]) if len(row) > 13 else 200.0
                        is_fillet = (row[14].strip() == "1") if len(row) > 14 else False
                        radius = float(row[15]) if len(row) > 15 else 0.0
                        new_targets.append({
                            'type': row[0].strip(),
                            'joint': [float(x) for x in row[1:7]],
                            'tcp': [float(x) for x in row[7:13]],
                            'speed': speed,
                            'fillet': is_fillet,
                            'radius': radius,
                            'zone': get_zone_label(is_fillet, radius)
                        })
            self.saved_targets = new_targets
            self._auto_save_targets()
            self.target_listbox.delete(0, tk.END)
            for idx, t in enumerate(self.saved_targets):
                self.target_listbox.insert(tk.END, self._format_target_label(idx + 1, t))
            messagebox.showinfo("Thành công", f"Đã nạp thành công {len(self.saved_targets)} điểm từ:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")

    def run_cycle(self):
        if not self.is_connected or not self.indy:
            return
        if not self.saved_targets:
            messagebox.showwarning("Cảnh báo", "Không có điểm nào được lưu để chạy chu trình.")
            return
            
        status = self.status_cache
        if status.get('ready', 0) != 1:
            messagebox.showwarning(
                "Cảnh báo",
                "Robot chưa READY. Hãy bật SERVO và tắt chế độ Cầm tay trước khi chạy chu trình."
            )
            return
            
        self.cycle_running = True
            
        def run():
            # UI Disable - Luồng chính
            def disable_ui():
                self.btn_run_cycle.config(state="disabled", text="Đang chạy...")
                self.btn_save_point.config(state="disabled")
                self.btn_update_point.config(state="disabled")
                self.btn_clear_points.config(state="disabled")
                self.btn_delete_point.config(state="disabled")
                self.point_speed_slider.config(state="disabled")
                self.btn_move_to_point.config(state="disabled")
                self.btn_apply_all_speed.config(state="disabled")

                # Luôn giữ các nút can thiệp khẩn cấp ở trạng thái BẬT
                self.btn_stop_cycle.config(state="normal", bg=self.accent_red)
                self.btn_servo_off.config(state="normal")
                self.btn_disconnect.config(state="normal", bg=self.accent_red)
                self.btn_emg.config(state="normal")
            self._post_ui(disable_ui)
            
            # Phân nhóm các điểm:
            # - Chuỗi điểm có fillet == True sẽ được gom chạy Waypoint Fillet
            # - Điểm có fillet == False sẽ di chuyển đơn lẻ và dừng chính xác 100%
            segments = []
            curr_seg = []
            
            try:
                self.indy.execute_waypoint_path(
                    self.saved_targets,
                    cancel_check_cb=lambda: not self.cycle_running or not self.is_connected
                )
            except Exception as e:
                print(f"Lỗi chạy chu trình: {e}")
            finally:
                if self.indy:
                    self.indy._flush_socket()
                time.sleep(0.3)  # Nghỉ 300ms giải phóng băng thông truyền trước khi trả lại quyền điều khiển
            
            self.cycle_running = False
            # UI Enable - Luồng chính
            def enable_ui():
                if self.is_connected:
                    self.btn_run_cycle.config(state="normal", text="Chạy Chu Trình")
                    self.btn_save_point.config(state="normal")
                    self.btn_update_point.config(state="normal")
                    self.btn_clear_points.config(state="normal")
                    self.btn_delete_point.config(state="normal")
                    self.point_speed_slider.config(state="normal")
                    self.btn_move_to_point.config(state="normal")
                    self.btn_apply_all_speed.config(state="normal")
                    self.target_listbox.selection_clear(0, tk.END)
            self._post_ui(enable_ui)
            
        threading.Thread(target=run, daemon=True).start()

    def stop_cycle(self):
        self.cycle_running = False
        def enable_ui():
            if self.is_connected:
                self.btn_run_cycle.config(state="normal", text="Chạy Chu Trình")
                self.btn_save_point.config(state="normal")
                self.btn_update_point.config(state="normal")
                self.btn_clear_points.config(state="normal")
                self.btn_delete_point.config(state="normal")
                self.point_speed_slider.config(state="normal")
                self.btn_move_to_point.config(state="normal")
                self.btn_apply_all_speed.config(state="normal")
        self._post_ui(enable_ui)

        def run_stop():
            try:
                if self.indy:
                    self.indy.stop_motion()
            except Exception as e:
                print(f"Lỗi dừng chu trình: {e}")
        threading.Thread(target=run_stop, daemon=True).start()

    def upload_program(self, proj_json_str):
        if not self.is_connected or not self.indy:
            return False
        return self.indy.upload_json_program(proj_json_str)

    def move_to_saved_target_wait(self, idx, cancel_cb=None):
        """Hàm di chuyển đến điểm lưu trong danh sách và đợi dừng (dùng cho kịch bản đồng bộ)"""
        if not self.is_connected or not self.indy or idx >= len(self.saved_targets):
            return False
            
        target = self.saved_targets[idx]
        mtype = target['type']
        
        try:
            st = self.indy.get_robot_status()
            if isinstance(st, dict) and st.get('busy', 0) == 1:
                self.indy.stop_motion()
                time.sleep(0.1)
        except Exception:
            pass

        try:
            point_speed = target.get('speed', 200)
            self.update_speed(point_speed)
            time.sleep(0.05)

            if mtype == "MoveJ":
                self.indy.joint_move_to(target['joint'])
            elif mtype == "MoveL":
                self.indy.task_move_to(target['tcp'])
                
            time.sleep(0.2)
            timeout = 30.0
            elapsed = 0.0
            while elapsed < timeout:
                if cancel_cb and cancel_cb():
                    if self.indy: self.indy.stop_motion()
                    return False
                status = self.indy.get_robot_status()
                is_moving = status.get('busy', 0) == 1 or status.get('is_robot_moving', 0) == 1
                if not is_moving:
                    return True
                time.sleep(0.2)
                elapsed += 0.2
        except Exception as e:
            print(f"Lỗi di chuyển điểm {idx+1} của {self.panel_name}: {e}")
            
        return False

    def update_status_loop(self):
        consecutive_err_count = 0
        while self.running:
            if self.is_connected and self.indy:
                # Nhường socket cho luồng Jog khi đang giữ nút
                if self.jog_holding:
                    time.sleep(0.3)
                    continue
                try:
                    state_data = self.indy.get_all_states()
                    if state_data:
                        consecutive_err_count = 0
                        angles = state_data['angles']
                        tcp = state_data['tcp']
                        servo_state, brake_state = state_data['servo_state']
                        status = state_data['status']

                        # Cập nhật cache trạng thái để on_jog_press dùng (không cần gọi socket)
                        self.status_cache = status
                        self.status_cache_time = time.monotonic()

                        # Nếu phát hiện lỗi/khẩn cấp trong khi đang Jog -> Tự động dừng khẩn
                        if (status.get('error', 0) == 1 or status.get('emergency', 0) == 1 or status.get('collision', 0) == 1) and self.jog_holding:
                            self.on_jog_release()
                        
                        def update_ui():
                            # Cập nhật nhãn hiển thị góc khớp và thanh giới hạn
                            for i in range(min(len(angles), 6)):
                                val = angles[i]
                                self.angle_labels[i].config(text=f"J{i+1}: {val:.2f}°")
                                
                                if i < len(self.limit_canvases):
                                    canvas = self.limit_canvases[i]
                                    min_lim, max_lim = self.joint_limits[i]
                                    span = max_lim - min_lim
                                    
                                    val_clamped = max(min_lim, min(max_lim, val))
                                    pct = (val_clamped - min_lim) / span
                                    cw = max(100, canvas.winfo_width())
                                    bar_w = cw - 20
                                    x_val = 10 + pct * bar_w
                                    
                                    dist_to_limit = min(abs(val - min_lim), abs(val - max_lim))
                                    
                                    if dist_to_limit <= 3.0:
                                        fill_color = self.accent_red
                                        label_color = self.accent_red
                                    elif dist_to_limit <= 15.0:
                                        fill_color = self.accent_orange
                                        label_color = self.accent_orange
                                    else:
                                        fill_color = self.accent_green
                                        label_color = self.text_color
                                        
                                    self.limit_labels[i].config(
                                        text=f"J{i+1}: {val:.2f}° ({min_lim}° ~ {max_lim}°)",
                                        fg=label_color
                                    )
                                    
                                    canvas.coords(self.limit_pointers[i], x_val - 5, 3, x_val + 5, 15)
                                    canvas.itemconfig(self.limit_pointers[i], fill=fill_color)
                                    canvas.coords("bg_bar", 10, 7, 10 + bar_w, 11)
                                    
                            # Cập nhật nhãn hiển thị TCP
                            tcp_names = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
                            for i in range(min(len(tcp), 6)):
                                if i < 3:
                                    val = tcp[i] * 1000.0
                                    unit = "mm"
                                else:
                                    val = tcp[i]
                                    unit = "°"
                                self.tcp_labels[i].config(text=f"{tcp_names[i]}: {val:.2f} {unit}")
                                
                            # Cập nhật trạng thái Servo
                            if sum(servo_state) > 0:
                                self.lbl_servo_status.config(text="Servo: ON (Động cơ giữ lực | Phanh đã nhả)", fg=self.accent_green)
                            else:
                                self.lbl_servo_status.config(text="Servo: OFF (Đã ngắt lực | Đang khóa phanh vật lý)", fg=self.accent_red)
                                
                            # Cập nhật Badges
                            if status.get('ready', 0) == 1:
                                self.badge_ready.config(text="READY: YES", bg=self.accent_green)
                            else:
                                self.badge_ready.config(text="READY: NO", bg=self.accent_gray)
                                
                            if status.get('emergency', 0) == 1:
                                self.badge_emg.config(text="EMG: STOPPED", bg=self.accent_red)
                            else:
                                self.badge_emg.config(text="EMG: NORMAL", bg=self.accent_green)
                                
                            if status.get('collision', 0) == 1:
                                self.badge_col.config(text="COLLISION: ACTIVE", bg=self.accent_red)
                            else:
                                self.badge_col.config(text="COLLISION: NO", bg=self.accent_green)
                                
                            err_info = status.get('error_info', {})
                            self.last_error_info = err_info
                            if status.get('error', 0) == 1 or status.get('emergency', 0) == 1 or status.get('collision', 0) == 1:
                                self.badge_err.config(text="ERROR: ACTIVE", bg=self.accent_red)
                                err_msg = err_info.get('msg', 'Phát hiện trạng thái lỗi')
                                self.lbl_error_info.config(text=f"⚠️ Lỗi: {err_msg}", fg=self.accent_red)
                            else:
                                self.badge_err.config(text="ERROR: NO", bg=self.accent_green)
                                self.lbl_error_info.config(text="✓ Trạng thái: Hệ thống hoạt động bình thường", fg=self.accent_green)
                                
                        self._post_ui(update_ui)
                    else:
                        consecutive_err_count += 1
                        if consecutive_err_count >= 3:
                            print("Phát hiện mất kết nối socket quá 3 lần liên tiếp! Chuyển về trạng thái Disconnect...")
                            self.is_connected = False
                            self._post_ui(self.disconnect_robot)
                except Exception as e:
                    print(f"Lỗi vòng lặp cập nhật: {e}")
                    consecutive_err_count += 1
                    if consecutive_err_count >= 3 or any(x in str(e).lower() for x in ["10054", "10038", "forcibly closed", "connection reset"]):
                        print("Phát hiện mất kết nối mạng TCP cứng! Chuyển về trạng thái Disconnect...")
                        self.is_connected = False
                        self._post_ui(self.disconnect_robot)
            # 2 Hz là đủ cho HMI, giảm mạnh tải so với 4 request mỗi 150 ms.
            time.sleep(0.5)

    def destroy_panel(self):
        self.running = False
        self.cycle_running = False
        self._jog_stop_event.set()
        self._jog_generation += 1
        self.jog_holding = False
        self.jog_active = False
        self.is_connected = False
        self._ui_dispatcher_closed = True
        client = self.indy
        self.indy = None
        if client:
            threading.Thread(
                target=client.disconnect,
                daemon=True,
                name=f"{self.panel_name}-shutdown"
            ).start()

    def open_error_details_dialog(self):
        err_info = getattr(self, 'last_error_info', None)

        if not err_info:
            err_info = {'code': 0, 'msg': 'Không có dữ liệu lỗi từ Controller', 'joint': None, 'raw': None}

        dialog = tk.Toplevel(self)
        dialog.title("🔍 Chi tiết Mã Lỗi Robot Neuromeka")
        dialog.geometry("540x440")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self)
        dialog.grab_set()

        hdr = tk.Label(dialog, text="BÁO CÁO MÃ LỖI CONTROLLER ROBOT", font=("Segoe UI", 12, "bold"), bg=self.bg_color, fg=self.accent_blue)
        hdr.pack(pady=(15, 5))

        info_frame = tk.LabelFrame(dialog, text=" Thông tin chi tiết ", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg=self.text_color, bd=1)
        info_frame.pack(padx=15, pady=10, fill="both", expand=True)

        code_val = err_info.get('code', '0')
        msg_val = err_info.get('msg', 'Không phát hiện lỗi')
        joint_val = err_info.get('joint')
        joint_str = f"Khớp J{joint_val + 1}" if joint_val is not None and 0 <= joint_val < 6 else "Toàn hệ thống / Không áp dụng"

        tk.Label(info_frame, text="📍 Mã lỗi (Error Code):", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_color).pack(anchor="w", padx=10, pady=(10, 2))
        tk.Label(info_frame, text=f"   {code_val}", font=("Segoe UI", 11, "bold"), bg=self.card_color, fg=self.accent_red if str(code_val) != "0" else self.accent_green).pack(anchor="w", padx=10, pady=(0, 5))

        tk.Label(info_frame, text="📍 Khớp ảnh hưởng (Joint):", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_color).pack(anchor="w", padx=10, pady=(5, 2))
        tk.Label(info_frame, text=f"   {joint_str}", font=("Segoe UI", 10), bg=self.card_color, fg=self.text_color).pack(anchor="w", padx=10, pady=(0, 5))

        tk.Label(info_frame, text="📍 Mô tả & Chi tiết thông báo:", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_color).pack(anchor="w", padx=10, pady=(5, 2))
        msg_lbl = tk.Message(info_frame, text=msg_val, font=("Segoe UI", 10), bg=self.card_color, fg=self.text_color, width=480)
        msg_lbl.pack(anchor="w", padx=10, pady=(0, 10))

        rec_frame = tk.Frame(dialog, bg=self.card_color, bd=1, relief="groove")
        rec_frame.pack(padx=15, pady=(0, 10), fill="x")

        tk.Label(rec_frame, text="* Gợi ý xử lý & Khắc phục:", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg="#f39c12").pack(anchor="w", padx=10, pady=(5, 2))
        guide_text = "1. Kiểm tra môi trường xung quanh, loại bỏ vật cản nếu bị va chạm.\n2. Nếu bấm nút EMG khẩn cấp, hãy xoay nhả nút cơ khí.\n3. Nhấn 'Reset Robot' bên dưới để khôi phục trạng thái Servo Controller."
        tk.Label(rec_frame, text=guide_text, font=("Segoe UI", 8), bg=self.card_color, fg=self.text_color, justify="left").pack(anchor="w", padx=10, pady=(0, 5))

        btn_box = tk.Frame(dialog, bg=self.bg_color)
        btn_box.pack(pady=10)

        def do_reset():
            dialog.destroy()
            self.reset_robot()

        btn_reset = tk.Button(btn_box, text="* Reset Robot Ngay", font=("Segoe UI", 9, "bold"), bg=self.accent_green, fg="white", command=do_reset, padx=15, pady=4)
        btn_reset.pack(side="left", padx=10)

        btn_close = tk.Button(btn_box, text="Đóng", font=("Segoe UI", 9), bg=self.accent_gray, fg="white", command=dialog.destroy, padx=15, pady=4)
        btn_close.pack(side="left", padx=10)

    def open_tcp_calib_dialog(self):
        TCPCalibrationDialog(self.winfo_toplevel(), self)

    def open_ref_frame_calib_dialog(self):
        RefFrameCalibrationDialog(self.winfo_toplevel(), self)


class TCPCalibrationDialog(tk.Toplevel):
    def __init__(self, parent, robot_panel):
        super().__init__(parent)
        self.robot_panel = robot_panel
        self.indy = robot_panel.indy
        self.robot_name = robot_panel.robot_name

        self.title(f"🎯 Hiệu Chuẩn TCP 4 Điểm - {self.robot_name}")
        self.geometry("820x720")
        
        # Color palette
        self.bg_color = "#1e1e24"
        self.card_color = "#2a2b36"
        self.text_color = "#ffffff"
        self.accent_blue = "#007acc"
        self.accent_green = "#28a745"
        self.accent_red = "#dc3545"
        self.accent_orange = "#fd7e14"
        self.accent_gray = "#4e5166"

        self.configure(bg=self.bg_color)
        self.resizable(False, False)

        self.points = [None, None, None, None]  # 4 poses: Each pose is [X, Y, Z, Rx, Ry, Rz]
        self.point_labels = []
        self.calculated_tcp = None  # [x_mm, y_mm, z_mm]
        self.rms_error = None
        self.max_error = None
        self._point_reads_in_progress = set()

        self.create_widgets()
        self.transient(parent)
        # Không dùng grab_set để cho phép người dùng thoải mái Jog / di chuyển robot ở cửa sổ chính song song

    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self, bg=self.bg_color)
        header_frame.pack(fill="x", padx=20, pady=10)

        lbl_title = tk.Label(header_frame, text=f"🎯 BỘ HIỆU CHUẨN TCP 4 ĐIỂM ({self.robot_name.upper()})",
                             font=("Segoe UI", 14, "bold"), bg=self.bg_color, fg=self.accent_blue)
        lbl_title.pack(anchor="w")

        lbl_guide = tk.Label(header_frame, text="Hướng dẫn: Di chuyển kim đo (TCP) chạm ĐÚNG 1 điểm mốc cố định ở 4 góc nghiêng khác nhau. Nhấn 'Lưu P' tương ứng tại mỗi tư thế.",
                              font=("Segoe UI", 9), bg=self.bg_color, fg="#bdc3c7", justify="left")
        lbl_guide.pack(anchor="w", pady=(2, 0))

        # Khung điều khiển nhanh chế độ Cầm tay ngay trên cửa sổ Calib
        quick_ctrl = tk.Frame(header_frame, bg=self.card_color, bd=1, relief="solid")
        quick_ctrl.pack(fill="x", pady=8)

        tk.Label(quick_ctrl, text="Bảng điều khiển nhanh (Có thể Jog bên ngoài giao diện chính song song):",
                 font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_color).pack(side="left", padx=10, pady=5)

        btn_t_on = tk.Button(quick_ctrl, text="BẬT CHẾ ĐỘ CẦM TAY", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                             command=lambda: self.robot_panel.toggle_teach_mode(True))
        btn_t_on.pack(side="left", padx=5, pady=5)

        btn_t_off = tk.Button(quick_ctrl, text="TẮT (KHÓA LẠI)", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                             command=lambda: self.robot_panel.toggle_teach_mode(False))
        btn_t_off.pack(side="left", padx=5, pady=5)

        # Points Container Frame
        points_frame = tk.LabelFrame(self, text=" Danh sách 4 điểm tư thế mốc ", font=("Segoe UI", 10, "bold"),
                                    bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        points_frame.pack(fill="x", padx=20, pady=5)

        for i in range(4):
            row_f = tk.Frame(points_frame, bg=self.card_color)
            row_f.pack(fill="x", padx=10, pady=6)

            lbl_name = tk.Label(row_f, text=f"📍 Điểm P{i+1}:", font=("Segoe UI", 10, "bold"),
                                bg=self.card_color, fg="#f1c40f", width=10, anchor="w")
            lbl_name.pack(side="left", padx=5)

            lbl_val = tk.Label(row_f, text="[ Chưa lưu dữ liệu ]", font=("Segoe UI", 9),
                               bg="#1e1e24", fg="#7f8c8d", width=54, anchor="w", bd=1, relief="sunken", padx=5, pady=3)
            lbl_val.pack(side="left", padx=5)
            self.point_labels.append(lbl_val)

            btn_save = tk.Button(row_f, text=f"Lưu P{i+1}", font=("Segoe UI", 9, "bold"),
                                 bg=self.accent_orange, fg="white", width=8,
                                 command=lambda idx=i: self.save_point(idx))
            btn_save.pack(side="left", padx=3)

            btn_clear = tk.Button(row_f, text="Xóa", font=("Segoe UI", 9),
                                  bg=self.accent_gray, fg="white", width=5,
                                  command=lambda idx=i: self.clear_point(idx))
            btn_clear.pack(side="left", padx=3)

        # Action Buttons Frame
        action_frame = tk.Frame(self, bg=self.bg_color)
        action_frame.pack(fill="x", padx=20, pady=10)

        self.btn_calc = tk.Button(action_frame, text="* TÍNH TOÁN TCP", font=("Segoe UI", 10, "bold"),
                                  bg=self.accent_blue, fg="white", height=2, command=self.calculate_tcp)
        self.btn_calc.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_reset_all = tk.Button(action_frame, text="* ĐẶT LẠI 4 ĐIỂM", font=("Segoe UI", 10, "bold"),
                                       bg="#57606f", fg="white", height=2, command=self.reset_all_points)
        self.btn_reset_all.pack(side="left", fill="x", expand=True, padx=5)

        # Results Display Frame
        results_frame = tk.LabelFrame(self, text=" Kết quả tính toán TCP Offset ", font=("Segoe UI", 10, "bold"),
                                       bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        results_frame.pack(fill="x", padx=20, pady=5)

        res_grid = tk.Frame(results_frame, bg=self.card_color)
        res_grid.pack(fill="x", padx=15, pady=10)

        tk.Label(res_grid, text="TCP Offset [X, Y, Z]:", font=("Segoe UI", 10, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=0, column=0, sticky="w", pady=4)
        self.lbl_res_tcp = tk.Label(res_grid, text="X = --- mm | Y = --- mm | Z = --- mm",
                                    font=("Segoe UI", 11, "bold"), bg=self.card_color, fg="#2ecc71")
        self.lbl_res_tcp.grid(row=0, column=1, sticky="w", padx=10, pady=4)

        tk.Label(res_grid, text="Sai số trung bình (RMS):", font=("Segoe UI", 10, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=1, column=0, sticky="w", pady=4)
        self.lbl_res_error = tk.Label(res_grid, text="RMS: --- mm (Tối đa: --- mm)",
                                      font=("Segoe UI", 10), bg=self.card_color, fg="#3498db")
        self.lbl_res_error.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        tk.Label(res_grid, text="Đánh giá chất lượng:", font=("Segoe UI", 10, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=2, column=0, sticky="w", pady=4)
        self.lbl_res_quality = tk.Label(res_grid, text="Chưa tính toán",
                                        font=("Segoe UI", 10, "bold"), bg=self.card_color, fg=self.accent_gray)
        self.lbl_res_quality.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        # Apply & Close Frame
        bottom_frame = tk.Frame(self, bg=self.bg_color)
        bottom_frame.pack(fill="x", padx=20, pady=15)

        self.btn_apply = tk.Button(bottom_frame, text="✅ ÁP DỤNG TCP VÀO ROBOT CONTROLLER",
                                   font=("Segoe UI", 11, "bold"), bg=self.accent_green, fg="white",
                                   height=2, state="disabled", command=self.apply_tcp_to_robot)
        self.btn_apply.pack(fill="x", expand=True)

    def save_point(self, index):
        if not self.robot_panel.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối! Vui lòng kết nối Robot trước khi lưu điểm.", parent=self)
            return
        if index in self._point_reads_in_progress:
            return
        self._point_reads_in_progress.add(index)
        self.point_labels[index].config(text="[ Đang đọc tọa độ... ]", fg="#f1c40f")
        client = self.indy

        def read_tcp():
            try:
                tcp = client.get_task_pos()

                def apply_tcp():
                    if not self.winfo_exists():
                        return
                    self._point_reads_in_progress.discard(index)
                    self.points[index] = tcp
                    str_val = (
                        f"X:{tcp[0] * 1000.0:.1f} Y:{tcp[1] * 1000.0:.1f} "
                        f"Z:{tcp[2] * 1000.0:.1f} | Rx:{tcp[3]:.1f}° "
                        f"Ry:{tcp[4]:.1f}° Rz:{tcp[5]:.1f}°"
                    )
                    self.point_labels[index].config(text=str_val, fg="#2ecc71")

                self.robot_panel._post_ui(apply_tcp)
            except Exception as exc:
                def show_error(exc=exc):
                    if not self.winfo_exists():
                        return
                    self._point_reads_in_progress.discard(index)
                    self.point_labels[index].config(text="[ Đọc thất bại ]", fg="#e74c3c")
                    messagebox.showerror("Lỗi", f"Không thể đọc tọa độ từ Robot: {exc}", parent=self)
                self.robot_panel._post_ui(show_error)

        threading.Thread(
            target=read_tcp,
            daemon=True,
            name=f"{self.robot_name}-tcp-read-{index + 1}"
        ).start()

    def clear_point(self, index):
        self.points[index] = None
        self.point_labels[index].config(text="[ Chưa lưu dữ liệu ]", fg="#7f8c8d")
        self.btn_apply.config(state="disabled")

    def reset_all_points(self):
        for i in range(4):
            self.clear_point(i)
        self.calculated_tcp = None
        self.rms_error = None
        self.max_error = None
        self.lbl_res_tcp.config(text="X = --- mm | Y = --- mm | Z = --- mm", fg="#2ecc71")
        self.lbl_res_error.config(text="RMS: --- mm (Tối đa: --- mm)", fg="#3498db")
        self.lbl_res_quality.config(text="Chưa tính toán", fg=self.accent_gray)
        self.btn_apply.config(state="disabled")

    def calculate_tcp(self):
        if any(p is None for p in self.points):
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng lưu đủ cả 4 điểm (P1, P2, P3, P4) trước khi tính toán!", parent=self)
            return

        import numpy as np

        def get_rotation_matrix(rx_deg, ry_deg, rz_deg):
            rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
            Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
            Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
            Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
            return Rz @ Ry @ Rx

        try:
            P_flange = []
            R_mats = []
            for p in self.points:
                P_flange.append(np.array([p[0] * 1000.0, p[1] * 1000.0, p[2] * 1000.0]))
                R_mats.append(get_rotation_matrix(p[3], p[4], p[5]))

            A = []
            B = []
            for i in range(1, 4):
                A.append(R_mats[0] - R_mats[i])
                B.append(P_flange[i] - P_flange[0])
            A = np.vstack(A)
            B = np.hstack(B)

            V_tcp, _, _, _ = np.linalg.lstsq(A, B, rcond=None)

            P_targets = [P_flange[i] + R_mats[i] @ V_tcp for i in range(4)]
            P_target_avg = np.mean(P_targets, axis=0)
            errors = [np.linalg.norm(pt - P_target_avg) for pt in P_targets]
            rms_err = float(np.sqrt(np.mean(np.square(errors))))
            max_err = float(np.max(errors))

            self.calculated_tcp = V_tcp
            self.rms_error = rms_err
            self.max_error = max_err

            self.lbl_res_tcp.config(text=f"X = {V_tcp[0]:.2f} mm | Y = {V_tcp[1]:.2f} mm | Z = {V_tcp[2]:.2f} mm", fg="#2ecc71")
            self.lbl_res_error.config(text=f"RMS: {rms_err:.2f} mm (Tối đa: {max_err:.2f} mm)")

            if rms_err < 1.0:
                self.lbl_res_quality.config(text="Cực kỳ chính xác (< 1.0mm)", fg="#2ecc71")
            elif rms_err < 2.5:
                self.lbl_res_quality.config(text="Chính xác tốt (< 2.5mm)", fg="#f1c40f")
            else:
                self.lbl_res_quality.config(text="Sai số cao (>= 2.5mm) - Nên đo lại điểm", fg="#e74c3c")

            self.btn_apply.config(state="normal")
        except Exception as e:
            messagebox.showerror("Lỗi tính toán", f"Không thể tính toán TCP: {e}", parent=self)

    def apply_tcp_to_robot(self):
        if self.calculated_tcp is None:
            return

        if not self.robot_panel.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối!", parent=self)
            return

        x_m = self.calculated_tcp[0] / 1000.0
        y_m = self.calculated_tcp[1] / 1000.0
        z_m = self.calculated_tcp[2] / 1000.0
        fpos = [x_m, y_m, z_m, 0.0, 0.0, 0.0]

        client = self.indy
        result_tcp = list(self.calculated_tcp)
        self.btn_apply.config(state="disabled", text="ĐANG GHI XUỐNG CONTROLLER...")

        def write_tcp():
            error = None
            try:
                success = client.set_tool_frame(fpos)
            except Exception as exc:
                success = False
                error = exc

            def finish_write():
                if not self.winfo_exists():
                    return
                self.btn_apply.config(state="normal", text="✅ ÁP DỤNG TCP VÀO ROBOT CONTROLLER")
                if success:
                    messagebox.showinfo(
                        "Thành công",
                        f"Đã ghi TCP mới cho {self.robot_name}!\n\n"
                        f"Offset: X={result_tcp[0]:.2f}mm, Y={result_tcp[1]:.2f}mm, Z={result_tcp[2]:.2f}mm",
                        parent=self
                    )
                    self.destroy()
                elif error:
                    messagebox.showerror("Lỗi", f"Không thể ghi TCP vào Robot: {error}", parent=self)
                else:
                    messagebox.showerror("Lỗi", "Controller không chấp nhận cấu hình TCP mới!", parent=self)

            self.robot_panel._post_ui(finish_write)

        threading.Thread(
            target=write_tcp,
            daemon=True,
            name=f"{self.robot_name}-tcp-write"
        ).start()


class RefFrameCalibrationDialog(tk.Toplevel):
    def __init__(self, parent, robot_panel):
        super().__init__(parent)
        self.robot_panel = robot_panel
        self.indy = robot_panel.indy
        self.robot_name = robot_panel.robot_name

        self.title(f"📐 Dựng & Hiệu Chuẩn Reference Frame (3 Điểm) - {self.robot_name}")
        self.geometry("860x830")
        
        # Color palette
        self.bg_color = "#1e1e24"
        self.card_color = "#2a2b36"
        self.text_color = "#ffffff"
        self.accent_blue = "#007acc"
        self.accent_green = "#28a745"
        self.accent_red = "#dc3545"
        self.accent_orange = "#fd7e14"
        self.accent_purple = "#8e44ad"
        self.accent_gray = "#4e5166"

        self.configure(bg=self.bg_color)
        self.resizable(False, False)

        # 3 points: P_origin, P_x_axis, P_xy_plane
        # Each point is [X, Y, Z, Rx, Ry, Rz] in [m, m, m, deg, deg, deg]
        self.points = [None, None, None]
        self.point_labels = []
        self.calculated_ref_frame = None  # [x_m, y_m, z_m, rx_deg, ry_deg, rz_deg]
        self._point_reads_in_progress = set()

        self.var_set_origin = tk.BooleanVar(value=True)

        self.create_widgets()
        self.transient(parent)
        self.load_current_ref_frame()

    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self, bg=self.bg_color)
        header_frame.pack(fill="x", padx=20, pady=10)

        lbl_title = tk.Label(header_frame, text=f"📐 BỘ DỰNG & HIỆU CHUẨN REFERENCE FRAME 3 ĐIỂM ({self.robot_name.upper()})",
                             font=("Segoe UI", 13, "bold"), bg=self.bg_color, fg="#9b59b6")
        lbl_title.pack(anchor="w")

        lbl_guide = tk.Label(header_frame,
                             text="Hướng dẫn: Dạy 3 điểm trên mặt bàn làm việc để căn chỉnh hệ trục XYZ song song hoàn toàn với mặt bàn,\n"
                                  "khắc phục hiện tượng Jog Task bị xéo/lệch so với mép bàn hoặc băng chuyền.",
                             font=("Segoe UI", 9), bg=self.bg_color, fg="#bdc3c7", justify="left")
        lbl_guide.pack(anchor="w", pady=(2, 0))

        # Khung điều khiển nhanh chế độ Cầm tay
        quick_ctrl = tk.Frame(header_frame, bg=self.card_color, bd=1, relief="solid")
        quick_ctrl.pack(fill="x", pady=6)

        tk.Label(quick_ctrl, text="Bảng điều khiển nhanh (Có thể Jog bên ngoài giao diện chính song song):",
                 font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_color).pack(side="left", padx=10, pady=5)

        btn_t_on = tk.Button(quick_ctrl, text="BẬT CHẾ ĐỘ CẦM TAY", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                             command=lambda: self.robot_panel.toggle_teach_mode(True))
        btn_t_on.pack(side="left", padx=5, pady=5)

        btn_t_off = tk.Button(quick_ctrl, text="TẮT (KHÓA LẠI)", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                             command=lambda: self.robot_panel.toggle_teach_mode(False))
        btn_t_off.pack(side="left", padx=5, pady=5)

        # Khung Hệ trục tọa độ hiện tại & Nút Reset Base
        curr_frame_box = tk.LabelFrame(self, text=" Hệ trục Reference Frame hiện tại trên Robot ", font=("Segoe UI", 10, "bold"),
                                       bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        curr_frame_box.pack(fill="x", padx=20, pady=3)

        curr_inner = tk.Frame(curr_frame_box, bg=self.card_color)
        curr_inner.pack(fill="x", padx=10, pady=5)

        self.lbl_curr_frame = tk.Label(curr_inner, text="[ Đang đọc dữ liệu từ Robot Controller... ]",
                                       font=("Segoe UI", 9, "bold"), bg=self.card_color, fg="#f39c12", anchor="w")
        self.lbl_curr_frame.pack(side="left", fill="x", expand=True, padx=5)

        btn_reset_base = tk.Button(curr_inner, text="* Reset về Gốc Base", font=("Segoe UI", 9, "bold"),
                                   bg="#c0392b", fg="white", command=self.reset_to_base_frame)
        btn_reset_base.pack(side="right", padx=5)

        # Points Container Frame (3 Points)
        points_frame = tk.LabelFrame(self, text=" Danh sách 3 điểm định hướng hệ trục ", font=("Segoe UI", 10, "bold"),
                                     bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        points_frame.pack(fill="x", padx=20, pady=4)

        point_descriptions = [
            ("📍 Điểm 1 (Gốc O):", "Điểm đặt làm gốc tọa độ (0, 0, 0) của mặt bàn hoặc phôi"),
            ("➡️ Điểm 2 (+X):", "Điểm nằm trên phương trục +X (dọc theo mép bàn / băng tải)"),
            ("↗️ Điểm 3 (Mặt XY):", "Điểm trên mặt bàn theo hướng +Y (tạo mặt phẳng làm việc XY)")
        ]

        for i, (title, desc) in enumerate(point_descriptions):
            row_f = tk.Frame(points_frame, bg=self.card_color)
            row_f.pack(fill="x", padx=10, pady=4)

            title_box = tk.Frame(row_f, bg=self.card_color, width=150)
            title_box.pack(side="left", padx=5)
            lbl_name = tk.Label(title_box, text=title, font=("Segoe UI", 9, "bold"),
                                bg=self.card_color, fg="#f1c40f", anchor="w")
            lbl_name.pack(anchor="w")
            lbl_sub = tk.Label(title_box, text=desc, font=("Segoe UI", 7),
                               bg=self.card_color, fg="#95a5a6", anchor="w")
            lbl_sub.pack(anchor="w")

            lbl_val = tk.Label(row_f, text="[ Chưa lưu dữ liệu ]", font=("Segoe UI", 9),
                               bg="#1e1e24", fg="#7f8c8d", width=46, anchor="w", bd=1, relief="sunken", padx=5, pady=3)
            lbl_val.pack(side="left", padx=5, fill="y")
            self.point_labels.append(lbl_val)

            btn_save = tk.Button(row_f, text="Lưu Điểm", font=("Segoe UI", 9, "bold"),
                                 bg=self.accent_orange, fg="white", width=9,
                                 command=lambda idx=i: self.save_point(idx))
            btn_save.pack(side="left", padx=3)

            btn_clear = tk.Button(row_f, text="Xóa", font=("Segoe UI", 9),
                                  bg=self.accent_gray, fg="white", width=5,
                                  command=lambda idx=i: self.clear_point(idx))
            btn_clear.pack(side="left", padx=3)

        # Options Frame
        opt_frame = tk.Frame(self, bg=self.bg_color)
        opt_frame.pack(fill="x", padx=20, pady=2)

        chk_origin = tk.Checkbutton(
            opt_frame,
            text="☑ Thiết lập Gốc tọa độ mới tại Điểm O (Nếu bỏ chọn: Gốc tọa độ giữ nguyên (0,0,0) ở Base, chỉ xoay hướng trục X/Y/Z)",
            variable=self.var_set_origin, font=("Segoe UI", 9),
            bg=self.bg_color, fg=self.text_color, selectcolor=self.card_color, activebackground=self.bg_color,
            activeforeground=self.text_color
        )
        chk_origin.pack(anchor="w", padx=5)

        # Action Buttons Frame
        action_frame = tk.Frame(self, bg=self.bg_color)
        action_frame.pack(fill="x", padx=20, pady=4)

        # Hàng 1: Tính toán & Đặt lại
        row1_act = tk.Frame(action_frame, bg=self.bg_color)
        row1_act.pack(fill="x", pady=2)

        self.btn_calc = tk.Button(row1_act, text="* TÍNH TOÁN REFERENCE FRAME", font=("Segoe UI", 10, "bold"),
                                  bg=self.accent_blue, fg="white", height=2, command=self.calculate_ref_frame)
        self.btn_calc.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_reset_all = tk.Button(row1_act, text="* ĐẶT LẠI 3 ĐIỂM", font=("Segoe UI", 10, "bold"),
                                       bg="#57606f", fg="white", height=2, command=self.reset_all_points)
        self.btn_reset_all.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Hàng 2: Lưu File & Tải File
        row2_act = tk.Frame(action_frame, bg=self.bg_color)
        row2_act.pack(fill="x", pady=2)

        self.btn_save_file = tk.Button(row2_act, text="💾 LƯU CẤU HÌNH RA TỆP (.JSON)", font=("Segoe UI", 9, "bold"),
                                       bg="#27ae60", fg="white", height=1, command=self.save_ref_frame_to_file)
        self.btn_save_file.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_load_file = tk.Button(row2_act, text="📂 TẢI CẤU HÌNH TỪ TỆP (.JSON)", font=("Segoe UI", 9, "bold"),
                                       bg="#2980b9", fg="white", height=1, command=self.load_ref_frame_from_file)
        self.btn_load_file.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Results Display Frame
        results_frame = tk.LabelFrame(self, text=" Kết quả tính toán Reference Frame ", font=("Segoe UI", 10, "bold"),
                                       bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        results_frame.pack(fill="x", padx=20, pady=4)

        res_grid = tk.Frame(results_frame, bg=self.card_color)
        res_grid.pack(fill="x", padx=15, pady=6)

        tk.Label(res_grid, text="Tọa độ Gốc [X, Y, Z]:", font=("Segoe UI", 9, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_res_origin = tk.Label(res_grid, text="Chưa tính toán", font=("Segoe UI", 10, "bold"),
                                       bg=self.card_color, fg="#7f8c8d")
        self.lbl_res_origin.grid(row=0, column=1, sticky="w", padx=10, pady=2)

        tk.Label(res_grid, text="Góc xoay [Rx, Ry, Rz]:", font=("Segoe UI", 9, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=1, column=0, sticky="w", pady=2)
        self.lbl_res_angles = tk.Label(res_grid, text="Chưa tính toán", font=("Segoe UI", 10, "bold"),
                                       bg=self.card_color, fg="#7f8c8d")
        self.lbl_res_angles.grid(row=1, column=1, sticky="w", padx=10, pady=2)

        tk.Label(res_grid, text="Thông số hình học:", font=("Segoe UI", 9, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=2, column=0, sticky="w", pady=2)
        self.lbl_res_vectors = tk.Label(res_grid, text="Độ dài trục X: --- mm | Độ dài trục Y: --- mm | Góc phẳng: ---°",
                                        font=("Segoe UI", 9), bg=self.card_color, fg="#bdc3c7")
        self.lbl_res_vectors.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        tk.Label(res_grid, text="Chất lượng căn chỉnh:", font=("Segoe UI", 9, "bold"),
                 bg=self.card_color, fg=self.text_color).grid(row=3, column=0, sticky="w", pady=2)
        self.lbl_res_quality = tk.Label(res_grid, text="Chưa tính toán", font=("Segoe UI", 9, "bold"),
                                        bg=self.card_color, fg=self.accent_gray)
        self.lbl_res_quality.grid(row=3, column=1, sticky="w", padx=10, pady=2)

        # Apply Button
        apply_frame = tk.Frame(self, bg=self.bg_color)
        apply_frame.pack(fill="x", padx=20, pady=6)

        self.btn_apply = tk.Button(apply_frame, text="✅ ÁP DỤNG REFERENCE FRAME VÀO ROBOT CONTROLLER",
                                   font=("Segoe UI", 11, "bold"), bg=self.accent_green, fg="white",
                                   height=2, command=self.apply_ref_frame_to_robot, state="disabled")
        self.btn_apply.pack(fill="x")

    def load_current_ref_frame(self):
        """Đọc và hiển thị hệ trục Reference Frame hiện tại của Robot."""
        if not self.robot_panel.is_connected or not self.indy:
            self.lbl_curr_frame.config(text="Robot chưa kết nối", fg=self.accent_gray)
            return

        def fetch():
            try:
                curr = self.indy.get_reference_frame()
                if curr and len(curr) >= 6:
                    x_mm, y_mm, z_mm = curr[0] * 1000.0, curr[1] * 1000.0, curr[2] * 1000.0
                    rx, ry, rz = curr[3], curr[4], curr[5]
                    is_zero = all(abs(v) < 1e-4 for v in curr)
                    status_text = " (Gốc Base Mặc Định)" if is_zero else " (Hệ trục đã hiệu chuẩn)"
                    def update_ui():
                        if not self.winfo_exists():
                            return
                        self.lbl_curr_frame.config(
                            text=f"Gốc: X={x_mm:+.1f} mm, Y={y_mm:+.1f} mm, Z={z_mm:+.1f} mm  |  Góc xoay: Rx={rx:+.2f}°, Ry={ry:+.2f}°, Rz={rz:+.2f}°{status_text}",
                            fg="#2ecc71" if is_zero else "#f39c12"
                        )
                    self.robot_panel._post_ui(update_ui)
            except Exception as e:
                def update_err():
                    if not self.winfo_exists():
                        return
                    self.lbl_curr_frame.config(text=f"Lỗi đọc Ref Frame: {e}", fg=self.accent_red)
                self.robot_panel._post_ui(update_err)

        threading.Thread(target=fetch, daemon=True).start()

    def reset_to_base_frame(self):
        """Reset Reference Frame về mặc định của Base Frame [0,0,0, 0,0,0]."""
        if not self.robot_panel.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối!", parent=self)
            return

        ans = messagebox.askyesno(
            "Xác nhận Reset",
            f"Bạn có chắc chắn muốn Reset Reference Frame của {self.robot_name} về Gốc Base mặc định [0, 0, 0, 0, 0, 0] không?\n\n"
            "(Hệ trục tọa độ Task Jog sẽ quay về chuẩn theo chân đế Robot).",
            parent=self
        )
        if not ans:
            return

        def run_reset():
            ok = self.indy.reset_reference_frame()
            def finish():
                if not self.winfo_exists():
                    return
                if ok:
                    messagebox.showinfo("Thành công", f"Đã reset Reference Frame của {self.robot_name} về Gốc Base mặc định [0, 0, 0, 0, 0, 0]!", parent=self)
                    self.load_current_ref_frame()
                else:
                    messagebox.showerror("Lỗi", "Không thể reset Reference Frame trên Robot Controller!", parent=self)
            self.robot_panel._post_ui(finish)

        threading.Thread(target=run_reset, daemon=True).start()

    def save_point(self, idx):
        if not self.robot_panel.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối! Vui lòng kết nối Robot trước.", parent=self)
            return

        if idx in self._point_reads_in_progress:
            return
        self._point_reads_in_progress.add(idx)

        self.point_labels[idx].config(text="[ Đang đọc tọa độ TCP... ]", fg=self.accent_orange)

        def read_pos():
            try:
                tcp = self.indy.get_task_pos()
                if tcp and len(tcp) >= 6:
                    self.points[idx] = list(tcp)
                    x_mm = tcp[0] * 1000.0
                    y_mm = tcp[1] * 1000.0
                    z_mm = tcp[2] * 1000.0
                    rx, ry, rz = tcp[3], tcp[4], tcp[5]
                    text = f"X: {x_mm:7.2f} mm | Y: {y_mm:7.2f} mm | Z: {z_mm:7.2f} mm  (Rx:{rx:5.1f}°, Ry:{ry:5.1f}°, Rz:{rz:5.1f}°)"
                    def update_success():
                        if not self.winfo_exists():
                            return
                        self.point_labels[idx].config(text=text, fg="#2ecc71")
                        self._point_reads_in_progress.discard(idx)
                    self.robot_panel._post_ui(update_success)
                else:
                    raise ValueError("Dữ liệu vị trí trả về không hợp lệ")
            except Exception as e:
                def update_fail():
                    if not self.winfo_exists():
                        return
                    self.point_labels[idx].config(text=f"[ Lỗi đọc: {e} ]", fg=self.accent_red)
                    self._point_reads_in_progress.discard(idx)
                self.robot_panel._post_ui(update_fail)

        threading.Thread(target=read_pos, daemon=True).start()

    def clear_point(self, idx):
        self.points[idx] = None
        self.point_labels[idx].config(text="[ Chưa lưu dữ liệu ]", fg="#7f8c8d")
        self.calculated_ref_frame = None
        self.lbl_res_origin.config(text="Chưa tính toán", fg="#7f8c8d")
        self.lbl_res_angles.config(text="Chưa tính toán", fg="#7f8c8d")
        self.lbl_res_vectors.config(text="Độ dài trục X: --- mm | Độ dài trục Y: --- mm | Góc phẳng: ---°")
        self.lbl_res_quality.config(text="Chưa tính toán", fg=self.accent_gray)
        self.btn_apply.config(state="disabled")

    def reset_all_points(self):
        for i in range(3):
            self.clear_point(i)

    def calculate_ref_frame(self):
        if any(p is None for p in self.points):
            messagebox.showwarning(
                "Thiếu dữ liệu",
                "Vui lòng lưu đủ cả 3 điểm:\n"
                "  - Điểm 1 (Gốc O)\n"
                "  - Điểm 2 (Hướng trục +X)\n"
                "  - Điểm 3 (Mặt phẳng XY / Hướng +Y)\n"
                "trước khi thực hiện tính toán!",
                parent=self
            )
            return

        import numpy as np

        try:
            po = np.array(self.points[0][:3], dtype=float)
            px = np.array(self.points[1][:3], dtype=float)
            pxy = np.array(self.points[2][:3], dtype=float)

            vx = px - po
            vxy = pxy - po

            len_vx = np.linalg.norm(vx)
            len_vxy = np.linalg.norm(vxy)

            if len_vx < 0.010:  # < 10mm
                messagebox.showerror(
                    "Khoảng cách quá ngắn",
                    f"Khoảng cách từ Điểm Gốc O đến Điểm X chỉ đạt {len_vx*1000.0:.1f} mm (< 10 mm).\n"
                    "Vui lòng di chuyển điểm X xa gốc O hơn (khuyến nghị >= 50 mm) để đảm bảo độ chính xác góc.",
                    parent=self
                )
                return

            if len_vxy < 0.010:  # < 10mm
                messagebox.showerror(
                    "Khoảng cách quá ngắn",
                    f"Khoảng cách từ Điểm Gốc O đến Điểm XY chỉ đạt {len_vxy*1000.0:.1f} mm (< 10 mm).\n"
                    "Vui lòng di chuyển điểm XY xa gốc O hơn (khuyến nghị >= 50 mm).",
                    parent=self
                )
                return

            x_hat = vx / len_vx

            # Vector pháp tuyến mặt phẳng XY = trục Z
            vz = np.cross(x_hat, vxy)
            len_vz = np.linalg.norm(vz)

            if len_vz < 1e-4:
                messagebox.showerror(
                    "Điểm thẳng hàng",
                    "3 điểm bạn chọn gần như thẳng hàng trên 1 đường thẳng!\n"
                    "Không thể tạo được mặt phẳng tọa độ XY.\n"
                    "Vui lòng lưu lại Điểm 3 (XY) lệch sang hướng vuông góc với trục X.",
                    parent=self
                )
                return

            z_hat = vz / len_vz
            y_hat = np.cross(z_hat, x_hat)  # Trục Y trực giao

            # Ma trận xoay R = [x_hat, y_hat, z_hat]
            R = np.column_stack([x_hat, y_hat, z_hat])

            # Tính góc Euler RPY (Z-Y-X: R = Rz @ Ry @ Rx)
            beta = np.arctan2(-R[2, 0], np.sqrt(R[0, 0]**2 + R[1, 0]**2))
            if np.abs(np.cos(beta)) > 1e-6:
                alpha = np.arctan2(R[2, 1], R[2, 2])
                gamma = np.arctan2(R[1, 0], R[0, 0])
            else:
                alpha = 0.0
                gamma = np.arctan2(-R[0, 1], R[1, 1])

            rx_deg, ry_deg, rz_deg = np.degrees([alpha, beta, gamma])

            # Góc giữa vector vx và vxy
            cos_angle = np.clip(np.dot(vx, vxy) / (len_vx * len_vxy), -1.0, 1.0)
            plane_angle_deg = float(np.degrees(np.arccos(cos_angle)))

            keep_origin = self.var_set_origin.get()
            if keep_origin:
                origin_pos = po.tolist()
            else:
                origin_pos = [0.0, 0.0, 0.0]

            self.calculated_ref_frame = [
                float(origin_pos[0]), float(origin_pos[1]), float(origin_pos[2]),
                float(rx_deg), float(ry_deg), float(rz_deg)
            ]

            # Cập nhật hiển thị kết quả
            x_mm = origin_pos[0] * 1000.0
            y_mm = origin_pos[1] * 1000.0
            z_mm = origin_pos[2] * 1000.0

            self.lbl_res_origin.config(text=f"X = {x_mm:+.2f} mm | Y = {y_mm:+.2f} mm | Z = {z_mm:+.2f} mm", fg="#2ecc71")
            self.lbl_res_angles.config(text=f"Rx = {rx_deg:+.2f}° | Ry = {ry_deg:+.2f}° | Rz = {rz_deg:+.2f}°", fg="#3498db")
            self.lbl_res_vectors.config(
                text=f"Độ dài trục X: {len_vx*1000.0:.1f} mm | Độ dài trục Y: {len_vxy*1000.0:.1f} mm | Góc phẳng: {plane_angle_deg:.1f}°"
            )

            if 45.0 <= plane_angle_deg <= 135.0:
                self.lbl_res_quality.config(text=f"Chất lượng căn chỉnh: RẤT TỐT (Góc phẳng {plane_angle_deg:.1f}°)", fg="#2ecc71")
            elif 20.0 <= plane_angle_deg <= 160.0:
                self.lbl_res_quality.config(text=f"Chất lượng căn chỉnh: CHẤP NHẬN ĐƯỢC (Góc phẳng {plane_angle_deg:.1f}°)", fg="#f1c40f")
            else:
                self.lbl_res_quality.config(text=f"Góc mặt phẳng hơi hẹp ({plane_angle_deg:.1f}°) - Khuyên nên chọn điểm Y rộng hơn", fg="#e74c3c")

            self.btn_apply.config(state="normal")
        except Exception as e:
            messagebox.showerror("Lỗi tính toán", f"Không thể tính toán Reference Frame: {e}", parent=self)

    def save_ref_frame_to_file(self):
        """Lưu toàn bộ điểm dạy và kết quả Reference Frame ra file JSON."""
        ref_frame_to_save = self.calculated_ref_frame
        if ref_frame_to_save is None:
            if self.robot_panel.is_connected and self.indy:
                try:
                    curr = self.indy.get_reference_frame()
                    if curr and len(curr) >= 6 and any(abs(v) > 1e-4 for v in curr):
                        ref_frame_to_save = list(curr)
                except Exception:
                    pass

        if ref_frame_to_save is None and all(p is None for p in self.points):
            messagebox.showwarning(
                "Chưa có dữ liệu",
                "Chưa có dữ liệu Reference Frame để lưu!\n\n"
                "Vui lòng lưu 3 điểm và bấm 'TÍNH TOÁN REFERENCE FRAME' trước khi lưu file.",
                parent=self
            )
            return

        import json
        from datetime import datetime

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_robot_name = self.robot_name.replace(" ", "_").replace("&", "_").replace("(", "").replace(")", "").replace("/", "_")
        default_filename = f"RefFrame_{safe_robot_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lưu File Cấu Hình Reference Frame",
            initialfile=default_filename,
            defaultextension=".json",
            filetypes=[("Reference Frame JSON (*.json)", "*.json"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return

        po = self.points[0]
        px = self.points[1]
        pxy = self.points[2]

        data = {
            "title": "Neuromeka Indy Reference Frame Configuration",
            "robot_name": self.robot_name,
            "created_at": now_str,
            "origin_mode": "custom_origin" if self.var_set_origin.get() else "base_origin",
            "points": {
                "P1_origin": po,
                "P2_x_axis": px,
                "P3_xy_plane": pxy
            },
            "reference_frame": ref_frame_to_save if ref_frame_to_save else [0.0] * 6,
            "reference_frame_display": {
                "x_mm": round((ref_frame_to_save[0] if ref_frame_to_save else 0.0) * 1000.0, 3),
                "y_mm": round((ref_frame_to_save[1] if ref_frame_to_save else 0.0) * 1000.0, 3),
                "z_mm": round((ref_frame_to_save[2] if ref_frame_to_save else 0.0) * 1000.0, 3),
                "rx_deg": round(ref_frame_to_save[3] if ref_frame_to_save else 0.0, 4),
                "ry_deg": round(ref_frame_to_save[4] if ref_frame_to_save else 0.0, 4),
                "rz_deg": round(ref_frame_to_save[5] if ref_frame_to_save else 0.0, 4)
            }
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            messagebox.showinfo(
                "Đã lưu thành công",
                f"Đã lưu cấu hình Reference Frame thành công vào tệp:\n{path}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Lỗi ghi file", f"Không thể lưu file cấu hình: {e}", parent=self)

    def load_ref_frame_from_file(self):
        """Tải cấu hình Reference Frame từ file JSON và sẵn sàng nạp vào Robot."""
        import json

        path = filedialog.askopenfilename(
            parent=self,
            title="Mở File Cấu Hình Reference Frame",
            filetypes=[("Reference Frame JSON (*.json)", "*.json"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Đọc 3 điểm nếu có trong file
            pts = data.get("points", {})
            p1 = pts.get("P1_origin")
            p2 = pts.get("P2_x_axis")
            p3 = pts.get("P3_xy_plane")

            for i, p in enumerate([p1, p2, p3]):
                if p and len(p) >= 6:
                    self.points[i] = list(p)
                    x_mm, y_mm, z_mm = p[0] * 1000.0, p[1] * 1000.0, p[2] * 1000.0
                    rx, ry, rz = p[3], p[4], p[5]
                    text = f"X: {x_mm:7.2f} mm | Y: {y_mm:7.2f} mm | Z: {z_mm:7.2f} mm  (Rx:{rx:5.1f}°, Ry:{ry:5.1f}°, Rz:{rz:5.1f}°)"
                    self.point_labels[i].config(text=text, fg="#2ecc71")
                else:
                    self.points[i] = None
                    self.point_labels[i].config(text="[ Không có trong file ]", fg="#7f8c8d")

            # Đọc origin mode
            mode = data.get("origin_mode", "custom_origin")
            self.var_set_origin.set(mode == "custom_origin")

            # Đọc reference_frame
            ref = data.get("reference_frame")
            if not ref or len(ref) < 6:
                disp = data.get("reference_frame_display", {})
                if disp:
                    ref = [
                        disp.get("x_mm", 0.0) / 1000.0,
                        disp.get("y_mm", 0.0) / 1000.0,
                        disp.get("z_mm", 0.0) / 1000.0,
                        disp.get("rx_deg", 0.0),
                        disp.get("ry_deg", 0.0),
                        disp.get("rz_deg", 0.0)
                    ]

            if ref and len(ref) >= 6:
                self.calculated_ref_frame = [float(v) for v in ref[:6]]
                x_mm = self.calculated_ref_frame[0] * 1000.0
                y_mm = self.calculated_ref_frame[1] * 1000.0
                z_mm = self.calculated_ref_frame[2] * 1000.0
                rx_deg = self.calculated_ref_frame[3]
                ry_deg = self.calculated_ref_frame[4]
                rz_deg = self.calculated_ref_frame[5]

                self.lbl_res_origin.config(text=f"X = {x_mm:+.2f} mm | Y = {y_mm:+.2f} mm | Z = {z_mm:+.2f} mm", fg="#2ecc71")
                self.lbl_res_angles.config(text=f"Rx = {rx_deg:+.2f}° | Ry = {ry_deg:+.2f}° | Rz = {rz_deg:+.2f}°", fg="#3498db")
                import os
                self.lbl_res_vectors.config(text=f"Nạp từ file: {os.path.basename(path)}")
                self.lbl_res_quality.config(text="Đã nạp thành công từ tệp cấu hình", fg="#2ecc71")
                self.btn_apply.config(state="normal")

                # Prompt apply
                if self.robot_panel.is_connected and self.indy:
                    ans = messagebox.askyesno(
                        "Nạp thành công",
                        f"Đã nạp thành công Reference Frame từ tệp:\n{os.path.basename(path)}\n\n"
                        f"📍 Tọa độ gốc: X={x_mm:+.2f} mm, Y={y_mm:+.2f} mm, Z={z_mm:+.2f} mm\n"
                        f"📍 Góc xoay: Rx={rx_deg:+.2f}°, Ry={ry_deg:+.2f}°, Rz={rz_deg:+.2f}°\n\n"
                        "Bạn có muốn ghi ngay cấu hình này xuống Robot Controller không?",
                        parent=self
                    )
                    if ans:
                        self.apply_ref_frame_to_robot()
            else:
                messagebox.showwarning("Dữ liệu không đầy đủ", "File không chứa cấu hình Reference Frame hợp lệ!", parent=self)

        except Exception as e:
            messagebox.showerror("Lỗi đọc file", f"Không thể đọc file cấu hình: {e}", parent=self)

    def apply_ref_frame_to_robot(self):
        if self.calculated_ref_frame is None:
            return

        if not self.robot_panel.is_connected or not self.indy:
            messagebox.showerror("Lỗi", "Robot chưa kết nối!", parent=self)
            return

        ref_frame = list(self.calculated_ref_frame)
        self.btn_apply.config(state="disabled", text="ĐANG GHI XUỐNG ROBOT CONTROLLER...")

        def write_frame():
            error = None
            try:
                success = self.indy.set_reference_frame(ref_frame)
            except Exception as exc:
                success = False
                error = exc

            def finish_write():
                if not self.winfo_exists():
                    return
                self.btn_apply.config(state="normal", text="✅ ÁP DỤNG REFERENCE FRAME VÀO ROBOT CONTROLLER")
                if success:
                    origin_type = "gốc tại Điểm O" if self.var_set_origin.get() else "gốc giữ nguyên tại Base"
                    messagebox.showinfo(
                        "Thành công",
                        f"Đã cập nhật Reference Frame thành công cho {self.robot_name}!\n\n"
                        f"📍 Chế độ: {origin_type}\n"
                        f"📍 Tọa độ gốc: X={ref_frame[0]*1000.0:+.2f} mm, Y={ref_frame[1]*1000.0:+.2f} mm, Z={ref_frame[2]*1000.0:+.2f} mm\n"
                        f"📍 Góc xoay: Rx={ref_frame[3]:+.2f}°, Ry={ref_frame[4]:+.2f}°, Rz={ref_frame[5]:+.2f}°\n\n"
                        "Giờ đây các lệnh Task Jog (X, Y, Z) và di chuyển thẳng (MoveL) sẽ song song hoàn toàn với mặt bàn làm việc!",
                        parent=self
                    )
                    self.load_current_ref_frame()
                elif error:
                    messagebox.showerror("Lỗi", f"Không thể ghi Reference Frame: {error}", parent=self)
                else:
                    messagebox.showerror("Lỗi", "Controller từ chối cấu hình Reference Frame mới!", parent=self)

            self.robot_panel._post_ui(finish_write)

        threading.Thread(target=write_frame, daemon=True).start()
