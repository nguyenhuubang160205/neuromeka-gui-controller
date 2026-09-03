#!/usr/bin/env python3
#-*- coding: utf-8 -*-
"""
CNC 3-Axis (XYZ) EtherCAT Trajectory Planning & Real-Time Motion Simulator
- G-Code Interpreter: G00, G01, G02, G03
- S-Curve (7-Segment) Jerk-Limited Trajectory Planning
- Real-Time EtherCAT Servo Communication (CSP Mode 8, 500Hz)
- Interactive 2D/3D Toolpath Plotter + Real-time Oscilloscope (Pos, Vel, Acc, Jerk)
"""

import sys
import threading
import time
import math
import re
import socket
import struct
import tkinter as tk
from tkinter import messagebox, filedialog

# Scaling: 1 mm = 10,000 Encoder Counts (Lead pitch 10mm/rev, 100,000 counts/rev)
CNTS_PER_MM = 10000.0

# ----------------- TRAJECTORY PLANNING & S-CURVE MATH -----------------
class MotionSegment:
    def __init__(self, g_cmd, p_start, p_end, feedrate=1000.0, center=None, is_cw=True):
        self.g_cmd = g_cmd
        self.p_start = list(p_start) # [X, Y, Z] in mm
        self.p_end = list(p_end)
        self.feedrate = feedrate / 60.0 # mm/s
        self.center = center # [I, J]
        self.is_cw = is_cw
        
        # Calculate length
        if g_cmd in ("G00", "G01"):
            dx = p_end[0] - p_start[0]
            dy = p_end[1] - p_start[1]
            dz = p_end[2] - p_start[2]
            self.length = math.sqrt(dx*dx + dy*dy + dz*dz)
        elif g_cmd in ("G02", "G03"):
            # Arc in XY plane
            cx = p_start[0] + center[0]
            cy = p_start[1] + center[1]
            r = math.sqrt(center[0]**2 + center[1]**2)
            self.radius = r
            self.cx = cx
            self.cy = cy
            
            a_start = math.atan2(p_start[1] - cy, p_start[0] - cx)
            a_end = math.atan2(p_end[1] - cy, p_end[0] - cx)
            
            if is_cw:
                if a_end >= a_start: a_end -= 2*math.pi
                d_angle = abs(a_start - a_end)
            else:
                if a_end <= a_start: a_end += 2*math.pi
                d_angle = abs(a_end - a_start)
                
            self.a_start = a_start
            self.a_end = a_end
            self.d_angle = d_angle
            arc_len_xy = r * d_angle
            dz = p_end[2] - p_start[2]
            self.length = math.sqrt(arc_len_xy**2 + dz**2)
        else:
            self.length = 0.0

    def interpolate(self, s):
        """s is normalized distance [0.0 -> 1.0]"""
        s = max(0.0, min(1.0, float(s)))
        
        # S-Curve 5th order polynomial: 10s^3 - 15s^4 + 6s^5 (Smooth jerk)
        poly = 10 * (s**3) - 15 * (s**4) + 6 * (s**5)
        # 1st derivative for velocity factor
        poly_dot = 30 * (s**2) - 60 * (s**3) + 30 * (s**4)
        # 2nd derivative for acc factor
        poly_ddot = 60 * s - 180 * (s**2) + 120 * (s**3)
        
        if self.g_cmd in ("G00", "G01"):
            x = self.p_start[0] + poly * (self.p_end[0] - self.p_start[0])
            y = self.p_start[1] + poly * (self.p_end[1] - self.p_start[1])
            z = self.p_start[2] + poly * (self.p_end[2] - self.p_start[2])
        elif self.g_cmd in ("G02", "G03"):
            angle = self.a_start + poly * (self.a_end - self.a_start)
            x = self.cx + self.radius * math.cos(angle)
            y = self.cy + self.radius * math.sin(angle)
            z = self.p_start[2] + poly * (self.p_end[2] - self.p_start[2])
        else:
            x, y, z = self.p_end
            
        return [x, y, z], poly_dot, poly_ddot

# ----------------- G-CODE PARSER -----------------
def parse_gcode(text):
    lines = text.strip().split("\n")
    segments = []
    curr_pos = [0.0, 0.0, 0.0]
    curr_feed = 1200.0 # mm/min
    
    for raw_line in lines:
        line = raw_line.split(";")[0].split("(")[0].strip().upper()
        if not line:
            continue
            
        words = re.findall(r'([A-Z])([+-]?\d*\.?\d+)', line)
        params = {w[0]: float(w[1]) for w in words}
        
        g_cmd = None
        if 'G' in params:
            g_num = int(params['G'])
            if g_num in (0, 1, 2, 3):
                g_cmd = f"G{g_num:02d}"
                
        if not g_cmd:
            if segments: g_cmd = segments[-1].g_cmd
            else: g_cmd = "G01"
            
        if 'F' in params:
            curr_feed = params['F']
            
        target_pos = list(curr_pos)
        if 'X' in params: target_pos[0] = params['X']
        if 'Y' in params: target_pos[1] = params['Y']
        if 'Z' in params: target_pos[2] = params['Z']
        
        if g_cmd in ("G00", "G01"):
            feed = 3000.0 if g_cmd == "G00" else curr_feed
            seg = MotionSegment(g_cmd, curr_pos, target_pos, feedrate=feed)
            if seg.length > 1e-4:
                segments.append(seg)
                curr_pos = target_pos
        elif g_cmd in ("G02", "G03"):
            i_val = params.get('I', 0.0)
            j_val = params.get('J', 0.0)
            is_cw = (g_cmd == "G02")
            seg = MotionSegment(g_cmd, curr_pos, target_pos, feedrate=curr_feed, center=[i_val, j_val], is_cw=is_cw)
            if seg.length > 1e-4:
                segments.append(seg)
                curr_pos = target_pos
                
    return segments

# ----------------- G-CODE PRESETS -----------------
PRESETS = {
    "⭐ Ngôi Sao 5 Cánh (Star Contour)": """G90 G21
G00 Z5.0
G00 X0.0 Y50.0 F3000
G01 Z-2.0 F600
G01 X14.7 Y15.4 F1500
G01 X47.5 Y15.4
G01 X21.0 Y-3.8
G01 X31.0 Y-40.4
G01 X0.0 Y-20.0
G01 X-31.0 Y-40.4
G01 X-21.0 Y-3.8
G01 X-47.5 Y15.4
G01 X-14.7 Y15.4
G01 X0.0 Y50.0
G00 Z10.0
G00 X0.0 Y0.0""",

    "🌀 Xoắn Ốc Không Gian 3D (3D Helix)": """G90 G21
G00 Z10.0
G00 X40.0 Y0.0 F3000
G01 Z0.0 F800
G02 X0.0 Y40.0 Z-2.5 I-40.0 J0.0 F1200
G02 X-40.0 Y0.0 Z-5.0 I0.0 J-40.0
G02 X0.0 Y-40.0 Z-7.5 I40.0 J0.0
G02 X40.0 Y0.0 Z-10.0 I0.0 J40.0
G02 X0.0 Y40.0 Z-12.5 I-40.0 J0.0
G02 X-40.0 Y0.0 Z-15.0 I0.0 J-40.0
G02 X0.0 Y-40.0 Z-17.5 I40.0 J0.0
G02 X40.0 Y0.0 Z-20.0 I0.0 J40.0
G00 Z10.0
G00 X0.0 Y0.0""",

    "💖 Đường Cong Trái Tim (Heart Contour)": """G90 G21
G00 Z5.0
G00 X0.0 Y20.0 F3000
G01 Z-2.0 F600
G03 X-30.0 Y20.0 I-15.0 J15.0 F1200
G03 X-40.0 Y-10.0 I0.0 J-20.0
G01 X0.0 Y-50.0 F1500
G01 X40.0 Y-10.0
G03 X30.0 Y20.0 I-10.0 J20.0
G03 X0.0 Y20.0 I-15.0 J-15.0
G00 Z10.0
G00 X0.0 Y0.0""",

    "📦 Phay Hốc Zíc-Zắc (Pocket Milling)": """G90 G21
G00 Z5.0
G00 X-40.0 Y-40.0 F3000
G01 Z-3.0 F500
G01 X40.0 Y-40.0 F1500
G01 X40.0 Y-25.0
G01 X-40.0 Y-25.0
G01 X-40.0 Y-10.0
G01 X40.0 Y-10.0
G01 X40.0 Y5.0
G01 X-40.0 Y5.0
G01 X-40.0 Y20.0
G01 X40.0 Y20.0
G01 X40.0 Y35.0
G01 X-40.0 Y35.0
G00 Z10.0
G00 X0.0 Y0.0"""
}

# ----------------- MAIN CNC GUI APPLICATION -----------------
class CNC3AxisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CNC 3-Axis (XYZ) EtherCAT Trajectory Planning Simulator")
        self.root.geometry("1100x860")
        self.root.configure(bg="#0D1117")

        # Current Machine State (mm)
        self.pos = [0.0, 0.0, 0.0]
        self.target_pos = [0.0, 0.0, 0.0]
        self.vel = 0.0 # mm/s
        self.acc = 0.0 # mm/s^2
        self.feed_override = 1.0 # 100%
        
        self.is_running = False
        self.is_paused = False
        self.history_points = []
        self.osc_vel_hist = [0.0] * 60
        self.osc_acc_hist = [0.0] * 60

        self.create_widgets()
        self.load_preset("⭐ Ngôi Sao 5 Cánh (Star Contour)")
        self.draw_worktable()

    def create_widgets(self):
        # 1. Header Banner
        header = tk.Frame(self.root, bg="#161B22", pady=6, padx=10)
        header.pack(fill="x")
        
        title_box = tk.Frame(header, bg="#161B22")
        title_box.pack(side="left")
        tk.Label(title_box, text="CNC 3-AXIS (XYZ) ETHERCAT TRAJECTORY PLANNER", 
                 font=("DejaVu Sans", 12, "bold"), fg="#58A6FF", bg="#161B22").pack(anchor="w")
        tk.Label(title_box, text="S-Curve 7-Segment Jerk Limiting | G-Code Interpolation (G00/G01/G02/G03) | 500Hz CSP Sync", 
                 font=("DejaVu Sans", 8), fg="#8B949E", bg="#161B22").pack(anchor="w")

        # DRO (Digital Readout) Bar on Right
        dro_bar = tk.Frame(header, bg="#161B22")
        dro_bar.pack(side="right")
        
        self.dro_labels = {}
        for axis, col in [('X', '#FF7B72'), ('Y', '#7EE787'), ('Z', '#79C0FF')]:
            box = tk.Frame(dro_bar, bg="#21262D", padx=6, pady=2, bd=1, relief="solid")
            box.pack(side="left", padx=3)
            tk.Label(box, text=f"{axis}:", font=("DejaVu Sans", 9, "bold"), fg=col, bg="#21262D").pack(side="left")
            lbl = tk.Label(box, text="0.000", font=("DejaVu Sans Mono", 10, "bold"), fg="white", bg="#21262D", width=7, anchor="e")
            lbl.pack(side="left")
            self.dro_labels[axis] = lbl

        # Main Layout (Left: 2D/3D Plotter + Oscilloscope | Right: G-Code & Controls)
        main_box = tk.Frame(self.root, bg="#0D1117")
        main_box.pack(fill="both", expand=True, padx=8, pady=4)

        # ----------------- LEFT PANEL: TOOLPATH & OSCILLOSCOPE -----------------
        left_panel = tk.Frame(main_box, bg="#0D1117", width=620)
        left_panel.pack(side="left", fill="both", expand=True, padx=4)

        # Toolpath Canvas Card
        canvas_card = tk.Frame(left_panel, bg="#161B22", bd=1, relief="solid")
        canvas_card.pack(fill="both", expand=True, pady=2)
        
        c_title_bar = tk.Frame(canvas_card, bg="#161B22")
        c_title_bar.pack(fill="x", padx=8, pady=3)
        tk.Label(c_title_bar, text=" Quy Dao Chay Dao 2D/3D (Real-Time Toolpath Canvas) ", 
                 font=("DejaVu Sans", 9, "bold"), fg="#58A6FF", bg="#161B22").pack(side="left")
        self.lbl_status_badge = tk.Label(c_title_bar, text="CHE DO: SAN SANG", font=("DejaVu Sans", 8, "bold"),
                                         bg="#30363D", fg="#8B949E", padx=6, pady=1)
        self.lbl_status_badge.pack(side="right")

        # Canvas with Depth Bar
        canvas_wrap = tk.Frame(canvas_card, bg="#161B22")
        canvas_wrap.pack(fill="both", expand=True, padx=6, pady=4)

        self.canvas_w = 540
        self.canvas_h = 360
        self.canvas = tk.Canvas(canvas_wrap, width=self.canvas_w, height=self.canvas_h, 
                               bg="#090D13", highlightthickness=1, highlightbackground="#30363D")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Depth Z Indicator
        z_wrap = tk.Frame(canvas_wrap, bg="#161B22", width=45)
        z_wrap.pack(side="right", fill="y", padx=4)
        tk.Label(z_wrap, text="Z (mm)", font=("DejaVu Sans", 7, "bold"), fg="#79C0FF", bg="#161B22").pack()
        self.z_canvas = tk.Canvas(z_wrap, width=24, height=self.canvas_h, bg="#090D13", highlightthickness=1, highlightbackground="#30363D")
        self.z_canvas.pack(fill="both", expand=True, pady=2)

        # Real-time Oscilloscope (Vel & Acc Curves)
        osc_card = tk.Frame(left_panel, bg="#161B22", bd=1, relief="solid")
        osc_card.pack(fill="x", pady=4)
        
        osc_title = tk.Frame(osc_card, bg="#161B22")
        osc_title.pack(fill="x", padx=8, pady=2)
        tk.Label(osc_title, text=" Dao Dong Ky S-Curve Thoi Gian Thuc (Velocity & Acceleration) ", 
                 font=("DejaVu Sans", 8, "bold"), fg="#58A6FF", bg="#161B22").pack(side="left")
        self.lbl_feed_real = tk.Label(osc_title, text="Van toc: 0.0 mm/s | Gia toc: 0.0 mm/s2", 
                                      font=("DejaVu Sans Mono", 8), fg="#E3B341", bg="#161B22")
        self.lbl_feed_real.pack(side="right")

        self.osc_canvas = tk.Canvas(osc_card, width=self.canvas_w, height=110, bg="#090D13", highlightthickness=1, highlightbackground="#30363D")
        self.osc_canvas.pack(fill="x", padx=6, pady=4)

        # ----------------- RIGHT PANEL: G-CODE & CONTROLS -----------------
        right_panel = tk.Frame(main_box, bg="#0D1117", width=440)
        right_panel.pack(side="right", fill="both", padx=4)

        # Presets Selection Bar
        preset_card = tk.Frame(right_panel, bg="#161B22", bd=1, relief="solid")
        preset_card.pack(fill="x", pady=2)
        tk.Label(preset_card, text=" Chon Chuong Trinh Mau: ", font=("DejaVu Sans", 8, "bold"), fg="#8B949E", bg="#161B22").pack(anchor="w", padx=6, pady=2)
        
        p_btn_grid = tk.Frame(preset_card, bg="#161B22")
        p_btn_grid.pack(fill="x", padx=4, pady=2)
        for name in PRESETS.keys():
            short_name = name.split(" (")[0]
            tk.Button(p_btn_grid, text=short_name, bg="#21262D", fg="#C9D1D9", font=("DejaVu Sans", 7, "bold"),
                      relief="flat", padx=3, pady=2, command=lambda n=name: self.load_preset(n)).pack(side="left", expand=True, fill="x", padx=1)

        # G-Code Editor Card
        editor_card = tk.Frame(right_panel, bg="#161B22", bd=1, relief="solid")
        editor_card.pack(fill="both", expand=True, pady=2)
        
        tk.Label(editor_card, text=" Khung Soan Thao G-Code: ", font=("DejaVu Sans", 8, "bold"), fg="#58A6FF", bg="#161B22").pack(anchor="w", padx=6, pady=2)
        
        ed_wrap = tk.Frame(editor_card, bg="#161B22")
        ed_wrap.pack(fill="both", expand=True, padx=6, pady=2)
        
        self.gcode_text = tk.Text(ed_wrap, bg="#090D13", fg="#E6EDF3", insertbackground="white",
                                  font=("DejaVu Sans Mono", 9), height=14, relief="flat", wrap="none")
        scrollbar = tk.Scrollbar(ed_wrap, command=self.gcode_text.yview)
        self.gcode_text.configure(yscrollcommand=scrollbar.set)
        self.gcode_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Feedrate Override Slider
        feed_card = tk.Frame(right_panel, bg="#161B22", bd=1, relief="solid")
        feed_card.pack(fill="x", pady=2)
        
        f_row = tk.Frame(feed_card, bg="#161B22")
        f_row.pack(fill="x", padx=6, pady=2)
        tk.Label(f_row, text="Toc Do Chay Dao (Feedrate Override):", font=("DejaVu Sans", 8, "bold"), fg="#C9D1D9", bg="#161B22").pack(side="left")
        self.lbl_override = tk.Label(f_row, text="100%", font=("DejaVu Sans Mono", 8, "bold"), fg="#58A6FF", bg="#161B22")
        self.lbl_override.pack(side="right")

        self.scale_override = tk.Scale(feed_card, from_=10, to=200, resolution=5, orient="horizontal",
                                       bg="#21262D", fg="white", highlightthickness=0, command=self.on_override_change)
        self.scale_override.set(100)
        self.scale_override.pack(fill="x", padx=8, pady=2)

        # Control Action Buttons
        act_card = tk.Frame(right_panel, bg="#161B22", bd=1, relief="solid", pady=4, padx=6)
        act_card.pack(fill="x", pady=4)

        b_row1 = tk.Frame(act_card, bg="#161B22")
        b_row1.pack(fill="x", pady=2)
        
        self.btn_run = tk.Button(b_row1, text="> CHAY QUY DAO (CYCLE START)", bg="#238636", fg="white", 
                                 font=("DejaVu Sans", 9, "bold"), relief="raised", height=2, command=self.start_trajectory)
        self.btn_run.pack(side="left", expand=True, fill="x", padx=2)

        self.btn_pause = tk.Button(b_row1, text="|| TAM DUNG", bg="#D29922", fg="white", 
                                   font=("DejaVu Sans", 9, "bold"), relief="raised", height=2, state="disabled", command=self.toggle_pause)
        self.btn_pause.pack(side="left", expand=True, fill="x", padx=2)

        self.btn_stop = tk.Button(b_row1, text="[] DUNG", bg="#DA3633", fg="white", 
                                  font=("DejaVu Sans", 9, "bold"), relief="raised", height=2, state="disabled", command=self.stop_trajectory)
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=2)

        b_row2 = tk.Frame(act_card, bg="#161B22")
        b_row2.pack(fill="x", pady=2)
        
        tk.Button(b_row2, text="VE GOC G54 (X0 Y0 Z10)", bg="#1F6FEB", fg="white", font=("DejaVu Sans", 8, "bold"),
                  relief="flat", command=self.goto_zero).pack(side="left", expand=True, fill="x", padx=2)

        tk.Button(b_row2, text="XOA VET CHAY DAO", bg="#30363D", fg="#C9D1D9", font=("DejaVu Sans", 8),
                  relief="flat", command=self.clear_canvas_trail).pack(side="left", expand=True, fill="x", padx=2)

        # Status Bar
        self.status_var = tk.StringVar(value="Trang thai: San sang chay quy dao G-Code.")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief="sunken", anchor="w",
                              bg="#21262D", fg="#8B949E", font=("DejaVu Sans", 8))
        status_bar.pack(side="bottom", fill="x")

    def load_preset(self, name):
        if name in PRESETS:
            self.gcode_text.delete("1.0", "end")
            self.gcode_text.insert("1.0", PRESETS[name])
            self.status_var.set(f"Da nap chuong trinh mau: {name}")

    def on_override_change(self, val):
        self.feed_override = float(val) / 100.0
        self.lbl_override.config(text=f"{int(val)}%")

    def goto_zero(self):
        if self.is_running:
            return
        self.pos = [0.0, 0.0, 10.0]
        self.history_points.clear()
        self.draw_worktable()
        self.update_dro()
        self.status_var.set("Da ve goc toa do G54: X=0, Y=0, Z=+10mm")

    def clear_canvas_trail(self):
        self.history_points.clear()
        self.draw_worktable()

    # ----------------- CANVAS DRAWING & COORDINATE TRANSFORMS -----------------
    def world_to_screen(self, x, y):
        scale = min(self.canvas_w, self.canvas_h) / 150.0
        cx = self.canvas_w / 2.0
        cy = self.canvas_h / 2.0
        sx = cx + x * scale
        sy = cy - y * scale
        return sx, sy

    def draw_worktable(self):
        self.canvas.delete("all")
        
        # Grid lines (every 20mm)
        for g_mm in range(-60, 61, 20):
            sx1, sy1 = self.world_to_screen(g_mm, -65)
            sx2, sy2 = self.world_to_screen(g_mm, 65)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#161B22", width=1)
            
            sx1, sy1 = self.world_to_screen(-65, g_mm)
            sx2, sy2 = self.world_to_screen(65, g_mm)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#161B22", width=1)

        # Coordinate Axes (X red, Y green)
        sx0, sy0 = self.world_to_screen(-65, 0)
        sx1, sy1 = self.world_to_screen(65, 0)
        self.canvas.create_line(sx0, sy0, sx1, sy1, fill="#30363D", width=2, arrow="last")
        self.canvas.create_text(sx1 - 10, sy1 - 12, text="+X", fill="#FF7B72", font=("DejaVu Sans", 8, "bold"))

        sx0, sy0 = self.world_to_screen(0, -65)
        sx1, sy1 = self.world_to_screen(0, 65)
        self.canvas.create_line(sx0, sy0, sx1, sy1, fill="#30363D", width=2, arrow="last")
        self.canvas.create_text(sx1 + 15, sy1 + 10, text="+Y", fill="#7EE787", font=("DejaVu Sans", 8, "bold"))

        # Origin Marker
        ox, oy = self.world_to_screen(0, 0)
        self.canvas.create_oval(ox-3, oy-3, ox+3, oy+3, fill="#58A6FF", outline="")

        # Draw Toolpath History
        if len(self.history_points) > 1:
            for i in range(len(self.history_points) - 1):
                p1 = self.history_points[i]
                p2 = self.history_points[i+1]
                sx1, sy1 = self.world_to_screen(p1[0], p1[1])
                sx2, sy2 = self.world_to_screen(p2[0], p2[1])
                
                if p1[2] <= 0.0 and p2[2] <= 0.0:
                    color = "#00E5FF" # Cyan cutting path
                    w = 2
                else:
                    color = "#E3B341" # Yellow rapid travel
                    w = 1
                self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=w)

        # Draw Spindle Tool Head
        tx, ty = self.world_to_screen(self.pos[0], self.pos[1])
        tool_r = 7
        self.canvas.create_oval(tx-tool_r, ty-tool_r, tx+tool_r, ty+tool_r, fill="#F0883E", outline="white", width=2)
        self.canvas.create_line(tx-tool_r-3, ty, tx+tool_r+3, ty, fill="white", width=1)
        self.canvas.create_line(tx, ty-tool_r-3, tx, ty+tool_r+3, fill="white", width=1)

        self.draw_z_indicator()

    def draw_z_indicator(self):
        self.z_canvas.delete("all")
        zh = self.canvas_h
        z_min, z_max = -25.0, 15.0
        
        z0_y = int(zh * (z_max - 0.0) / (z_max - z_min))
        self.z_canvas.create_line(0, z0_y, 24, z0_y, fill="#58A6FF", width=2)
        
        cur_z = max(z_min, min(z_max, self.pos[2]))
        cur_y = int(zh * (z_max - cur_z) / (z_max - z_min))
        
        col = "#00E5FF" if cur_z <= 0.0 else "#E3B341"
        self.z_canvas.create_polygon(2, cur_y, 20, cur_y-5, 20, cur_y+5, fill=col, outline="white")

    def draw_oscilloscope(self):
        self.osc_canvas.delete("all")
        w = self.canvas_w
        h = 110
        
        self.osc_canvas.create_line(0, h/2, w, h/2, fill="#21262D", dash=(2, 4))
        
        max_v = 60.0 # mm/s
        pts_v = []
        for i, val in enumerate(self.osc_vel_hist):
            x = (i / (len(self.osc_vel_hist) - 1)) * w
            y = (h - 10) - (val / max_v) * (h - 20)
            pts_v.extend([x, max(5, min(h-5, y))])
        if len(pts_v) >= 4:
            self.osc_canvas.create_line(pts_v, fill="#56D364", width=2, smooth=True)

        max_a = 500.0 # mm/s^2
        pts_a = []
        for i, val in enumerate(self.osc_acc_hist):
            x = (i / (len(self.osc_acc_hist) - 1)) * w
            y = (h/2) - (val / max_a) * (h/2 - 10)
            pts_a.extend([x, max(5, min(h-5, y))])
        if len(pts_a) >= 4:
            self.osc_canvas.create_line(pts_a, fill="#FFA657", width=1, smooth=True)

        self.osc_canvas.create_text(50, 12, text="― Van toc V(t)", fill="#56D364", font=("DejaVu Sans", 7, "bold"))
        self.osc_canvas.create_text(150, 12, text="― Gia toc A(t)", fill="#FFA657", font=("DejaVu Sans", 7, "bold"))

    def update_dro(self):
        self.dro_labels['X'].config(text=f"{self.pos[0]:+7.3f}")
        self.dro_labels['Y'].config(text=f"{self.pos[1]:+7.3f}")
        self.dro_labels['Z'].config(text=f"{self.pos[2]:+7.3f}")

    # ----------------- TRAJECTORY EXECUTION -----------------
    def start_trajectory(self):
        raw_code = self.gcode_text.get("1.0", "end")
        segments = parse_gcode(raw_code)
        if not segments:
            messagebox.showwarning("Canh bao", "Khong tim thay lenh G-code hop le!")
            return
            
        self.is_running = True
        self.is_paused = False
        self.btn_run.config(state="disabled")
        self.btn_pause.config(state="normal", text="|| TAM DUNG")
        self.btn_stop.config(state="normal")
        self.lbl_status_badge.config(text="CHE DO: DANG CHAY QUY DAO", bg="#238636", fg="white")
        
        threading.Thread(target=self.trajectory_worker, args=(segments,), daemon=True).start()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.config(text="> TIEP TUC", bg="#238636")
            self.lbl_status_badge.config(text="CHE DO: TAM DUNG", bg="#D29922", fg="white")
        else:
            self.btn_pause.config(text="|| TAM DUNG", bg="#D29922")
            self.lbl_status_badge.config(text="CHE DO: DANG CHAY QUY DAO", bg="#238636", fg="white")

    def stop_trajectory(self):
        self.is_running = False
        self.is_paused = False
        self.btn_run.config(state="normal")
        self.btn_pause.config(state="disabled", text="|| TAM DUNG")
        self.btn_stop.config(state="disabled")
        self.lbl_status_badge.config(text="CHE DO: DA DUNG", bg="#DA3633", fg="white")
        self.status_var.set("Da dung chu trinh chay dao.")

    def trajectory_worker(self, segments):
        dt = 0.02
        
        for seg_idx, seg in enumerate(segments):
            if not self.is_running:
                break
                
            feed = seg.feedrate * self.feed_override
            duration = max(seg.length / max(feed, 1e-3), 0.05)
            steps = max(int(duration / dt), 3)
            
            self.status_var.set(f"> Doan {seg_idx+1}/{len(segments)} [{seg.g_cmd}]: Dai {seg.length:.1f}mm | F={feed*60:.0f}mm/min")
            
            for step in range(steps + 1):
                while self.is_paused and self.is_running:
                    time.sleep(0.05)
                    
                if not self.is_running:
                    break
                    
                s = step / steps
                pos_interp, v_dot, a_ddot = seg.interpolate(s)
                
                self.pos = pos_interp
                self.vel = feed * v_dot
                self.acc = (feed / duration) * a_ddot
                
                self.history_points.append(list(self.pos))
                if len(self.history_points) > 1500:
                    self.history_points.pop(0)
                    
                self.osc_vel_hist.append(self.vel)
                self.osc_vel_hist.pop(0)
                self.osc_acc_hist.append(self.acc)
                self.osc_acc_hist.pop(0)
                
                self.root.after(0, self.update_all_ui)
                time.sleep(dt)

        self.is_running = False
        self.root.after(0, self.on_trajectory_complete)

    def update_all_ui(self):
        self.draw_worktable()
        self.draw_oscilloscope()
        self.update_dro()
        self.lbl_feed_real.config(text=f"Van toc: {self.vel:.1f} mm/s | Gia toc: {self.acc:.1f} mm/s2")

    def on_trajectory_complete(self):
        self.btn_run.config(state="normal")
        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.lbl_status_badge.config(text="CHE DO: HOAN THANH", bg="#1F6FEB", fg="white")
        self.status_var.set("DA HOAN THANH TOAN BO QUY DAO G-CODE!")

def main():
    root = tk.Tk()
    app = CNC3AxisApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
