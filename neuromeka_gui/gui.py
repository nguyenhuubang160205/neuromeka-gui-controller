import sys
import time
import threading
import json
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from client import UnifiedIndyClient
from robot_panel import RobotControlPanel
from program_panel import ProgramStudioPanel
from io_panel import IOPanel


class IndyRobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HỆ THỐNG ĐIỀU KHIỂN ROBOT NEUROMEKA INDY7")

        # Cấu hình tương thích đa nền tảng (Windows / Linux Ubuntu)
        if sys.platform.startswith('win'):
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        # Kích thước cửa sổ tối ưu theo độ phân giải màn hình
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        win_w = min(1280, max(1000, screen_w - 60))
        win_h = min(800, max(680, screen_h - 90))
        self.root.geometry(f"{win_w}x{win_h}+{max(0, (screen_w - win_w) // 2)}+{max(0, (screen_h - win_h) // 2)}")

        try:
            self.root.state('zoomed')
        except Exception:
            pass

        # Cấu hình màu sắc Dark Mode công nghiệp
        self.bg_color = "#1e1e24"
        self.card_color = "#2a2b36"
        self.text_color = "#ffffff"
        self.accent_blue = "#007acc"
        self.accent_green = "#28a745"
        self.accent_red = "#dc3545"
        self.accent_orange = "#fd7e14"
        self.accent_gray = "#4e5166"

        self.root.configure(bg=self.bg_color)
        self.is_fullscreen = False
        self.running = True
        self.auto_running = False
        self.auto_thread = None
        self._ui_queue = queue.SimpleQueue()
        self._ui_dispatcher_closed = False
        self._closing = False

        # Style cho Notebook Tabs
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        style.configure('TNotebook.Tab', background=self.accent_gray, foreground="white", font=("Segoe UI", 10, "bold"), padding=[18, 6])
        style.map('TNotebook.Tab', background=[('selected', self.accent_blue)], foreground=[('selected', 'white')])

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab 1: Bảng Điều Khiển Chi Tiết Robot Indy7
        self.robot_panel = RobotControlPanel(self.notebook, "Robot Indy7", "192.168.0.10")
        self.notebook.add(self.robot_panel, text=" 🤖 Điều Khiển Robot Indy7 ")

        # Tab 2: Bảng Điều Khiển & Bật/Tắt I/O Chuyên Dụng
        self.io_panel = IOPanel(self.notebook, self.robot_panel)
        self.notebook.add(self.io_panel, text=" ⚡ Bảng Điều Khiển I/O ")

        # Tab 3: Màn Hình Vận Hành Tự Động HMI
        self.hmi_frame = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.hmi_frame, text=" *️ Vận Hành Tự Động HMI ")
        self.create_hmi_widgets()

        # Tab 4: Lập Trình Chu Trình Robot (Visual Block & Python Script Studio)
        self.program_panel = ProgramStudioPanel(self.notebook, self.robot_panel)
        self.notebook.add(self.program_panel, text=" * Lập Trình Chu Trình ")

        # Phím tắt F11 toàn màn hình
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(25, self._drain_ui_queue)

    def _post_ui(self, callback):
        if not self._ui_dispatcher_closed:
            self._ui_queue.put(callback)

    def _drain_ui_queue(self):
        if self._ui_dispatcher_closed:
            return
        for _ in range(64):
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                pass
        if not self._ui_dispatcher_closed:
            try:
                self.root.after(25, self._drain_ui_queue)
            except Exception:
                pass

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)

    def create_hmi_widgets(self):
        main_layout = tk.Frame(self.hmi_frame, bg=self.bg_color)
        main_layout.pack(fill="both", expand=True, padx=15, pady=10)

        # Cột Trái: Bảng Điều Khiển Nút Bấm & Giám Sát Sản Lượng
        left_col = tk.Frame(main_layout, bg=self.bg_color)
        left_col.pack(side="left", fill="both", expand=True, padx=8, pady=5)

        # 1. Khung Nút Bấm Vận Hành Công Nghiệp
        ctrl_box = tk.LabelFrame(left_col, text=" Bảng Nút Bấm Điều Khiển Vận Hành ", font=("Segoe UI", 11, "bold"),
                                 bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        ctrl_box.pack(fill="x", pady=5)

        mode_frame = tk.Frame(ctrl_box, bg=self.card_color)
        mode_frame.pack(fill="x", padx=15, pady=8)

        tk.Label(mode_frame, text="Chế Độ Vận Hành (000_MODE):", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg=self.text_color).pack(side="left")
        self.hmi_mode_var = tk.StringVar(value="AUTO (Chạy Tự Động)")
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.hmi_mode_var, values=["AUTO (Chạy Tự Động)", "MANUAL (Thao Tác Bằng Tay)"],
                                  state="readonly", font=("Segoe UI", 10), width=24)
        mode_combo.pack(side="left", padx=10)
        mode_combo.bind("<<ComboboxSelected>>", self.on_hmi_mode_change)

        btn_grid = tk.Frame(ctrl_box, bg=self.card_color)
        btn_grid.pack(fill="x", padx=15, pady=10)

        self.btn_hmi_start = tk.Button(btn_grid, text="> START\n(Chạy Tự Động)", font=("Segoe UI", 11, "bold"), bg=self.accent_green, fg="white",
                                       width=14, height=2, command=self.hmi_btn_start_click)
        self.btn_hmi_start.grid(row=0, column=0, padx=6, pady=6)

        self.btn_hmi_stop = tk.Button(btn_grid, text="■ STOP\n(Dừng Chu Trình)", font=("Segoe UI", 11, "bold"), bg=self.accent_red, fg="white",
                                      width=14, height=2, command=self.hmi_btn_stop_click)
        self.btn_hmi_stop.grid(row=0, column=1, padx=6, pady=6)

        self.btn_hmi_reset = tk.Button(btn_grid, text="* RESET\n(Xóa Lỗi / EMG)", font=("Segoe UI", 11, "bold"), bg=self.accent_orange, fg="white",
                                       width=14, height=2, command=self.hmi_btn_reset_click)
        self.btn_hmi_reset.grid(row=0, column=2, padx=6, pady=6)

        self.btn_hmi_home = tk.Button(btn_grid, text="* HOMING\n(Về Gốc An Toàn)", font=("Segoe UI", 11, "bold"), bg=self.accent_blue, fg="white",
                                      width=14, height=2, command=self.hmi_btn_home_click)
        self.btn_hmi_home.grid(row=1, column=0, padx=6, pady=6)

        self.btn_hmi_emg = tk.Button(btn_grid, text="* EMERGENCY\n(Dừng Khẩn Cấp)", font=("Segoe UI", 11, "bold"), bg="#c0392b", fg="white",
                                     width=14, height=2, command=self.hmi_btn_emg_click)
        self.btn_hmi_emg.grid(row=1, column=1, padx=6, pady=6)

        self.btn_servo_toggle = tk.Button(btn_grid, text="⚡ SERVO ON\n(Bật Nguồn Động Cơ)", font=("Segoe UI", 10, "bold"), bg="#8e44ad", fg="white",
                                          width=14, height=2, command=self.hmi_btn_servo_click)
        self.btn_servo_toggle.grid(row=1, column=2, padx=6, pady=6)

        # 2. Khung Giám Sát Năng Suất Sản Xuất
        data_box = tk.LabelFrame(left_col, text=" Giám Sát Dữ Liệu Sản Xuất ", font=("Segoe UI", 11, "bold"),
                                 bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        data_box.pack(fill="both", expand=True, pady=8)

        self.lbl_pho_count = tk.Label(data_box, text="Số Lượng Chu Trình Đã Hoàn Tất: 0 Lần", font=("Segoe UI", 14, "bold"), bg=self.card_color, fg="#f1c40f")
        self.lbl_pho_count.pack(anchor="w", padx=15, pady=8)

        btn_reset_cnt = tk.Button(data_box, text="Reset Bộ Đếm Sản Lượng", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                                  command=self.reset_pho_counter)
        btn_reset_cnt.pack(anchor="w", padx=15, pady=(0, 8))

        self.lbl_hmi_cycle_time = tk.Label(data_box, text="Thời Gian Chu Trình (Cycle Time): 00:00.0s", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg="#3498db")
        self.lbl_hmi_cycle_time.pack(anchor="w", padx=15, pady=4)

        self.lbl_hmi_uptime = tk.Label(data_box, text="Thời Gian Hệ Thống Hoạt Động (Uptime): 00:00:00", font=("Segoe UI", 10, "bold"), bg=self.card_color, fg="#2ecc71")
        self.lbl_hmi_uptime.pack(anchor="w", padx=15, pady=4)

        # Cột Phải: Mô Phỏng Đèn Tháp & Nhật Ký Cảnh Báo
        right_col = tk.Frame(main_layout, bg=self.bg_color)
        right_col.pack(side="right", fill="both", expand=True, padx=8, pady=5)

        # 3. Khung Giám Sát Đèn Tháp
        lamp_box = tk.LabelFrame(right_col, text=" Trạng Thái Đèn Tháp & Tín Hiệu Vận Hành ", font=("Segoe UI", 11, "bold"),
                                 bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        lamp_box.pack(fill="x", pady=5)

        self.lbl_machine_state = tk.Label(lamp_box, text="TRẠNG THÁI MÁY: STOPPED (ĐÃ DỪNG)", font=("Segoe UI", 12, "bold"), bg=self.card_color, fg="#f1c40f")
        self.lbl_machine_state.pack(pady=8)

        # Graphic Canvas Đèn Tháp
        self.tower_canvas = tk.Canvas(lamp_box, height=80, bg=self.card_color, highlightthickness=0)
        self.tower_canvas.pack(fill="x", padx=15, pady=5)

        self.lamp_green_oval = self.tower_canvas.create_oval(30, 15, 70, 55, fill="#1b4d2e", outline="#ffffff", width=1.5)
        self.tower_canvas.create_text(50, 68, text="TL_Green (Chạy)", fill=self.text_color, font=("Segoe UI", 8, "bold"))

        self.lamp_yellow_oval = self.tower_canvas.create_oval(110, 15, 150, 55, fill="#f1c40f", outline="#ffffff", width=1.5)
        self.tower_canvas.create_text(130, 68, text="TL_Yellow (Dừng)", fill=self.text_color, font=("Segoe UI", 8, "bold"))

        self.lamp_red_oval = self.tower_canvas.create_oval(190, 15, 230, 55, fill="#4d1b1b", outline="#ffffff", width=1.5)
        self.tower_canvas.create_text(210, 68, text="TL_Red (Lỗi/EMG)", fill=self.text_color, font=("Segoe UI", 8, "bold"))

        self.lamp_buzzer_oval = self.tower_canvas.create_oval(270, 15, 310, 55, fill="#2c3e50", outline="#ffffff", width=1.5)
        self.tower_canvas.create_text(290, 68, text="TL_Buzzer (Còi)", fill=self.text_color, font=("Segoe UI", 8, "bold"))

        # 4. Khung Nhật Ký Cảnh Báo Lỗi & Sự Cố
        alarm_box = tk.LabelFrame(right_col, text=" Nhật Ký Cảnh Báo & Sự Cố (ALARM LOG) ", font=("Segoe UI", 11, "bold"),
                                  bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        alarm_box.pack(fill="both", expand=True, pady=5)

        self.alarm_listbox = tk.Listbox(alarm_box, bg="#1e1e24", fg="#e74c3c", font=("Segoe UI", 9, "bold"), bd=0)
        self.alarm_listbox.pack(fill="both", expand=True, padx=10, pady=8)

        btn_clear_alarm = tk.Button(alarm_box, text="Xóa Nhật Ký Cảnh Báo", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                                    command=self.clear_alarm_log)
        btn_clear_alarm.pack(anchor="e", padx=10, pady=(0, 8))

        # Biến trạng thái HMI
        self.hmi_machine_state = "STOPPED"
        self.pho_counter = 0
        self.start_uptime = time.time()
        self.cycle_start_time = None
        self.flash_toggle = False

        # Khởi chạy luồng giám sát HMI
        self.root.after(500, self.update_hmi_status_loop)

    def on_hmi_mode_change(self, event=None):
        mode = self.hmi_mode_var.get()
        if "AUTO" in mode:
            messagebox.showinfo("Thông báo", "Đã chuyển sang chế độ TỰ ĐỘNG (AUTO Mode).")
        else:
            messagebox.showinfo("Thông báo", "Đã chuyển sang chế độ BẰNG TAY (MANUAL Mode).")

    def hmi_btn_start_click(self):
        if not self.robot_panel.is_connected:
            messagebox.showwarning("Cảnh báo", "Robot chưa kết nối mạng! Vui lòng bấm Connect tại Tab Điều Khiển.")
            return

        st = getattr(self.robot_panel, 'status_cache', {})
        if st.get('ready', 0) != 1:
            messagebox.showwarning("Cảnh báo", "Robot chưa READY! Vui lòng bấm RESET và BẬT SERVO trước khi START.")
            return

        if not self.robot_panel.saved_targets:
            messagebox.showwarning("Cảnh báo", "Chưa có danh sách điểm dạy (Target Points). Vui lòng thêm điểm trước khi chạy chu trình!")
            return

        self.hmi_machine_state = "RUNNING"
        self.cycle_start_time = time.time()
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Bắt đầu chạy chu trình tự động ({len(self.robot_panel.saved_targets)} điểm).")

        # Kích hoạt chạy chu trình tự động của robot_panel
        self.robot_panel.run_cycle()

    def hmi_btn_stop_click(self):
        self.hmi_machine_state = "STOPPED"
        self.robot_panel.stop_cycle()
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Đã bấm STOP - Dừng chu trình tự động.")

    def hmi_btn_reset_click(self):
        self.hmi_machine_state = "STOPPED"
        self.robot_panel.reset_robot_state()
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Đã bấm RESET - Xóa lỗi và reset trạng thái hệ thống.")

    def hmi_btn_home_click(self):
        if not self.robot_panel.is_connected:
            messagebox.showwarning("Cảnh báo", "Robot chưa kết nối mạng!")
            return

        self.hmi_machine_state = "HOMING"
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Đang di chuyển về vị trí Home...")
        
        def run_h():
            try:
                if self.robot_panel.indy:
                    self.robot_panel.indy.go_home()
                    time.sleep(1.0)
            except Exception as e:
                print(f"Lỗi go_home: {e}")
            finally:
                self.hmi_machine_state = "STOPPED"

        threading.Thread(target=run_h, daemon=True).start()

    def hmi_btn_emg_click(self):
        self.hmi_machine_state = "ERROR"
        self.robot_panel.emergency_stop()
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] LỖI KHẨN CẤP: Yêu cầu Dừng Khẩn Cấp (EMG)!")

    def hmi_btn_servo_click(self):
        if not self.robot_panel.is_connected:
            messagebox.showwarning("Cảnh báo", "Robot chưa kết nối mạng!")
            return
        self.robot_panel.servo_on()
        self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Đã gửi lệnh Bật nguồn Servo Ready.")

    def reset_pho_counter(self):
        self.pho_counter = 0
        self.lbl_pho_count.config(text="Số Lượng Chu Trình Đã Hoàn Tất: 0 Lần")

    def clear_alarm_log(self):
        self.alarm_listbox.delete(0, tk.END)

    def update_hmi_status_loop(self):
        if not self.running:
            return

        # Cập nhật thời gian Uptime
        uptime_sec = int(time.time() - self.start_uptime)
        h = uptime_sec // 3600
        m = (uptime_sec % 3600) // 60
        s = uptime_sec % 60
        self.lbl_hmi_uptime.config(text=f"Thời Gian Hệ Thống Hoạt Động (Uptime): {h:02d}:{m:02d}:{s:02d}")

        # Cập nhật thời gian chu trình
        if self.hmi_machine_state == "RUNNING" and self.cycle_start_time:
            c_elapsed = time.time() - self.cycle_start_time
            cm = int(c_elapsed // 60)
            cs = c_elapsed % 60
            self.lbl_hmi_cycle_time.config(text=f"Thời Gian Chu Trình (Cycle Time): {cm:02d}:{cs:04.1f}s")

        # Đồng bộ trạng thái chạy chu trình từ robot_panel
        if hasattr(self.robot_panel, 'cycle_running') and self.robot_panel.cycle_running:
            if self.hmi_machine_state != "RUNNING":
                self.hmi_machine_state = "RUNNING"
                self.cycle_start_time = time.time()
        elif self.hmi_machine_state == "RUNNING":
            self.hmi_machine_state = "STOPPED"
            self.pho_counter += 1
            self.lbl_pho_count.config(text=f"Số Lượng Chu Trình Đã Hoàn Tất: {self.pho_counter} Lần")

        # Kiểm tra cờ lỗi từ Robot
        st = getattr(self.robot_panel, 'status_cache', {})
        if st.get('error', 0) == 1 or st.get('emergency', 0) == 1 or st.get('collision', 0) == 1:
            if self.hmi_machine_state != "ERROR":
                self.hmi_machine_state = "ERROR"
                err_msg = st.get('error_info', {}).get('msg', 'Phát hiện sự cố phần cứng!')
                self.alarm_listbox.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ALARM: {err_msg}")

        # Cập nhật hiển thị Đèn Tháp (Tower Lamp)
        self.flash_toggle = not self.flash_toggle
        if self.hmi_machine_state == "RUNNING":
            self.lbl_machine_state.config(text="TRẠNG THÁI MÁY: RUNNING (ĐANG HOẠT ĐỘNG)", fg="#2ecc71")
            self.tower_canvas.itemconfig(self.lamp_green_oval, fill="#2ecc71")
            self.tower_canvas.itemconfig(self.lamp_yellow_oval, fill="#4a421b")
            self.tower_canvas.itemconfig(self.lamp_red_oval, fill="#4d1b1b")
            self.tower_canvas.itemconfig(self.lamp_buzzer_oval, fill="#2c3e50")
        elif self.hmi_machine_state == "STOPPED":
            self.lbl_machine_state.config(text="TRẠNG THÁI MÁY: STOPPED (ĐÃ DỪNG)", fg="#f1c40f")
            self.tower_canvas.itemconfig(self.lamp_green_oval, fill="#1b4d2e")
            self.tower_canvas.itemconfig(self.lamp_yellow_oval, fill="#f1c40f")
            self.tower_canvas.itemconfig(self.lamp_red_oval, fill="#4d1b1b")
            self.tower_canvas.itemconfig(self.lamp_buzzer_oval, fill="#2c3e50")
        elif self.hmi_machine_state == "ERROR":
            self.lbl_machine_state.config(text="TRẠNG THÁI MÁY: ERROR (SỰ CỐ KHẨN CẤP)", fg="#e74c3c")
            self.tower_canvas.itemconfig(self.lamp_green_oval, fill="#1b4d2e")
            self.tower_canvas.itemconfig(self.lamp_yellow_oval, fill="#4a421b")
            red_fill = "#e74c3c" if self.flash_toggle else "#4d1b1b"
            self.tower_canvas.itemconfig(self.lamp_red_oval, fill=red_fill)
            self.tower_canvas.itemconfig(self.lamp_buzzer_oval, fill="#e74c3c" if self.flash_toggle else "#2c3e50")

        self.root.after(500, self.update_hmi_status_loop)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        self.running = False
        self._ui_dispatcher_closed = True

        # Dừng interpreter & python runner nếu đang chạy
        try:
            if hasattr(self, 'program_panel'):
                if self.program_panel.program_interpreter:
                    self.program_panel.program_interpreter.stop()
                if self.program_panel.python_runner:
                    self.program_panel.python_runner.stop_script()
        except Exception:
            pass

        # Dừng luồng giám sát I/O
        try:
            if hasattr(self, 'io_panel'):
                self.io_panel.running = False
                self.io_panel._ui_dispatcher_closed = True
        except Exception:
            pass

        # Dừng robot_panel và các luồng điều khiển
        try:
            if hasattr(self, 'robot_panel'):
                self.robot_panel.destroy_panel()
        except Exception:
            pass

        # Đảm bảo nhả toàn bộ socket TCP / gRPC đến robot ngay lập tức
        try:
            from client import shutdown_all_clients
            shutdown_all_clients()
        except Exception:
            pass

        # Đóng cửa sổ giao diện Tkinter
        try:
            self.root.destroy()
        except Exception:
            pass
