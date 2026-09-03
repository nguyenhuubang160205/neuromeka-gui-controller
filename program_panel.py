"""
Giao Diện Lập Trình Chu Trình Robot (Programming Studio Panel)
Hỗ trợ 2 chế độ:
- Chế độ 1: 🧩 Visual Block Program (Soạn thảo cây lệnh logic trực quan: Loop, While, If-Else, DO/DI, Biến)
- Chế độ 2: 🐍 Python Script Studio (Nạp file .py, soạn thảo mã và thực thi trực tiếp)
"""

import os
import time
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from program_engine import (
    Program, ProgramInterpreter, BaseInstruction, InstructionFactory,
    MovePointInstruction, SetDOInstruction, WaitDIInstruction, WaitTimeInstruction,
    SetVarInstruction, LogInstruction, LoopCountInstruction, WhileInstruction,
    IfConditionInstruction, BreakInstruction, ContinueInstruction, StopProgramInstruction
)
from python_runner import PythonScriptRunner, SCRIPT_TEMPLATES


class TextLineNumbers(tk.Canvas):
    """Cột hiển thị số dòng cho Text Editor."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textwidget = None

    def attach(self, text_widget):
        self.textwidget = text_widget

    def redraw(self, *args):
        self.delete("all")

        i = self.textwidget.index("@0,0")
        while True:
            dline = self.textwidget.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.create_text(
                22, y,
                anchor="ne",
                text=linenum,
                fill="#858585",
                font=("Consolas", 10)
            )
            i = self.textwidget.index(f"{i}+1line")


class CustomCodeEditor(tk.Frame):
    """Khung soạn thảo mã nguồn có số dòng và cuộn đồng bộ."""
    def __init__(self, parent, bg_color="#181820", text_color="#f8f8f2"):
        super().__init__(parent, bg=bg_color)
        
        self.linenumbers = TextLineNumbers(self, width=38, bg="#21222c", highlightthickness=0)
        self.text = tk.Text(self, bg=bg_color, fg=text_color, insertbackground="white",
                            font=("Courier", 11), undo=True, wrap="none", bd=0, padx=8, pady=4)
        self.scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self._on_scroll_y)
        self.scrollbar_x = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        
        self.text.configure(yscrollcommand=self._on_text_scroll_y, xscrollcommand=self.scrollbar_x.set)
        self.linenumbers.attach(self.text)
        
        self.linenumbers.pack(side="left", fill="y")
        self.scrollbar_y.pack(side="right", fill="y")
        self.scrollbar_x.pack(side="bottom", fill="x")
        self.text.pack(side="left", fill="both", expand=True)
        
        self.text.bind("<KeyRelease>", self._on_change)
        self.text.bind("<MouseWheel>", self._on_change)
        self.text.bind("<Button-1>", self._on_change)
        
        # Hỗ trợ thụt đầu dòng 4 space khi nhấn Tab
        self.text.bind("<Tab>", self._on_tab)

    def _on_scroll_y(self, *args):
        self.text.yview(*args)
        self.linenumbers.redraw()

    def _on_text_scroll_y(self, *args):
        self.scrollbar_y.set(*args)
        self.linenumbers.redraw()

    def _on_change(self, event=None):
        self.linenumbers.redraw()

    def _on_tab(self, event):
        self.text.insert(tk.INSERT, "    ")
        self.linenumbers.redraw()
        return 'break'

    def get_text(self) -> str:
        return self.text.get("1.0", tk.END)

    def set_text(self, content: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.linenumbers.redraw()


class ProgramStudioPanel(tk.Frame):
    def __init__(self, parent, robot_panel):
        super().__init__(parent)
        self.robot_panel = robot_panel
        self.client = robot_panel.indy

        # Bảng màu Dark Theme đồng nhất
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

        self.current_program = Program("Chu Trình Tự Động Indy7")
        self.program_interpreter: Optional[ProgramInterpreter] = None
        self.python_runner = PythonScriptRunner(
            client_provider=lambda: self.robot_panel.indy,
            saved_targets_provider=lambda: self.robot_panel.saved_targets,
            log_callback=self._log_python_output,
            finish_callback=self._on_python_finished
        )

        self._ui_queue = queue.SimpleQueue()
        self._highlighted_item_id = None

        self.create_widgets()
        self.after(30, self._drain_ui_queue)

    def _post_ui(self, cb):
        self._ui_queue.put(cb)

    def _drain_ui_queue(self):
        for _ in range(32):
            try:
                cb = self._ui_queue.get_nowait()
                cb()
            except queue.Empty:
                break
            except Exception as e:
                print(f"Lỗi _drain_ui_queue ProgramStudio: {e}")
        self.after(30, self._drain_ui_queue)

    def get_targets_dict(self) -> dict:
        raw = getattr(self.robot_panel, 'saved_targets', [])
        return {f"P{i+1}": pt for i, pt in enumerate(raw)}

    def create_widgets(self):
        # Header Tiêu đề
        header_f = tk.Frame(self, bg=self.bg_color)
        header_f.pack(fill="x", padx=15, pady=(8, 4))

        tk.Label(header_f, text="* LẬP TRÌNH CHU TRÌNH ROBOT (PROGRAMMING STUDIO)",
                 font=("Segoe UI", 13, "bold"), bg=self.bg_color, fg="#9b59b6").pack(anchor="w")

        tk.Label(header_f, text="Hỗ trợ 2 chế độ: Lập trình cây khối lệnh (Loop, While, If-Else, DI/DO) hoặc Nạp & Chạy mã nguồn Python (.py)",
                 font=("Segoe UI", 9), bg=self.bg_color, fg="#bdc3c7").pack(anchor="w")

        # Sub-Notebook chứa 2 Chế độ Lập trình
        self.sub_notebook = ttk.Notebook(self)
        self.sub_notebook.pack(fill="both", expand=True, padx=15, pady=6)

        # Tab 1: Visual Block Program
        self.tab_visual = tk.Frame(self.sub_notebook, bg=self.bg_color)
        self.sub_notebook.add(self.tab_visual, text=" 🧩 Lập Trình Khối Lệnh (Visual Tree) ")
        self.create_visual_editor_tab()

        # Tab 2: Python Script Studio
        self.tab_python = tk.Frame(self.sub_notebook, bg=self.bg_color)
        self.sub_notebook.add(self.tab_python, text=" 🐍 Python Script Studio (.py Engine) ")
        self.create_python_editor_tab()

    # ==========================================================================
    # SUB-TAB 1: VISUAL BLOCK EDITOR
    # ==========================================================================

    def create_visual_editor_tab(self):
        main_layout = tk.Frame(self.tab_visual, bg=self.bg_color)
        main_layout.pack(fill="both", expand=True, padx=5, pady=5)

        # Cột Trái: Cây lệnh & Thanh công cụ thao tác
        left_f = tk.Frame(main_layout, bg=self.bg_color)
        left_f.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Toolbar
        tb = tk.Frame(left_f, bg=self.card_color, bd=1, relief="solid")
        tb.pack(fill="x", pady=(0, 5))

        btn_add = tk.Button(tb, text="➕ Thêm Lệnh", font=("Segoe UI", 9, "bold"), bg=self.accent_green, fg="white",
                            command=self.open_add_instruction_dialog)
        btn_add.pack(side="left", padx=4, pady=5)

        btn_edit = tk.Button(tb, text="✏ Sửa Lệnh", font=("Segoe UI", 9, "bold"), bg=self.accent_orange, fg="white",
                             command=self.edit_selected_instruction)
        btn_edit.pack(side="left", padx=4, pady=5)

        btn_del = tk.Button(tb, text="❌ Xóa Lệnh", font=("Segoe UI", 9, "bold"), bg=self.accent_red, fg="white",
                            command=self.delete_selected_instruction)
        btn_del.pack(side="left", padx=4, pady=5)

        btn_up = tk.Button(tb, text="▲ Lên", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                           command=lambda: self.move_instruction(-1))
        btn_up.pack(side="left", padx=4, pady=5)

        btn_down = tk.Button(tb, text="▼ Xuống", font=("Segoe UI", 9, "bold"), bg=self.accent_gray, fg="white",
                             command=lambda: self.move_instruction(1))
        btn_down.pack(side="left", padx=4, pady=5)

        # Lưu & Tải
        btn_open = tk.Button(tb, text="📂 Tải (.json)", font=("Segoe UI", 9), bg="#2980b9", fg="white",
                             command=self.load_visual_program)
        btn_open.pack(side="right", padx=4, pady=5)

        btn_save = tk.Button(tb, text="💾 Lưu (.json)", font=("Segoe UI", 9), bg="#27ae60", fg="white",
                             command=self.save_visual_program)
        btn_save.pack(side="right", padx=4, pady=5)

        btn_exp_py = tk.Button(tb, text="* Xuất Python", font=("Segoe UI", 9, "bold"), bg="#8e44ad", fg="white",
                               command=self.export_visual_to_python)
        btn_exp_py.pack(side="right", padx=4, pady=5)

        # Treeview hiển thị khối lệnh
        tree_frame = tk.Frame(left_f, bg=self.card_color)
        tree_frame.pack(fill="both", expand=True)

        self.prog_tree = ttk.Treeview(tree_frame, columns=("desc",), show="tree", selectmode="browse")
        self.prog_tree.column("#0", width=420, anchor="w")
        self.prog_tree.heading("#0", text="Danh Sách Khối Lệnh Chương Trình")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.prog_tree.yview)
        self.prog_tree.configure(yscrollcommand=tree_scroll_y.set)

        self.prog_tree.pack(side="left", fill="both", expand=True)
        tree_scroll_y.pack(side="right", fill="y")

        self.prog_tree.tag_configure("highlight", background="#2ecc71", foreground="#000000")
        self.prog_tree.tag_configure("loop", foreground="#f1c40f")
        self.prog_tree.tag_configure("if", foreground="#3498db")
        self.prog_tree.tag_configure("motion", foreground="#2ecc71")
        self.prog_tree.tag_configure("io", foreground="#e67e22")

        self.prog_tree.bind("<Double-1>", lambda e: self.edit_selected_instruction())

        # Cột Phải: Bảng điều khiển thực thi & Giám sát biến
        right_f = tk.Frame(main_layout, bg=self.bg_color, width=320)
        right_f.pack(side="right", fill="both", padx=(6, 0))

        # Khung Nút Chạy / Dừng
        run_box = tk.LabelFrame(right_f, text=" Bảng Điều Khiển Thực Thi ", font=("Segoe UI", 10, "bold"),
                                bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        run_box.pack(fill="x", pady=(0, 6))

        self.btn_run_prog = tk.Button(run_box, text="> CHẠY CHƯƠNG TRÌNH", font=("Segoe UI", 11, "bold"),
                                      bg=self.accent_green, fg="white", height=2, command=self.start_visual_program)
        self.btn_run_prog.pack(fill="x", padx=10, pady=5)

        ctrl_row = tk.Frame(run_box, bg=self.card_color)
        ctrl_row.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_pause_prog = tk.Button(ctrl_row, text="⏸ Tạm Dừng", font=("Segoe UI", 9, "bold"),
                                        bg=self.accent_orange, fg="white", state="disabled", command=self.pause_visual_program)
        self.btn_pause_prog.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_stop_prog = tk.Button(ctrl_row, text="■ Dừng Lại", font=("Segoe UI", 9, "bold"),
                                       bg=self.accent_red, fg="white", state="disabled", command=self.stop_visual_program)
        self.btn_stop_prog.pack(side="right", fill="x", expand=True, padx=(3, 0))

        # Khung Giám Sát Biến (Variables Table)
        var_box = tk.LabelFrame(right_f, text=" Giám Sát Biến Số & Trạng Thái ", font=("Segoe UI", 10, "bold"),
                                bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        var_box.pack(fill="both", expand=True, pady=4)

        self.var_listbox = tk.Listbox(var_box, bg="#1e1e24", fg="#f1c40f", font=("Consolas", 10), bd=0)
        self.var_listbox.pack(fill="both", expand=True, padx=8, pady=6)

        # Cập nhật danh sách cây ban đầu
        self.refresh_treeview()

    def refresh_treeview(self):
        """Vẽ lại toàn bộ cây lệnh từ self.current_program."""
        self.prog_tree.delete(*self.prog_tree.get_children())
        self._tree_item_map = {}  # item_id -> instruction

        def insert_recursive(parent_id, inst_list):
            for inst in inst_list:
                tag = "normal"
                if inst.type in ("MovePoint", "MoveDirect"):
                    tag = "motion"
                elif inst.type in ("LoopCount", "While"):
                    tag = "loop"
                elif inst.type == "IfCondition":
                    tag = "if"
                elif inst.type in ("SetDO", "WaitDI"):
                    tag = "io"

                item_id = self.prog_tree.insert(parent_id, "end", text=inst.display_text(), tags=(tag,), open=True)
                self._tree_item_map[item_id] = inst

                # Nếu là Loop / While
                if hasattr(inst, 'children') and inst.children:
                    insert_recursive(item_id, inst.children)
                # Nếu là IfCondition
                elif isinstance(inst, IfConditionInstruction):
                    if inst.then_children:
                        then_id = self.prog_tree.insert(item_id, "end", text="✅ NHÁNH ĐÚNG (THEN):", tags=("if",), open=True)
                        insert_recursive(then_id, inst.then_children)
                    if inst.else_children:
                        else_id = self.prog_tree.insert(item_id, "end", text="❌ NHÁNH SAI (ELSE):", tags=("if",), open=True)
                        insert_recursive(else_id, inst.else_children)

        insert_recursive("", self.current_program.instructions)

    def _get_selected_instruction(self):
        sel = self.prog_tree.selection()
        if not sel:
            return None, None
        item_id = sel[0]
        inst = self._tree_item_map.get(item_id)
        return item_id, inst

    def open_add_instruction_dialog(self):
        """Mở hộp thoại thêm lệnh mới vào chương trình."""
        dlg = tk.Toplevel(self)
        dlg.title("➕ Thêm Khối Lệnh Mới")
        dlg.geometry("540x480")
        dlg.configure(bg=self.bg_color)
        dlg.transient(self)
        dlg.resizable(False, False)

        tk.Label(dlg, text="CHỌN LOẠI KHỐI LỆNH ĐIỀU KHIỂN", font=("Segoe UI", 12, "bold"),
                 bg=self.bg_color, fg="#9b59b6").pack(pady=10)

        type_var = tk.StringVar(value="MovePoint")
        type_combo = ttk.Combobox(
            dlg, textvariable=type_var,
            values=[
                "MovePoint - Di Chuyển Điểm (MoveJ / MoveL)",
                "SetDO - Bật/Tắt Ngõ Ra Số (Digital Output)",
                "WaitDI - Chờ Cảm Biến Ngõ Vào (Digital Input)",
                "WaitTime - Tạm Dừng Nghỉ (Delay)",
                "SetVar - Gán & Tính Toán Biến Số",
                "LoopCount - Vòng Lặp Lặp Đi Lặp Lại (Loop N Lần)",
                "While - Vòng Lặp Có Điều Kiện (While)",
                "IfCondition - Rẽ Nhánh Điều Kiện (IF - ELSE)",
                "Log - Ghi Thông Báo Nhật Ký",
                "Break - Thoát Vòng Lặp",
                "Continue - Bỏ Qua Sang Vòng Lặp Tiếp",
                "StopProgram - Dừng Chương Trình"
            ],
            state="readonly", font=("Segoe UI", 10), width=45
        )
        type_combo.pack(pady=5)

        form_frame = tk.LabelFrame(dlg, text=" Cấu hình tham số lệnh ", font=("Segoe UI", 10, "bold"),
                                   bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        form_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Dynamic widgets
        form_widgets = {}

        def update_form(*args):
            for w in form_frame.winfo_children():
                w.destroy()
            form_widgets.clear()
            raw_type = type_var.get().split(" - ")[0].strip()

            if raw_type == "MovePoint":
                tk.Label(form_frame, text="Tên Điểm Dạy:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                targets = list(self.get_targets_dict().keys())
                if not targets: targets = ["P1", "P2", "P3"]
                pt_cb = ttk.Combobox(form_frame, values=targets, state="normal", width=12)
                pt_cb.set(targets[0])
                pt_cb.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["target_name"] = pt_cb

                tk.Label(form_frame, text="Kiểu Chuyển Động:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
                mtype_cb = ttk.Combobox(form_frame, values=["MoveJ", "MoveL"], state="readonly", width=12)
                mtype_cb.set("MoveJ")
                mtype_cb.grid(row=1, column=1, padx=10, pady=8, sticky="w")
                form_widgets["motion_type"] = mtype_cb

                tk.Label(form_frame, text="Tốc Độ (mm/s):", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9)).grid(row=2, column=0, padx=10, pady=8, sticky="w")
                sp_ent = tk.Entry(form_frame, width=14, bg="#1e1e24", fg="white")
                sp_ent.insert(0, "200")
                sp_ent.grid(row=2, column=1, padx=10, pady=8, sticky="w")
                form_widgets["speed"] = sp_ent

            elif raw_type == "SetDO":
                tk.Label(form_frame, text="Chân DO (0..31):", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                pin_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                pin_ent.insert(0, "0")
                pin_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["pin"] = pin_ent

                tk.Label(form_frame, text="Trạng Thái:", bg=self.card_color, fg=self.text_color).grid(row=1, column=0, padx=10, pady=8, sticky="w")
                st_cb = ttk.Combobox(form_frame, values=["ON (BẬT / True)", "OFF (TẮT / False)"], state="readonly", width=16)
                st_cb.set("ON (BẬT / True)")
                st_cb.grid(row=1, column=1, padx=10, pady=8, sticky="w")
                form_widgets["state"] = st_cb

            elif raw_type == "WaitDI":
                tk.Label(form_frame, text="Chân Cảm Biến DI (0..31):", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                pin_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                pin_ent.insert(0, "0")
                pin_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["pin"] = pin_ent

                tk.Label(form_frame, text="Giá Trị Chờ:", bg=self.card_color, fg=self.text_color).grid(row=1, column=0, padx=10, pady=8, sticky="w")
                st_cb = ttk.Combobox(form_frame, values=["1 (Kích hoạt)", "0 (Ngắt)"], state="readonly", width=14)
                st_cb.set("1 (Kích hoạt)")
                st_cb.grid(row=1, column=1, padx=10, pady=8, sticky="w")
                form_widgets["state"] = st_cb

                tk.Label(form_frame, text="Timeout (giây, 0=vô hạn):", bg=self.card_color, fg=self.text_color).grid(row=2, column=0, padx=10, pady=8, sticky="w")
                to_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                to_ent.insert(0, "30.0")
                to_ent.grid(row=2, column=1, padx=10, pady=8, sticky="w")
                form_widgets["timeout"] = to_ent

            elif raw_type == "WaitTime":
                tk.Label(form_frame, text="Thời Gian Dừng Nghỉ (giây):", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                sec_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                sec_ent.insert(0, "1.0")
                sec_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["seconds"] = sec_ent

            elif raw_type == "SetVar":
                tk.Label(form_frame, text="Tên Biến:", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                vname_ent = tk.Entry(form_frame, width=14, bg="#1e1e24", fg="white")
                vname_ent.insert(0, "counter")
                vname_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["var_name"] = vname_ent

                tk.Label(form_frame, text="Biểu Thức / Giá Trị:", bg=self.card_color, fg=self.text_color).grid(row=1, column=0, padx=10, pady=8, sticky="w")
                exp_ent = tk.Entry(form_frame, width=22, bg="#1e1e24", fg="white")
                exp_ent.insert(0, "counter + 1")
                exp_ent.grid(row=1, column=1, padx=10, pady=8, sticky="w")
                form_widgets["expression"] = exp_ent

            elif raw_type == "LoopCount":
                tk.Label(form_frame, text="Số Lần Lặp (0=vô tận):", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                cnt_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                cnt_ent.insert(0, "5")
                cnt_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["count"] = cnt_ent

                tk.Label(form_frame, text="Tên Biến Đếm:", bg=self.card_color, fg=self.text_color).grid(row=1, column=0, padx=10, pady=8, sticky="w")
                vname_ent = tk.Entry(form_frame, width=10, bg="#1e1e24", fg="white")
                vname_ent.insert(0, "i")
                vname_ent.grid(row=1, column=1, padx=10, pady=8, sticky="w")
                form_widgets["var_name"] = vname_ent

            elif raw_type in ("While", "IfCondition"):
                tk.Label(form_frame, text="Biểu Thức Điều Kiện:", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                cond_ent = tk.Entry(form_frame, width=28, bg="#1e1e24", fg="white")
                cond_ent.insert(0, "di(0) == 1")
                cond_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["condition"] = cond_ent

                tk.Label(form_frame, text="(Ví dụ: di(0) == 1, counter < 5, flag == True)", font=("Segoe UI", 8),
                         bg=self.card_color, fg="#95a5a6").grid(row=1, column=0, columnspan=2, padx=10, sticky="w")

            elif raw_type == "Log":
                tk.Label(form_frame, text="Nội Dung Ghi Log:", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                msg_ent = tk.Entry(form_frame, width=32, bg="#1e1e24", fg="white")
                msg_ent.insert(0, "Đang xử lý sản phẩm {i}...")
                msg_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["message"] = msg_ent

            elif raw_type == "StopProgram":
                tk.Label(form_frame, text="Lý Do Dừng:", bg=self.card_color, fg=self.text_color).grid(row=0, column=0, padx=10, pady=8, sticky="w")
                msg_ent = tk.Entry(form_frame, width=30, bg="#1e1e24", fg="white")
                msg_ent.insert(0, "Hoàn tất chu trình!")
                msg_ent.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                form_widgets["message"] = msg_ent

        type_combo.bind("<<ComboboxSelected>>", update_form)
        update_form()

        # Comment chung
        comment_row = tk.Frame(dlg, bg=self.bg_color)
        comment_row.pack(fill="x", padx=20, pady=5)
        tk.Label(comment_row, text="Ghi chú (Comment):", bg=self.bg_color, fg="#bdc3c7", font=("Segoe UI", 9)).pack(side="left")
        comment_ent = tk.Entry(comment_row, bg="#1e1e24", fg="white", font=("Segoe UI", 9))
        comment_ent.pack(side="left", fill="x", expand=True, padx=8)

        def save_and_insert():
            raw_type = type_var.get().split(" - ")[0].strip()
            comm = comment_ent.get().strip()
            inst = None

            try:
                if raw_type == "MovePoint":
                    inst = MovePointInstruction(
                        target_name=form_widgets["target_name"].get().strip(),
                        motion_type=form_widgets["motion_type"].get().strip(),
                        speed=float(form_widgets["speed"].get()),
                        comment=comm
                    )
                elif raw_type == "SetDO":
                    inst = SetDOInstruction(
                        pin=int(form_widgets["pin"].get()),
                        state=("ON" in form_widgets["state"].get()),
                        comment=comm
                    )
                elif raw_type == "WaitDI":
                    inst = WaitDIInstruction(
                        pin=int(form_widgets["pin"].get()),
                        state=int(form_widgets["state"].get().split()[0]),
                        timeout=float(form_widgets["timeout"].get()),
                        comment=comm
                    )
                elif raw_type == "WaitTime":
                    inst = WaitTimeInstruction(seconds=float(form_widgets["seconds"].get()), comment=comm)
                elif raw_type == "SetVar":
                    inst = SetVarInstruction(
                        var_name=form_widgets["var_name"].get().strip(),
                        expression=form_widgets["expression"].get().strip(),
                        comment=comm
                    )
                elif raw_type == "LoopCount":
                    inst = LoopCountInstruction(
                        count=int(form_widgets["count"].get()),
                        var_name=form_widgets["var_name"].get().strip(),
                        comment=comm
                    )
                elif raw_type == "While":
                    inst = WhileInstruction(condition=form_widgets["condition"].get().strip(), comment=comm)
                elif raw_type == "IfCondition":
                    inst = IfConditionInstruction(condition=form_widgets["condition"].get().strip(), comment=comm)
                elif raw_type == "Log":
                    inst = LogInstruction(message=form_widgets["message"].get(), comment=comm)
                elif raw_type == "Break":
                    inst = BreakInstruction(comment=comm)
                elif raw_type == "Continue":
                    inst = ContinueInstruction(comment=comm)
                elif raw_type == "StopProgram":
                    inst = StopProgramInstruction(message=form_widgets["message"].get(), comment=comm)

                if inst:
                    # Kiểm tra chèn vào node cha nếu đang chọn node lồng
                    _, sel_inst = self._get_selected_instruction()
                    if sel_inst and hasattr(sel_inst, 'children'):
                        sel_inst.children.append(inst)
                    elif sel_inst and isinstance(sel_inst, IfConditionInstruction):
                        sel_inst.then_children.append(inst)
                    else:
                        self.current_program.add_instruction(inst)

                    self.refresh_treeview()
                    dlg.destroy()
            except Exception as e:
                messagebox.showerror("Lỗi nhập liệu", f"Không thể tạo khối lệnh: {e}", parent=dlg)

        btn_save = tk.Button(dlg, text="✅ THÊM VÀO CHƯƠNG TRÌNH", font=("Segoe UI", 10, "bold"),
                             bg=self.accent_green, fg="white", height=2, command=save_and_insert)
        btn_save.pack(fill="x", padx=20, pady=10)

    def delete_selected_instruction(self):
        _, inst = self._get_selected_instruction()
        if not inst:
            messagebox.showwarning("Chưa chọn lệnh", "Vui lòng bấm chọn một dòng lệnh trong cây để xóa!")
            return

        def remove_rec(inst_list):
            if inst in inst_list:
                inst_list.remove(inst)
                return True
            for item in inst_list:
                if hasattr(item, 'children') and remove_rec(item.children):
                    return True
                if isinstance(item, IfConditionInstruction):
                    if remove_rec(item.then_children) or remove_rec(item.else_children):
                        return True
            return False

        remove_rec(self.current_program.instructions)
        self.refresh_treeview()

    def edit_selected_instruction(self):
        _, inst = self._get_selected_instruction()
        if not inst:
            return
        # Sửa ghi chú đơn giản
        new_comment = tk.simpledialog.askstring("Sửa ghi chú", "Nhập ghi chú mới cho lệnh:", initialvalue=inst.comment, parent=self) if hasattr(tk, 'simpledialog') else None
        if new_comment is not None:
            inst.comment = new_comment
            self.refresh_treeview()

    def move_instruction(self, direction: int):
        _, inst = self._get_selected_instruction()
        if not inst:
            return

        def move_in_list(lst):
            if inst in lst:
                idx = lst.index(inst)
                new_idx = idx + direction
                if 0 <= new_idx < len(lst):
                    lst[idx], lst[new_idx] = lst[new_idx], lst[idx]
                    return True
            for item in lst:
                if hasattr(item, 'children') and move_in_list(item.children):
                    return True
                if isinstance(item, IfConditionInstruction):
                    if move_in_list(item.then_children) or move_in_list(item.else_children):
                        return True
            return False

        move_in_list(self.current_program.instructions)
        self.refresh_treeview()

    def save_visual_program(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lưu Chương Trình Robot (.json)",
            defaultextension=".json",
            filetypes=[("Robot Program Files (*.json)", "*.json"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            self.current_program.save_to_json(path)
            messagebox.showinfo("Thành công", f"Đã lưu chương trình vào tệp:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file: {e}", parent=self)

    def load_visual_program(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Mở Chương Trình Robot (.json)",
            filetypes=[("Robot Program Files (*.json)", "*.json"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            self.current_program = Program.load_from_json(path)
            self.refresh_treeview()
            messagebox.showinfo("Thành công", f"Đã nạp chương trình thành công ({len(self.current_program.instructions)} khối lệnh)!", parent=self)
        except Exception as e:
            messagebox.showerror("Lỗi mở file", f"Không thể mở file: {e}", parent=self)

    def export_visual_to_python(self):
        py_code = self.current_program.to_python_code()
        self.code_editor.set_text(py_code)
        self.sub_notebook.select(self.tab_python)
        messagebox.showinfo("Xuất mã Python", "Đã xuất toàn bộ khối lệnh thành mã nguồn Python và chuyển sang Tab Python Script Studio!", parent=self)

    def start_visual_program(self):
        if not self.current_program.instructions:
            messagebox.showwarning("Cảnh báo", "Chương trình chưa có khối lệnh nào để chạy!", parent=self)
            return

        self.btn_run_prog.config(state="disabled", text="Đang chạy...")
        self.btn_pause_prog.config(state="normal", text="⏸ Tạm Dừng")
        self.btn_stop_prog.config(state="normal")
        self.var_listbox.delete(0, tk.END)

        def log_cb(msg):
            self._post_ui(lambda: self._log_python_output(msg))

        def step_cb(inst):
            def update_hl():
                for item_id, i_obj in self._tree_item_map.items():
                    if i_obj == inst:
                        self.prog_tree.selection_set(item_id)
                        self.prog_tree.see(item_id)
                        break
                # Cập nhật bảng biến
                if self.program_interpreter and self.program_interpreter.context:
                    self.var_listbox.delete(0, tk.END)
                    for k, v in self.program_interpreter.context.variables.items():
                        self.var_listbox.insert(tk.END, f"{k} = {v}")
            self._post_ui(update_hl)

        def finish_cb(success, msg):
            def on_done():
                self.btn_run_prog.config(state="normal", text="> CHẠY CHƯƠNG TRÌNH")
                self.btn_pause_prog.config(state="disabled", text="⏸ Tạm Dừng")
                self.btn_stop_prog.config(state="disabled")
            self._post_ui(on_done)

        self.program_interpreter = ProgramInterpreter(
            program=self.current_program,
            client=self.robot_panel.indy,
            saved_targets_provider=lambda: self.robot_panel.saved_targets,
            log_callback=log_cb,
            step_callback=step_cb,
            finish_callback=finish_cb
        )
        self.program_interpreter.start()

    def pause_visual_program(self):
        if self.program_interpreter and self.program_interpreter.is_running:
            ctx = self.program_interpreter.context
            if ctx and ctx.pause_event.is_set():
                self.program_interpreter.pause()
                self.btn_pause_prog.config(text="> Tiếp Tục", bg=self.accent_green)
            else:
                self.program_interpreter.resume()
                self.btn_pause_prog.config(text="⏸ Tạm Dừng", bg=self.accent_orange)

    def stop_visual_program(self):
        if self.program_interpreter:
            self.program_interpreter.stop()

    # ==========================================================================
    # SUB-TAB 2: PYTHON SCRIPT STUDIO
    # ==========================================================================

    def create_python_editor_tab(self):
        main_layout = tk.Frame(self.tab_python, bg=self.bg_color)
        main_layout.pack(fill="both", expand=True, padx=5, pady=5)

        # Thanh Toolbar Hành động
        tb = tk.Frame(main_layout, bg=self.card_color, bd=1, relief="solid")
        tb.pack(fill="x", pady=(0, 6))

        btn_load_py = tk.Button(tb, text="📂 NẠP FILE PYTHON (.py)", font=("Segoe UI", 9, "bold"), bg="#2980b9", fg="white",
                                command=self.load_python_file)
        btn_load_py.pack(side="left", padx=5, pady=5)

        btn_save_py = tk.Button(tb, text="💾 LƯU FILE SCRIPT (.py)", font=("Segoe UI", 9, "bold"), bg="#27ae60", fg="white",
                                command=self.save_python_file)
        btn_save_py.pack(side="left", padx=5, pady=5)

        tk.Label(tb, text="Chọn Template:", bg=self.card_color, fg=self.text_color, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(15, 5))
        self.template_combo = ttk.Combobox(tb, values=list(SCRIPT_TEMPLATES.keys()), state="readonly", width=34)
        self.template_combo.set(list(SCRIPT_TEMPLATES.keys())[0])
        self.template_combo.pack(side="left", padx=5, pady=5)
        self.template_combo.bind("<<ComboboxSelected>>", self.on_template_selected)

        self.btn_run_py = tk.Button(tb, text="> CHẠY SCRIPT PYTHON", font=("Segoe UI", 10, "bold"), bg=self.accent_green, fg="white",
                                    command=self.run_python_script)
        self.btn_run_py.pack(side="right", padx=6, pady=5)

        self.btn_stop_py = tk.Button(tb, text="■ DỪNG SCRIPT", font=("Segoe UI", 10, "bold"), bg=self.accent_red, fg="white",
                                     command=self.stop_python_script, state="disabled")
        self.btn_stop_py.pack(side="right", padx=6, pady=5)

        # PanedWindow: Trái/Trên là Editor, Phải/Dưới là Terminal Console
        paned = tk.PanedWindow(main_layout, orient="vertical", bg=self.bg_color, sashwidth=4)
        paned.pack(fill="both", expand=True)

        # Code Editor
        self.code_editor = CustomCodeEditor(paned)
        paned.add(self.code_editor, height=350)

        # Gán mã mẫu mặc định
        self.code_editor.set_text(list(SCRIPT_TEMPLATES.values())[0])

        # Terminal Console Output Frame
        console_frame = tk.LabelFrame(paned, text=" Cửa Sổ Terminal Output Console (Realtime Log) ",
                                      font=("Segoe UI", 10, "bold"), bg=self.card_color, fg=self.text_color, bd=1, relief="solid")
        paned.add(console_frame, height=180)

        console_toolbar = tk.Frame(console_frame, bg=self.card_color)
        console_toolbar.pack(fill="x", padx=6, pady=2)

        self.lbl_py_status = tk.Label(console_toolbar, text="Trạng Thái: SẴN SÀNG (IDLE)", font=("Segoe UI", 9, "bold"),
                                      bg=self.card_color, fg="#2ecc71")
        self.lbl_py_status.pack(side="left")

        btn_clear_log = tk.Button(console_toolbar, text="Xóa Console Log", font=("Segoe UI", 8), bg=self.accent_gray, fg="white",
                                  command=self.clear_console_log)
        btn_clear_log.pack(side="right")

        self.console_text = tk.Text(console_frame, bg="#121218", fg="#a6e22e", insertbackground="white",
                                    font=("Consolas", 10), wrap="word", bd=0, padx=8, pady=4)
        console_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=console_scroll.set)

        self.console_text.pack(side="left", fill="both", expand=True)
        console_scroll.pack(side="right", fill="y")

    def on_template_selected(self, event=None):
        name = self.template_combo.get()
        if name in SCRIPT_TEMPLATES:
            ans = messagebox.askyesno("Tải Template", f"Bạn có muốn tải mã mẫu '{name}' vào trình soạn thảo không?\n(Mã cũ sẽ bị thay thế)", parent=self)
            if ans:
                self.code_editor.set_text(SCRIPT_TEMPLATES[name])

    def load_python_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Chọn Tệp Python Script (.py)",
            filetypes=[("Python Files (*.py)", "*.py"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.code_editor.set_text(content)
            self._log_python_output(f"📂 Đã nạp thành công file: {os.path.basename(path)}")
            messagebox.showinfo("Thành công", f"Đã nạp file Python:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", f"Không thể đọc file Python: {e}", parent=self)

    def save_python_file(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lưu Python Script (.py)",
            defaultextension=".py",
            filetypes=[("Python Files (*.py)", "*.py"), ("Tất cả tập tin (*.*)", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.code_editor.get_text())
            self._log_python_output(f"💾 Đã lưu file script: {os.path.basename(path)}")
            messagebox.showinfo("Thành công", f"Đã lưu script thành công vào:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file: {e}", parent=self)

    def run_python_script(self):
        code = self.code_editor.get_text().strip()
        if not code:
            messagebox.showwarning("Cảnh báo", "Trình soạn thảo đang trống! Vui lòng nhập mã Python trước khi chạy.", parent=self)
            return

        self.btn_run_py.config(state="disabled", text="Đang chạy...")
        self.btn_stop_py.config(state="normal")
        self.lbl_py_status.config(text="Trạng Thái: ĐANG CHẠY (RUNNING)", fg="#f1c40f")

        self.python_runner.execute_script(code, file_name="Custom_Robot_Script.py")

    def stop_python_script(self):
        self.python_runner.stop_script()

    def _on_python_finished(self, success: bool, msg: str):
        def ui_done():
            self.btn_run_py.config(state="normal", text="> CHẠY SCRIPT PYTHON")
            self.btn_stop_py.config(state="disabled")
            if success:
                self.lbl_py_status.config(text="Trạng Thái: HOÀN TẤT (COMPLETED)", fg="#2ecc71")
            else:
                self.lbl_py_status.config(text=f"Trạng Thái: LỖI / DỪNG ({msg})", fg="#e74c3c")
        self._post_ui(ui_done)

    def _log_python_output(self, msg: str):
        def append():
            self.console_text.insert(tk.END, msg + "\n")
            self.console_text.see(tk.END)
        self._post_ui(append)

    def clear_console_log(self):
        self.console_text.delete("1.0", tk.END)
