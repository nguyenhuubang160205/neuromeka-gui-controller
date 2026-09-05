import time
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox


class IOPanel(tk.Frame):
    """
    Tab Chuyên Dụng Quản Lý, Bật/Tắt và Giám Sát Toàn Bộ 32 Digital Outputs & 32 Digital Inputs.
    Được thiết kế chuẩn hóa trung tính (DO 00..31, DI 00..31), không gán cố định thiết bị.
    """
    def __init__(self, parent, robot_panel):
        super().__init__(parent)
        self.robot_panel = robot_panel
        
        # Bảng màu Dark Mode đồng nhất
        self.bg_color = "#1e1e24"
        self.card_color = "#2a2b36"
        self.text_color = "#ffffff"
        self.accent_blue = "#007acc"
        self.accent_green = "#28a745"
        self.accent_red = "#dc3545"
        self.accent_orange = "#fd7e14"
        self.accent_gray = "#4e5166"
        
        self.configure(bg=self.bg_color)
        
        # Quản lý hàng đợi UI luồng an toàn
        self._ui_queue = queue.SimpleQueue()
        self._ui_dispatcher_closed = False
        self.running = True
        
        # Bộ đệm trạng thái 32 DO và 32 DI
        self.do_states = [0] * 32
        self.di_states = [0] * 32
        
        # Từ điển lưu widget để cập nhật nhanh
        self.do_buttons = {}
        self.do_badges = {}
        self.di_indicators = {}
        self.di_labels = {}
        
        self.create_widgets()
        self.after(25, self._drain_ui_queue)
        
        # Luồng giám sát I/O chạy ngầm nhẹ nhàng
        self.poll_thread = threading.Thread(target=self._io_poll_loop, daemon=True, name="IOPanel-Poll")
        self.poll_thread.start()

    def _post_ui(self, callback):
        if not self._ui_dispatcher_closed:
            self._ui_queue.put(callback)

    def _drain_ui_queue(self):
        if self._ui_dispatcher_closed:
            return
        for _ in range(64):
            try:
                cb = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                cb()
            except Exception as e:
                pass
        if not self._ui_dispatcher_closed:
            try:
                self.after(25, self._drain_ui_queue)
            except Exception:
                pass

    def _get_indy(self):
        if self.robot_panel and getattr(self.robot_panel, 'is_connected', False):
            return getattr(self.robot_panel, 'indy', None)
        return None

    def create_widgets(self):
        # Header Tiêu đề
        header_frame = tk.Frame(self, bg=self.card_color, height=50)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        lbl_title = tk.Label(header_frame, text="⚡ BẢNG ĐIỀU KHIỂN & GIÁM SÁT DIGITAL I/O (32 DO / 32 DI)",
                             font=("Segoe UI", 12, "bold"), bg=self.card_color, fg=self.text_color)
        lbl_title.pack(side="left", padx=15, pady=8)
        
        lbl_sub = tk.Label(header_frame, text="Hỗ trợ đầy đủ Cụm XS6 (TO 1-8), XS7 (DO 1-8), XS4/XS5 (DI 1-16) & Mở rộng",
                           font=("Segoe UI", 9, "italic"), bg=self.card_color, fg="#adb5bd")
        lbl_sub.pack(side="right", padx=15, pady=8)
        
        # Khung chứa 2 cột chính
        main_split = tk.Frame(self, bg=self.bg_color)
        main_split.pack(fill="both", expand=True, padx=10, pady=5)
        
        # =========================================================================
        # CỘT TRÁI: 32 DIGITAL OUTPUTS (DO)
        # =========================================================================
        left_col = tk.LabelFrame(main_split, text=" BẢNG ĐIỀU KHIỂN DIGITAL OUTPUTS (DO 00 - DO 31) ",
                                 font=("Segoe UI", 11, "bold"), bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 5), pady=5)
        
        # Thanh công cụ DO trên cùng
        do_toolbar = tk.Frame(left_col, bg=self.card_color)
        do_toolbar.pack(fill="x", padx=10, pady=6)
        
        btn_all_off = tk.Button(do_toolbar, text="⛔ TẮT TẤT CẢ (ALL OFF)", font=("Segoe UI", 9, "bold"),
                                bg=self.accent_red, fg="white", activebackground="#a71d2a", command=self.turn_all_do_off)
        btn_all_off.pack(side="left", padx=5)
        
        btn_all_on = tk.Button(do_toolbar, text="⚡ BẬT TẤT CẢ (ALL ON)", font=("Segoe UI", 9, "bold"),
                               bg=self.accent_green, fg="white", activebackground="#1e7e34", command=self.turn_all_do_on)
        btn_all_on.pack(side="left", padx=5)
        
        # Khung cuộn Canvas cho DO
        do_canvas = tk.Canvas(left_col, bg=self.card_color, highlightthickness=0)
        do_scrollbar = ttk.Scrollbar(left_col, orient="vertical", command=do_canvas.yview)
        self.do_scroll_content = tk.Frame(do_canvas, bg=self.card_color)
        
        self.do_scroll_content.bind("<Configure>", lambda e: do_canvas.configure(scrollregion=do_canvas.bbox("all")))
        do_canvas.create_window((0, 0), window=self.do_scroll_content, anchor="nw")
        do_canvas.configure(yscrollcommand=do_scrollbar.set)
        
        do_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=5)
        do_scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        
        self._build_do_matrix()
        
        # =========================================================================
        # CỘT PHẢI: 32 DIGITAL INPUTS (DI)
        # =========================================================================
        right_col = tk.LabelFrame(main_split, text=" GIÁM SÁT THỜI GIAN THỰC DIGITAL INPUTS (DI 00 - DI 31) ",
                                  font=("Segoe UI", 11, "bold"), bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        right_col.pack(side="right", fill="both", expand=True, padx=(5, 0), pady=5)
        
        # Thanh trạng thái DI trên cùng
        di_toolbar = tk.Frame(right_col, bg=self.card_color)
        di_toolbar.pack(fill="x", padx=10, pady=6)
        
        lbl_di_tip = tk.Label(di_toolbar, text="🟢 Đèn sáng: Tín hiệu mức 1 (ON) | ⚪ Đèn tắt: Mức 0 (OFF)",
                              font=("Segoe UI", 9, "bold"), bg=self.card_color, fg="#2ecc71")
        lbl_di_tip.pack(side="left", padx=5)
        
        # Khung cuộn Canvas cho DI
        di_canvas = tk.Canvas(right_col, bg=self.card_color, highlightthickness=0)
        di_scrollbar = ttk.Scrollbar(right_col, orient="vertical", command=di_canvas.yview)
        self.di_scroll_content = tk.Frame(di_canvas, bg=self.card_color)
        
        self.di_scroll_content.bind("<Configure>", lambda e: di_canvas.configure(scrollregion=di_canvas.bbox("all")))
        di_canvas.create_window((0, 0), window=self.di_scroll_content, anchor="nw")
        di_canvas.configure(yscrollcommand=di_scrollbar.set)
        
        di_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=5)
        di_scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        
        self._build_di_matrix()

    def _build_do_matrix(self):
        """Xây dựng 32 ô điều khiển DO chia theo 3 nhóm phần cứng"""
        # Nhóm 1: Cụm XS6 (TO 1 -> 8 / DO 00 -> DO 07)
        sec1 = tk.LabelFrame(self.do_scroll_content, text=" 📍 Cụm XS6 — NPN Sinking (TO_1 -> TO_8) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#3498db", bd=1, relief="solid")
        sec1.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_xs6 = [
            (0, "DO 00", "TO_1", "Chân 12"),
            (1, "DO 01", "TO_2", "Chân 11"),
            (2, "DO 02", "TO_3", "Chân 14"),
            (3, "DO 03", "TO_4", "Chân 13"),
            (4, "DO 04", "TO_5", "Chân 16"),
            (5, "DO 05", "TO_6", "Chân 15"),
            (6, "DO 06", "TO_7", "Chân 18"),
            (7, "DO 07", "TO_8", "Chân 17"),
        ]
        self._populate_do_grid(sec1, pinout_xs6)
        
        # Nhóm 2: Cụm XS7 (DO 1 -> 8 / DO 08 -> DO 15)
        sec2 = tk.LabelFrame(self.do_scroll_content, text=" 📍 Cụm XS7 — PNP Sourcing (DO_1 -> DO_8) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#f39c12", bd=1, relief="solid")
        sec2.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_xs7 = [
            (8, "DO 08", "DO_1", "Chân 42"),
            (9, "DO 09", "DO_2", "Chân 41"),
            (10, "DO 10", "DO_3", "Chân 44"),
            (11, "DO 11", "DO_4", "Chân 43"),
            (12, "DO 12", "DO_5", "Chân 46"),
            (13, "DO 13", "DO_6", "Chân 45"),
            (14, "DO 14", "DO_7", "Chân 48"),
            (15, "DO 15", "DO_8", "Chân 47"),
        ]
        self._populate_do_grid(sec2, pinout_xs7)
        
        # Nhóm 3: Cổng Mở Rộng (DO 16 -> DO 31)
        sec3 = tk.LabelFrame(self.do_scroll_content, text=" 📍 Cổng Mở Rộng (DO 16 -> DO 31) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#adb5bd", bd=1, relief="solid")
        sec3.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_ext = [(i, f"DO {i:02d}", f"EXT_{i-15}", f"DO_{i}") for i in range(16, 32)]
        self._populate_do_grid(sec3, pinout_ext)

    def _populate_do_grid(self, parent_frame, pin_tuples):
        grid_frame = tk.Frame(parent_frame, bg="#23242e")
        grid_frame.pack(fill="x", expand=True, padx=6, pady=4)
        
        for col_idx in range(2):
            grid_frame.columnconfigure(col_idx, weight=1)
            
        for i, (idx, do_name, hw_name, pin_num_str) in enumerate(pin_tuples):
            row = i // 2
            col = i % 2
            
            cell = tk.Frame(grid_frame, bg="#2d303e", bd=1, relief="ridge")
            cell.grid(row=row, column=col, padx=4, pady=3, sticky="nsew")
            
            header_row = tk.Frame(cell, bg="#2d303e")
            header_row.pack(fill="x", padx=6, pady=(4, 1))
            
            lbl_name = tk.Label(header_row, text=f"{do_name} ({hw_name})", font=("Segoe UI", 9, "bold"),
                                bg="#2d303e", fg=self.text_color)
            lbl_name.pack(side="left")
            
            badge = tk.Label(header_row, text="OFF", font=("Segoe UI", 8, "bold"),
                             bg="#3d4052", fg="#888899", width=4)
            badge.pack(side="right")
            self.do_badges[idx] = badge
            
            ctrl_row = tk.Frame(cell, bg="#2d303e")
            ctrl_row.pack(fill="x", padx=6, pady=(1, 4))
            
            lbl_pin = tk.Label(ctrl_row, text=f"Domino: {pin_num_str}", font=("Segoe UI", 8), bg="#2d303e", fg="#adb5bd")
            lbl_pin.pack(side="left")
            
            btn_toggle = tk.Button(ctrl_row, text="BẬT (ON)", font=("Segoe UI", 8, "bold"),
                                   bg=self.accent_gray, fg="white", width=9,
                                   command=lambda p=idx: self.toggle_do(p))
            btn_toggle.pack(side="right")
            self.do_buttons[idx] = btn_toggle

    def _build_di_matrix(self):
        """Xây dựng 32 ô giám sát DI chia theo 3 nhóm phần cứng"""
        # Nhóm 1: Cụm XS4 (DI 1 -> 8 / DI 00 -> DI 07)
        sec1 = tk.LabelFrame(self.di_scroll_content, text=" 📍 Cụm XS4 — Tín Hiệu Đầu Vào (DI_1 -> DI_8) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#2ecc71", bd=1, relief="solid")
        sec1.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_xs4 = [
            (0, "DI 00", "DI_1", "Chân 2"),
            (1, "DI 01", "DI_2", "Chân 1"),
            (2, "DI 02", "DI_3", "Chân 4"),
            (3, "DI 03", "DI_4", "Chân 3"),
            (4, "DI 04", "DI_5", "Chân 6"),
            (5, "DI 05", "DI_6", "Chân 5"),
            (6, "DI 06", "DI_7", "Chân 8"),
            (7, "DI 07", "DI_8", "Chân 7"),
        ]
        self._populate_di_grid(sec1, pinout_xs4)
        
        # Nhóm 2: Cụm XS5 (DI 9 -> 16 / DI 08 -> DI 15)
        sec2 = tk.LabelFrame(self.di_scroll_content, text=" 📍 Cụm XS5 — Tín Hiệu Đầu Vào (DI_9 -> DI_16) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#1abc9c", bd=1, relief="solid")
        sec2.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_xs5 = [
            (8, "DI 08", "DI_9", "Chân 32"),
            (9, "DI 09", "DI_10", "Chân 31"),
            (10, "DI 10", "DI_11", "Chân 34"),
            (11, "DI 11", "DI_12", "Chân 33"),
            (12, "DI 12", "DI_13", "Chân 36"),
            (13, "DI 13", "DI_14", "Chân 35"),
            (14, "DI 14", "DI_15", "Chân 38"),
            (15, "DI 15", "DI_16", "Chân 37"),
        ]
        self._populate_di_grid(sec2, pinout_xs5)
        
        # Nhóm 3: Cổng Mở Rộng (DI 16 -> DI 31)
        sec3 = tk.LabelFrame(self.di_scroll_content, text=" 📍 Cổng Mở Rộng (DI 16 -> DI 31) ",
                             font=("Segoe UI", 9, "bold"), bg="#23242e", fg="#adb5bd", bd=1, relief="solid")
        sec3.pack(fill="x", expand=True, padx=5, pady=4)
        
        pinout_ext = [(i, f"DI {i:02d}", f"EXT_{i-15}", f"DI_{i}") for i in range(16, 32)]
        self._populate_di_grid(sec3, pinout_ext)

    def _populate_di_grid(self, parent_frame, pin_tuples):
        grid_frame = tk.Frame(parent_frame, bg="#23242e")
        grid_frame.pack(fill="x", expand=True, padx=6, pady=4)
        
        for col_idx in range(2):
            grid_frame.columnconfigure(col_idx, weight=1)
            
        for i, (idx, di_name, hw_name, pin_num_str) in enumerate(pin_tuples):
            row = i // 2
            col = i % 2
            
            cell = tk.Frame(grid_frame, bg="#2d303e", bd=1, relief="ridge")
            cell.grid(row=row, column=col, padx=4, pady=3, sticky="nsew")
            
            row_content = tk.Frame(cell, bg="#2d303e")
            row_content.pack(fill="x", padx=6, pady=4)
            
            # Đèn LED tròn
            led_canvas = tk.Label(row_content, text="●", font=("Segoe UI", 16), bg="#2d303e", fg="#555566")
            led_canvas.pack(side="left", padx=(0, 4))
            self.di_indicators[idx] = led_canvas
            
            lbl_name = tk.Label(row_content, text=f"{di_name} ({hw_name})", font=("Segoe UI", 9, "bold"),
                                bg="#2d303e", fg=self.text_color)
            lbl_name.pack(side="left")
            
            state_lbl = tk.Label(row_content, text="OFF (0)", font=("Segoe UI", 8, "bold"),
                                 bg="#3d4052", fg="#888899", width=6)
            state_lbl.pack(side="right")
            self.di_labels[idx] = state_lbl
            
            lbl_pin = tk.Label(cell, text=f"Domino: {pin_num_str}", font=("Segoe UI", 8), bg="#2d303e", fg="#adb5bd")
            lbl_pin.pack(anchor="w", padx=6, pady=(0, 3))

    def toggle_do(self, pin_idx):
        """Bật/Tắt đảo trạng thái 1 cổng DO bất kỳ"""
        indy = self._get_indy()
        if not indy:
            messagebox.showwarning("Chưa kết nối", "Vui lòng kết nối Robot ở Tab 1 trước khi bật/tắt I/O!")
            return
        cur_val = self.do_states[pin_idx] if 0 <= pin_idx < len(self.do_states) else 0
        new_val = 0 if cur_val else 1
        
        def run_set():
            try:
                indy.set_do(pin_idx, bool(new_val))
                self.do_states[pin_idx] = new_val
                def ui_up():
                    badge = self.do_badges.get(pin_idx)
                    btn = self.do_buttons.get(pin_idx)
                    if new_val:
                        if badge: badge.config(text="ON", bg=self.accent_green, fg="white")
                        if btn: btn.config(bg=self.accent_green, text="TẮT (OFF)")
                    else:
                        if badge: badge.config(text="OFF", bg="#3d4052", fg="#888899")
                        if btn: btn.config(bg=self.accent_gray, text="BẬT (ON)")
                self._post_ui(ui_up)
            except Exception as e:
                print(f"Lỗi toggle_do {pin_idx}: {e}")
        threading.Thread(target=run_set, daemon=True, name=f"do-{pin_idx}").start()

    def turn_all_do_off(self):
        """Tắt toàn bộ các ngõ ra DO"""
        indy = self._get_indy()
        if not indy:
            return
        def run_off():
            try:
                for i in range(32):
                    if self.do_states[i] == 1:
                        indy.set_do(i, False)
                        self.do_states[i] = 0
                def ui_up():
                    for idx, badge in self.do_badges.items():
                        badge.config(text="OFF", bg="#3d4052", fg="#888899")
                    for idx, btn in self.do_buttons.items():
                        btn.config(bg=self.accent_gray, text="BẬT (ON)")
                self._post_ui(ui_up)
            except Exception as e:
                print(f"Lỗi turn_all_do_off: {e}")
        threading.Thread(target=run_off, daemon=True).start()

    def turn_all_do_on(self):
        """Bật toàn bộ các ngõ ra DO"""
        indy = self._get_indy()
        if not indy:
            return
        def run_on():
            try:
                for i in range(32):
                    if self.do_states[i] == 0:
                        indy.set_do(i, True)
                        self.do_states[i] = 1
                def ui_up():
                    for idx, badge in self.do_badges.items():
                        badge.config(text="ON", bg=self.accent_green, fg="white")
                    for idx, btn in self.do_buttons.items():
                        btn.config(bg=self.accent_green, text="TẮT (OFF)")
                self._post_ui(ui_up)
            except Exception as e:
                print(f"Lỗi turn_all_do_on: {e}")
        threading.Thread(target=run_on, daemon=True).start()

    def _io_poll_loop(self):
        """Luồng đọc trạng thái I/O định kỳ không gây nghẽn socket"""
        while self.running:
            indy = self._get_indy()
            if indy and getattr(self.robot_panel, 'is_connected', False):
                # Nhường socket hoàn toàn nếu đang Jog hoặc đang chạy chu trình
                if getattr(self.robot_panel, 'jog_holding', False) or getattr(self.robot_panel, 'cycle_running', False):
                    time.sleep(0.5)
                    continue
                try:
                    if indy.lock.acquire(blocking=False):
                        try:
                            dos = indy.get_do()
                            dis = indy.get_di()
                            
                            if isinstance(dos, (list, tuple)):
                                self.do_states = list(dos[:32]) + [0] * max(0, 32 - len(dos[:32]))
                            if isinstance(dis, (list, tuple)):
                                self.di_states = list(dis[:32]) + [0] * max(0, 32 - len(dis[:32]))
                        finally:
                            indy.lock.release()
                            
                        def update_ui():
                            # Cập nhật ma trận DO
                            for idx, badge in self.do_badges.items():
                                val = self.do_states[idx] if idx < len(self.do_states) else 0
                                btn = self.do_buttons.get(idx)
                                if val:
                                    badge.config(text="ON", bg=self.accent_green, fg="white")
                                    if btn:
                                        btn.config(bg=self.accent_green, text="TẮT (OFF)")
                                else:
                                    badge.config(text="OFF", bg="#3d4052", fg="#888899")
                                    if btn:
                                        btn.config(bg=self.accent_gray, text="BẬT (ON)")
                                         
                            # Cập nhật ma trận DI
                            for idx, ind in self.di_indicators.items():
                                val = self.di_states[idx] if idx < len(self.di_states) else 0
                                lbl = self.di_labels.get(idx)
                                if val:
                                    ind.config(fg="#2ecc71")  # Xanh sáng
                                    if lbl:
                                        lbl.config(text="ON (1)", bg=self.accent_green, fg="white")
                                else:
                                    ind.config(fg="#555566")  # Xám mờ
                                    if lbl:
                                        lbl.config(text="OFF (0)", bg="#3d4052", fg="#888899")
                                        
                        self._post_ui(update_ui)
                except Exception:
                    pass
            time.sleep(0.8)
