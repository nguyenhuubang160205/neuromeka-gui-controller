#!/usr/bin/env python3
#-*- coding: utf-8 -*-
import sys
import threading
import time
import math
import json
import os
import tkinter as tk
from tkinter import messagebox, filedialog

import numpy as np
from scipy.spatial.transform import Rotation as R
from scipy.optimize import minimize

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

# ==================== ĐỘNG HỌC ROBOT INDY7 & DUAL TOOL CAD ====================
def rot_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])

def transform_matrix(xyz, rpy):
    rot = R.from_euler('xyz', rpy).as_matrix()
    T = np.eye(4)
    T[:3, :3] = rot
    T[:3, 3] = xyz
    return T

T_j0 = transform_matrix([0, 0, 0.0775], [0, 0, 0])
T_j1 = transform_matrix([0, -0.109, 0.222], [1.570796327, 1.570796327, 0])
T_j2 = transform_matrix([-0.45, 0, -0.0305], [0, 0, 0])
T_j3 = transform_matrix([-0.267, 0, -0.075], [-1.570796327, 0, 1.570796327])
T_j4 = transform_matrix([0, -0.114, 0.083], [1.570796327, 1.570796327, 0])
T_j5 = transform_matrix([-0.168, 0, 0.069], [-1.570796327, 0, 1.570796327])

TCP_OFFSETS = {
    "flange": transform_matrix([0, 0, 0.060], [0, 0, 0]),
    "suction": transform_matrix([0, 0, 0.200], [0, 0, 0]),         # Tâm núm giác hút CAD
    "gripper": transform_matrix([-0.065, 0, 0.160], [0, 0, 0])     # Tâm 2 má kẹp mềm CAD
}

TORQUE_LIMITS = [431.97, 431.97, 197.23, 79.79, 79.79, 79.79]

def forward_kinematics(q, tcp_mode="suction"):
    q0, q1, q2, q3, q4, q5 = q
    T = T_j0 @ rot_z(q0)
    T = T @ T_j1 @ rot_z(q1)
    T = T @ T_j2 @ rot_z(q2)
    T = T @ T_j3 @ rot_z(q3)
    T = T @ T_j4 @ rot_z(q4)
    T = T @ T_j5 @ rot_z(q5)
    T = T @ TCP_OFFSETS.get(tcp_mode, TCP_OFFSETS["suction"])
    
    pos_mm = T[:3, 3] * 1000.0
    euler_deg = R.from_matrix(T[:3, :3]).as_euler('xyz', degrees=True)
    return pos_mm, euler_deg, T

def inverse_kinematics(target_pos_mm, target_rpy_deg, q_init, tcp_mode="suction"):
    target_pos_m = np.array(target_pos_mm) / 1000.0
    target_rot = R.from_euler('xyz', target_rpy_deg, degrees=True).as_matrix()
    
    def cost(q):
        _, _, T = forward_kinematics(q, tcp_mode)
        pos_err = np.sum((T[:3, 3] - target_pos_m)**2) * 100.0
        rot_err = np.sum((T[:3, :3] - target_rot)**2) * 10.0
        reg = np.sum((q - q_init)**2) * 0.01
        return pos_err + rot_err + reg
        
    bounds = [(-3.05, 3.05)] * 6
    res = minimize(cost, q_init, method='L-BFGS-B', bounds=bounds, options={'maxiter': 50})
    return res.x

def calculate_joint_torques(q, payload_kg, tool_mass_kg=1.45):
    total_load = tool_mass_kg + payload_kg
    g = 9.81
    q0, q1, q2, q3, q4, q5 = q
    r_arm = 0.45 * abs(math.cos(q1)) + 0.35 * abs(math.cos(q1 + q2)) + 0.18 * abs(math.cos(q1 + q2 + q4))
    
    tau1 = (11.4 * 0.2 + total_load * r_arm) * g * abs(math.sin(q1))
    tau2 = (5.8 * 0.25 + total_load * (r_arm - 0.45 * abs(math.cos(q1)))) * g * abs(math.sin(q1 + q2))
    tau3 = total_load * 0.15 * g * abs(math.sin(q3))
    tau4 = (2.1 * 0.08 + total_load * 0.18) * g * abs(math.sin(q4))
    tau5 = total_load * 0.05 * g * abs(math.sin(q5))
    tau0 = 5.0
    
    torques = [tau0, tau1, tau2, tau3, tau4, tau5]
    percent_limits = [(torques[i] / TORQUE_LIMITS[i]) * 100.0 for i in range(6)]
    return torques, percent_limits

# ==================== CUSTOM PROGRESS BAR ====================
class CustomProgressBar(tk.Canvas):
    def __init__(self, parent, width=130, height=14, bg="#1A202C"):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=1, highlightbackground="#4A5568")
        self.w = width
        self.h = height
        self.rect = self.create_rectangle(0, 0, 0, height, fill="#38A169", width=0)
        
    def set_value(self, percent):
        p = max(0.0, min(100.0, float(percent)))
        fill_w = int((p / 100.0) * self.w)
        color = "#38A169" if p < 70 else ("#DD6B20" if p < 90 else "#E53E3E")
        self.coords(self.rect, 0, 0, fill_w, self.h)
        self.itemconfig(self.rect, fill=color)

# ==================== ROS 2 NODE ====================
class IndyRosNode(Node):
    def __init__(self):
        super().__init__('indy_gui_controller_node')
        self.pub = self.create_publisher(JointState, 'joint_states', 10)
        self.joint_names = ['joint0', 'joint1', 'joint2', 'joint3', 'joint4', 'joint5']
        
    def publish_joints(self, positions):
        try:
            msg = JointState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.name = self.joint_names
            msg.position = [float(p) for p in positions]
            self.pub.publish(msg)
        except Exception:
            pass

# ==================== GIAO DIỆN GUI TEACH PENDANT ====================
class IndyGUIApp:
    def __init__(self, root, ros_node):
        self.root = root
        self.node = ros_node
        self.root.title("Indy7 Robot - Teach Pendant & Tool Kep (Giac Hut + Kep Mem)")
        self.root.geometry("900x890")
        self.root.configure(bg="#1A202C")

        self.current_q = [0.0, -0.45, 1.25, 0.0, 0.78, 0.0]
        self.is_running_trajectory = False
        self.updating_ui_internal = False
        self.taught_points = []
        
        self.active_tcp = "suction"
        self.is_vacuum_on = False
        self.is_gripper_clamped = False
        self.payload_kg = 2.0
        self.cart_step_val = 20.0
        self.interp_mode = "joint"

        self.presets = {
            "Zero": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "Home": [0.0, -0.45, 1.25, 0.0, 0.78, 0.0],
            "Pick (Hut)": [0.75, -0.35, 1.05, 0.0, 0.85, 0.0],
            "Place (Kep)": [-0.75, -0.25, 1.15, -1.57, 0.65, 1.57]
        }

        self.create_widgets()
        self.update_all_displays()
        self.publish_timer()

    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#0D1B2A", pady=6)
        header_frame.pack(fill="x")
        title_label = tk.Label(header_frame, text="INDY7 ROBOT - TEACH PENDANT & TOOL KEP CAD", 
                               font=("DejaVu Sans", 12, "bold"), fg="#E0E1DD", bg="#0D1B2A")
        title_label.pack()
        sub_label = tk.Label(header_frame, text="Giac Hut Silicon Bellows & Tay Kep SMC | Giam Sat Dong Luc Hoc & Qua Tai Trong", 
                             font=("DejaVu Sans", 8), fg="#778DA9", bg="#0D1B2A")
        sub_label.pack()

        # Tool Bar
        tool_bar = tk.Frame(self.root, bg="#2D3748", pady=4, padx=8)
        tool_bar.pack(fill="x")
        
        tk.Label(tool_bar, text="Chon TCP:", fg="#F6E05E", bg="#2D3748", font=("DejaVu Sans", 9, "bold")).pack(side="left", padx=4)
        
        self.btn_tcp_suc = tk.Button(tool_bar, text="[x] Giac Hut Bellows (Z+200mm)", bg="#3182CE", fg="white", 
                                     font=("DejaVu Sans", 8, "bold"), relief="solid", command=lambda: self.set_tcp("suction"))
        self.btn_tcp_suc.pack(side="left", padx=3)
        
        self.btn_tcp_grip = tk.Button(tool_bar, text="[ ] Tay Kep Mem SMC (X-65mm, Z+160mm)", bg="#4A5568", fg="white", 
                                      font=("DejaVu Sans", 8, "bold"), relief="flat", command=lambda: self.set_tcp("gripper"))
        self.btn_tcp_grip.pack(side="left", padx=3)

        self.btn_vac = tk.Button(tool_bar, text="GIAC HUT: TAT", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                 relief="raised", padx=6, command=self.toggle_vacuum)
        self.btn_vac.pack(side="right", padx=3)

        self.btn_grip = tk.Button(tool_bar, text="TAY KEP: MO", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                  relief="raised", padx=6, command=self.toggle_gripper)
        self.btn_grip.pack(side="right", padx=3)

        main_container = tk.Frame(self.root, bg="#1A202C")
        main_container.pack(fill="both", expand=True, padx=6, pady=4)

        # ----------------- CỘT TRÁI: ĐIỀU KHIỂN & ĐỘNG LỰC HỌC -----------------
        left_frame = tk.Frame(main_container, width=440, bg="#1A202C")
        left_frame.pack(side="left", fill="both", expand=True, padx=3)

        # Presets
        preset_frame = tk.LabelFrame(left_frame, text=" Tu The Nhanh ", bg="#1A202C", fg="#63B3ED", font=("DejaVu Sans", 8, "bold"), padx=4, pady=3)
        preset_frame.pack(fill="x", pady=2)
        btn_grid = tk.Frame(preset_frame, bg="#1A202C")
        btn_grid.pack(fill="x")
        for name, q_val in self.presets.items():
            tk.Button(btn_grid, text=name, bg="#2B6CB0", fg="white", font=("DejaVu Sans", 8, "bold"),
                      relief="flat", command=lambda q=q_val: self.smooth_move_to(q)).pack(side="left", expand=True, fill="x", padx=1)

        # Switch Mode Frame
        mode_btn_bar = tk.Frame(left_frame, bg="#1A202C", pady=2)
        mode_btn_bar.pack(fill="x")
        
        self.btn_tab_cart = tk.Button(mode_btn_bar, text="TOA DO KHONG GIAN (XYZ - RxRyRz)", bg="#3182CE", fg="white", 
                                      font=("DejaVu Sans", 8, "bold"), relief="solid", command=lambda: self.switch_mode("cart"))
        self.btn_tab_cart.pack(side="left", expand=True, fill="x", padx=1)
        
        self.btn_tab_joint = tk.Button(mode_btn_bar, text="GOC KHOP (J0 - J5)", bg="#4A5568", fg="white", 
                                       font=("DejaVu Sans", 8, "bold"), relief="flat", command=lambda: self.switch_mode("joint"))
        self.btn_tab_joint.pack(side="left", expand=True, fill="x", padx=1)

        # Container for Joint & Cartesian controls
        self.ctrl_container = tk.Frame(left_frame, bg="#1A202C")
        self.ctrl_container.pack(fill="x", pady=2)

        self.cart_panel = tk.Frame(self.ctrl_container, bg="#1A202C")
        self.joint_panel = tk.Frame(self.ctrl_container, bg="#1A202C")
        
        self.build_cartesian_panel()
        self.build_joint_panel()
        self.cart_panel.pack(fill="x")

        # Giám sát Động lực học & Payload
        dyn_frame = tk.LabelFrame(left_frame, text=" Giam Sat Trong Luc & Tai Trong (Dynamics) ", 
                                  bg="#1A202C", fg="#F6E05E", font=("DejaVu Sans", 8, "bold"), padx=6, pady=4)
        dyn_frame.pack(fill="x", pady=3)

        payload_row = tk.Frame(dyn_frame, bg="#1A202C")
        payload_row.pack(fill="x", pady=1)
        tk.Label(payload_row, text="Tai gap (Payload):", bg="#1A202C", fg="white", font=("DejaVu Sans", 8, "bold")).pack(side="left")
        
        self.payload_scale = tk.Scale(payload_row, from_=0.0, to=10.0, resolution=0.5, orient="horizontal",
                                      bg="#2D3748", fg="white", highlightthickness=0, command=self.on_payload_change)
        self.payload_scale.set(2.0)
        self.payload_scale.pack(side="left", fill="x", expand=True, padx=4)
        
        self.payload_lbl = tk.Label(payload_row, text="2.0kg (+Tool 1.45kg)", bg="#1A202C", fg="#63B3ED", font=("DejaVu Sans Mono", 8, "bold"))
        self.payload_lbl.pack(side="left")

        # Torque Bars
        torque_grid = tk.Frame(dyn_frame, bg="#1A202C")
        torque_grid.pack(fill="x", pady=2)
        self.torque_bars = []
        self.torque_lbls = []
        for i in range(6):
            t_row = tk.Frame(torque_grid, bg="#1A202C")
            t_row.pack(fill="x", pady=1)
            tk.Label(t_row, text=f"J{i}:", width=3, bg="#1A202C", fg="#CBD5E0", font=("DejaVu Sans", 8, "bold")).pack(side="left")
            
            pbar = CustomProgressBar(t_row, width=130, height=12)
            pbar.pack(side="left", fill="x", expand=True, padx=4)
            self.torque_bars.append(pbar)
            
            tlbl = tk.Label(t_row, text="0.0 Nm (0%)", width=15, anchor="e", bg="#1A202C", fg="#E2E8F0", font=("DejaVu Sans Mono", 8))
            tlbl.pack(side="left")
            self.torque_lbls.append(tlbl)

        self.overload_warning = tk.Label(dyn_frame, text="Trang thai: An toan (Tai tong 3.45kg / 7.0kg)", 
                                         bg="#1A202C", fg="#48BB78", font=("DejaVu Sans", 8, "bold"))
        self.overload_warning.pack(fill="x", pady=2)

        # Nút Teach điểm
        self.btn_teach = tk.Button(left_frame, text="+ DAY VI TRI NAY (TEACH POINT)", bg="#D69E2E", fg="#1A202C",
                                   font=("DejaVu Sans", 10, "bold"), relief="raised", height=2, command=self.teach_current_point)
        self.btn_teach.pack(fill="x", pady=3)

        # ----------------- CỘT PHẢI: BẢNG DANH SÁCH ĐIỂM & CHẠY QUỸ ĐẠO -----------------
        right_frame = tk.Frame(main_container, width=420, bg="#1A202C")
        right_frame.pack(side="right", fill="both", expand=True, padx=3)

        list_frame = tk.LabelFrame(right_frame, text=" Danh Sach Diem Quy Dao (Waypoints) ", 
                                   bg="#1A202C", fg="#63B3ED", font=("DejaVu Sans", 8, "bold"), padx=4, pady=3)
        list_frame.pack(fill="both", expand=True, pady=2)

        # Listbox with Scrollbar
        list_container = tk.Frame(list_frame, bg="#1A202C")
        list_container.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(list_container, bg="#2D3748", fg="#E2E8F0", selectbackground="#3182CE",
                                  selectforeground="white", font=("DejaVu Sans Mono", 9), height=10, relief="flat")
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Nút thao tác danh sách điểm
        list_btn_frame = tk.Frame(list_frame, bg="#1A202C", pady=2)
        list_btn_frame.pack(fill="x")
        tk.Button(list_btn_frame, text="Den Diem", bg="#3182CE", fg="white", font=("DejaVu Sans", 8),
                  relief="flat", command=self.preview_selected_point).pack(side="left", expand=True, fill="x", padx=1)
        tk.Button(list_btn_frame, text="Xoa Diem", bg="#E53E3E", fg="white", font=("DejaVu Sans", 8),
                  relief="flat", command=self.delete_selected_point).pack(side="left", expand=True, fill="x", padx=1)
        tk.Button(list_btn_frame, text="Xoa Het", bg="#718096", fg="white", font=("DejaVu Sans", 8),
                  relief="flat", command=self.clear_all_points).pack(side="left", expand=True, fill="x", padx=1)

        file_frame = tk.Frame(list_frame, bg="#1A202C", pady=1)
        file_frame.pack(fill="x")
        tk.Button(file_frame, text="Luu File JSON", bg="#4A5568", fg="white", font=("DejaVu Sans", 8),
                  relief="flat", command=self.save_to_file).pack(side="left", expand=True, fill="x", padx=1)
        tk.Button(file_frame, text="Nap File JSON", bg="#4A5568", fg="white", font=("DejaVu Sans", 8),
                  relief="flat", command=self.load_from_file).pack(side="left", expand=True, fill="x", padx=1)

        # Cấu hình Quỹ đạo
        ctrl_frame = tk.LabelFrame(right_frame, text=" Thuc Thi Quy Dao ", 
                                   bg="#1A202C", fg="#48BB78", font=("DejaVu Sans", 8, "bold"), padx=4, pady=3)
        ctrl_frame.pack(fill="x", pady=2)

        interp_frame = tk.Frame(ctrl_frame, bg="#1A202C")
        interp_frame.pack(fill="x", pady=1)
        self.btn_mode_joint = tk.Button(interp_frame, text="[x] Khop (S-Curve)", bg="#2B6CB0", fg="white",
                                        font=("DejaVu Sans", 8), relief="solid", command=lambda: self.set_interp_mode("joint"))
        self.btn_mode_joint.pack(side="left", padx=4)
        
        self.btn_mode_line = tk.Button(interp_frame, text="[ ] Duong Thang (Cartesian Line)", bg="#4A5568", fg="white",
                                       font=("DejaVu Sans", 8), relief="flat", command=lambda: self.set_interp_mode("linear"))
        self.btn_mode_line.pack(side="left", padx=4)

        time_row = tk.Frame(ctrl_frame, bg="#1A202C")
        time_row.pack(fill="x", pady=2)
        tk.Label(time_row, text="Thoi gian giua 2 diem (s):", bg="#1A202C", fg="white", font=("DejaVu Sans", 8)).pack(side="left")
        self.time_entry = tk.Entry(time_row, width=6, bg="#2D3748", fg="white", insertbackground="white", justify="center")
        self.time_entry.insert(0, "2.0")
        self.time_entry.pack(side="right")

        loop_frame = tk.Frame(ctrl_frame, bg="#1A202C")
        loop_frame.pack(fill="x", pady=1)
        self.loop_enabled = True
        self.btn_loop = tk.Button(loop_frame, text="[x] Lap vong vo han (Continuous Loop)", bg="#2D3748", fg="#63B3ED",
                                  font=("DejaVu Sans", 8), relief="flat", command=self.toggle_loop)
        self.btn_loop.pack(anchor="w")

        btn_action_frame = tk.Frame(ctrl_frame, bg="#1A202C", pady=3)
        btn_action_frame.pack(fill="x")
        self.btn_play_taught = tk.Button(btn_action_frame, text="> CHAY QUY DAO", bg="#38A169", fg="white",
                                         font=("DejaVu Sans", 10, "bold"), relief="raised", height=2, command=self.start_taught_trajectory)
        self.btn_play_taught.pack(side="left", expand=True, fill="x", padx=2)

        self.btn_stop = tk.Button(btn_action_frame, text="[] DUNG", bg="#E53E3E", fg="white",
                                  font=("DejaVu Sans", 10, "bold"), relief="raised", height=2, state="disabled", command=self.stop_trajectory)
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=2)

        # Status Bar
        self.status_var = tk.StringVar(value="Trang thai: San sang - Tool Kep CAD 3D da kich hoat.")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief="sunken", anchor="w",
                              bg="#2D3748", fg="#CBD5E0", font=("DejaVu Sans", 8))
        status_bar.pack(side="bottom", fill="x")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        if self.loop_enabled:
            self.btn_loop.config(text="[x] Lap vong vo han (Continuous Loop)", fg="#63B3ED")
        else:
            self.btn_loop.config(text="[ ] Lap vong vo han (Continuous Loop)", fg="#A0AEC0")

    def set_interp_mode(self, mode):
        self.interp_mode = mode
        if mode == "joint":
            self.btn_mode_joint.config(text="[x] Khop (S-Curve)", bg="#2B6CB0", relief="solid")
            self.btn_mode_line.config(text="[ ] Duong Thang (Cartesian Line)", bg="#4A5568", relief="flat")
        else:
            self.btn_mode_joint.config(text="[ ] Khop (S-Curve)", bg="#4A5568", relief="flat")
            self.btn_mode_line.config(text="[x] Duong Thang (Cartesian Line)", bg="#2B6CB0", relief="solid")

    def set_tcp(self, tcp_type):
        self.active_tcp = tcp_type
        if tcp_type == "suction":
            self.btn_tcp_suc.config(text="[x] Giac Hut Bellows (Z+200mm)", bg="#3182CE", relief="solid")
            self.btn_tcp_grip.config(text="[ ] Tay Kep Mem SMC (X-65mm, Z+160mm)", bg="#4A5568", relief="flat")
        else:
            self.btn_tcp_suc.config(text="[ ] Giac Hut Bellows (Z+200mm)", bg="#4A5568", relief="flat")
            self.btn_tcp_grip.config(text="[x] Tay Kep Mem SMC (X-65mm, Z+160mm)", bg="#3182CE", relief="solid")
        self.update_cartesian_displays()
        self.status_var.set(f"Da chuyen diem lam viec sang: {self.active_tcp.upper()}")

    def switch_mode(self, mode):
        if mode == "cart":
            self.joint_panel.pack_forget()
            self.cart_panel.pack(fill="x")
            self.btn_tab_cart.config(bg="#3182CE", relief="solid")
            self.btn_tab_joint.config(bg="#4A5568", relief="flat")
        else:
            self.cart_panel.pack_forget()
            self.joint_panel.pack(fill="x")
            self.btn_tab_joint.config(bg="#3182CE", relief="solid")
            self.btn_tab_cart.config(bg="#4A5568", relief="flat")

    def build_joint_panel(self):
        self.joint_scales = []
        self.joint_val_labels = []
        for i in range(6):
            row = tk.Frame(self.joint_panel, bg="#1A202C")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"J{i}:", width=4, bg="#1A202C", fg="#CBD5E0", font=("DejaVu Sans", 8, "bold")).pack(side="left")
            
            scale = tk.Scale(row, from_=-3.05, to=3.05, resolution=0.01, orient="horizontal",
                             bg="#2D3748", fg="white", highlightthickness=0,
                             command=lambda val, idx=i: self.on_joint_scale_change(idx, val))
            scale.set(self.current_q[i])
            scale.pack(side="left", fill="x", expand=True, padx=4)
            self.joint_scales.append(scale)

            val_lbl = tk.Label(row, text="0 deg", width=7, anchor="e", bg="#1A202C", fg="#63B3ED", font=("DejaVu Sans Mono", 8))
            val_lbl.pack(side="left")
            self.joint_val_labels.append(val_lbl)

    def build_cartesian_panel(self):
        step_row = tk.Frame(self.cart_panel, bg="#1A202C")
        step_row.pack(fill="x", pady=1)
        tk.Label(step_row, text="Buoc:", bg="#1A202C", fg="white", font=("DejaVu Sans", 8, "bold")).pack(side="left")
        
        self.step_buttons = {}
        for step_val in [5, 10, 20, 50]:
            bg_c = "#3182CE" if step_val == 20 else "#4A5568"
            b = tk.Button(step_row, text=f"{step_val}mm", bg=bg_c, fg="white", font=("DejaVu Sans", 7, "bold"),
                          padx=4, relief="flat", command=lambda s=step_val: self.set_step_val(s))
            b.pack(side="left", padx=2)
            self.step_buttons[step_val] = b

        # Position (X, Y, Z)
        pos_group = tk.LabelFrame(self.cart_panel, text=" Vi Tri Dau Tool (Position XYZ) ", bg="#1A202C", fg="#E2E8F0", font=("DejaVu Sans", 8))
        pos_group.pack(fill="x", pady=1)

        self.cart_pos_labels = {}
        for axis, color in [('X', '#E53E3E'), ('Y', '#38A169'), ('Z', '#3182CE')]:
            row = tk.Frame(pos_group, bg="#1A202C")
            row.pack(fill="x", pady=1)
            lbl = tk.Label(row, text=f"{axis}:", width=3, fg=color, bg="#1A202C", font=("DejaVu Sans", 9, "bold"))
            lbl.pack(side="left")

            btn_minus = tk.Button(row, text=f" - {axis} ", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                  relief="raised", command=lambda a=axis, d=-1: self.jog_cartesian(a, d))
            btn_minus.pack(side="left", padx=1)

            val_lbl = tk.Label(row, text="0.0 mm", width=12, anchor="center", font=("DejaVu Sans Mono", 9, "bold"), bg="#2D3748", fg="white")
            val_lbl.pack(side="left", padx=3, fill="x", expand=True)
            self.cart_pos_labels[axis] = val_lbl

            btn_plus = tk.Button(row, text=f" + {axis} ", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                 relief="raised", command=lambda a=axis, d=1: self.jog_cartesian(a, d))
            btn_plus.pack(side="left", padx=1)

        # Orientation (Rx, Ry, Rz)
        rot_group = tk.LabelFrame(self.cart_panel, text=" Huong Goc (Rx, Ry, Rz) ", bg="#1A202C", fg="#E2E8F0", font=("DejaVu Sans", 8))
        rot_group.pack(fill="x", pady=1)

        self.cart_rot_labels = {}
        for axis, color in [('Rx', '#DD6B20'), ('Ry', '#805AD5'), ('Rz', '#D69E2E')]:
            row = tk.Frame(rot_group, bg="#1A202C")
            row.pack(fill="x", pady=1)
            lbl = tk.Label(row, text=f"{axis}:", width=3, fg=color, bg="#1A202C", font=("DejaVu Sans", 9, "bold"))
            lbl.pack(side="left")

            btn_minus = tk.Button(row, text=f" - {axis} ", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                  relief="raised", command=lambda a=axis, d=-1: self.jog_cartesian_rot(a, d))
            btn_minus.pack(side="left", padx=1)

            val_lbl = tk.Label(row, text="0.0 deg", width=12, anchor="center", font=("DejaVu Sans Mono", 9, "bold"), bg="#2D3748", fg="white")
            val_lbl.pack(side="left", padx=3, fill="x", expand=True)
            self.cart_rot_labels[axis] = val_lbl

            btn_plus = tk.Button(row, text=f" + {axis} ", bg="#4A5568", fg="white", font=("DejaVu Sans", 8, "bold"),
                                 relief="raised", command=lambda a=axis, d=1: self.jog_cartesian_rot(a, d))
            btn_plus.pack(side="left", padx=1)

    def set_step_val(self, val):
        self.cart_step_val = float(val)
        for s, btn in self.step_buttons.items():
            if s == val:
                btn.config(bg="#3182CE")
            else:
                btn.config(bg="#4A5568")

    def toggle_vacuum(self):
        self.is_vacuum_on = not self.is_vacuum_on
        if self.is_vacuum_on:
            self.btn_vac.config(text="GIAC HUT: BAT", bg="#3182CE")
        else:
            self.btn_vac.config(text="GIAC HUT: TAT", bg="#4A5568")

    def toggle_gripper(self):
        self.is_gripper_clamped = not self.is_gripper_clamped
        if self.is_gripper_clamped:
            self.btn_grip.config(text="TAY KEP: DONG", bg="#DD6B20")
        else:
            self.btn_grip.config(text="TAY KEP: MO", bg="#4A5568")

    def on_payload_change(self, val):
        self.payload_kg = float(val)
        self.payload_lbl.config(text=f"{self.payload_kg:.1f}kg (+Tool 1.45kg)")
        self.update_dynamics_display()

    def jog_cartesian(self, axis, direction):
        if self.is_running_trajectory:
            return
        step = self.cart_step_val * direction
        pos_mm, rpy_deg, _ = forward_kinematics(self.current_q, self.active_tcp)
        if axis == 'X': pos_mm[0] += step
        elif axis == 'Y': pos_mm[1] += step
        elif axis == 'Z': pos_mm[2] += step

        q_new = inverse_kinematics(pos_mm, rpy_deg, self.current_q, self.active_tcp)
        self.smooth_move_to(q_new, duration=0.35)

    def jog_cartesian_rot(self, axis, direction):
        if self.is_running_trajectory:
            return
        step_deg = 5.0 * direction
        pos_mm, rpy_deg, _ = forward_kinematics(self.current_q, self.active_tcp)
        if axis == 'Rx': rpy_deg[0] += step_deg
        elif axis == 'Ry': rpy_deg[1] += step_deg
        elif axis == 'Rz': rpy_deg[2] += step_deg

        q_new = inverse_kinematics(pos_mm, rpy_deg, self.current_q, self.active_tcp)
        self.smooth_move_to(q_new, duration=0.35)

    def on_joint_scale_change(self, idx, val):
        if not self.is_running_trajectory and not self.updating_ui_internal:
            val_f = float(val)
            self.current_q[idx] = val_f
            self.update_cartesian_displays()
            self.update_dynamics_display()

    def update_all_displays(self):
        self.updating_ui_internal = True
        for i in range(6):
            self.joint_scales[i].set(self.current_q[i])
            deg = math.degrees(self.current_q[i])
            self.joint_val_labels[i].config(text=f"{deg:+.0f} deg")
        self.update_cartesian_displays()
        self.update_dynamics_display()
        self.updating_ui_internal = False

    def update_cartesian_displays(self):
        pos_mm, rpy_deg, _ = forward_kinematics(self.current_q, self.active_tcp)
        self.cart_pos_labels['X'].config(text=f"{pos_mm[0]:+.1f} mm")
        self.cart_pos_labels['Y'].config(text=f"{pos_mm[1]:+.1f} mm")
        self.cart_pos_labels['Z'].config(text=f"{pos_mm[2]:+.1f} mm")
        self.cart_rot_labels['Rx'].config(text=f"{rpy_deg[0]:+.1f} deg")
        self.cart_rot_labels['Ry'].config(text=f"{rpy_deg[1]:+.1f} deg")
        self.cart_rot_labels['Rz'].config(text=f"{rpy_deg[2]:+.1f} deg")

    def update_dynamics_display(self):
        torques, p_limits = calculate_joint_torques(self.current_q, self.payload_kg)
        is_overloaded = False
        max_p = max(p_limits)
        
        for i in range(6):
            self.torque_bars[i].set_value(p_limits[i])
            self.torque_lbls[i].config(text=f"{torques[i]:.1f}Nm ({p_limits[i]:.0f}%)")
            if p_limits[i] >= 100.0 or (self.payload_kg + 1.45) > 7.0:
                is_overloaded = True
                
        if (self.payload_kg + 1.45) > 7.0:
            self.overload_warning.config(
                text=f"CANH BAO QUA TAI: Tong tai {self.payload_kg+1.45:.1f}kg vuot muc 7.0kg!",
                fg="#E53E3E"
            )
        elif is_overloaded:
            self.overload_warning.config(
                text=f"CANH BAO: Momen uon khop dat {max_p:.0f}% gioi han!",
                fg="#DD6B20"
            )
        else:
            self.overload_warning.config(
                text=f"Trang thai: An toan (Tai tong: {self.payload_kg+1.45:.2f}kg / 7.0kg)",
                fg="#48BB78"
            )

    def teach_current_point(self):
        p_name = f"P{len(self.taught_points) + 1}"
        point_joints = list(self.current_q)
        pos_mm, rpy_deg, _ = forward_kinematics(point_joints, self.active_tcp)
        
        actions = []
        if self.is_vacuum_on: actions.append("HUT")
        if self.is_gripper_clamped: actions.append("KEP")
        tool_act = "+".join(actions) if actions else "OFF"
        
        self.taught_points.append({
            "name": p_name,
            "tcp": self.active_tcp,
            "joints": point_joints,
            "pos_mm": list(pos_mm),
            "rpy_deg": list(rpy_deg),
            "vacuum": self.is_vacuum_on,
            "gripper": self.is_gripper_clamped
        })
        
        line_str = f"{p_name:<4} [{self.active_tcp[:3].upper()}] X:{pos_mm[0]:+5.0f} Y:{pos_mm[1]:+5.0f} Z:{pos_mm[2]:+5.0f} | {tool_act}"
        self.listbox.insert("end", line_str)
        self.status_var.set(f"Da luu {p_name} ({self.active_tcp.upper()}: X={pos_mm[0]:.0f}, Y={pos_mm[1]:.0f}, Z={pos_mm[2]:.0f}). Tong: {len(self.taught_points)}")

    def preview_selected_point(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Thong bao", "Vui long chon 1 diem trong danh sach!")
            return
        p = self.taught_points[sel[0]]
        self.smooth_move_to(p["joints"], duration=1.5)

    def delete_selected_point(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.listbox.delete(idx)
        del self.taught_points[idx]
        self.status_var.set(f"Da xoa diem. Con lai {len(self.taught_points)} diem.")

    def clear_all_points(self):
        self.listbox.delete(0, "end")
        self.taught_points.clear()
        self.status_var.set("Da xoa toan bo danh sach diem.")

    def save_to_file(self):
        if not self.taught_points:
            messagebox.showwarning("Canh bao", "Chua co diem nao de luu!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if path:
            with open(path, "w") as f:
                json.dump(self.taught_points, f, indent=2)
            messagebox.showinfo("Thanh cong", f"Da luu {len(self.taught_points)} diem vao file!")

    def load_from_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if path and os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            self.clear_all_points()
            self.taught_points = data
            for p in self.taught_points:
                pos = p.get("pos_mm", [0,0,0])
                actions = []
                if p.get("vacuum", False): actions.append("HUT")
                if p.get("gripper", False): actions.append("KEP")
                tool_act = "+".join(actions) if actions else "OFF"
                tcp_name = p.get("tcp", "suction")[:3].upper()
                line_str = f"{p['name']:<4} [{tcp_name}] X:{pos[0]:+5.0f} Y:{pos[1]:+5.0f} Z:{pos[2]:+5.0f} | {tool_act}"
                self.listbox.insert("end", line_str)
            self.status_var.set(f"Da nap {len(self.taught_points)} diem tu file!")

    def smooth_move_to(self, target_pos, duration=1.5):
        if self.is_running_trajectory:
            return
        def worker():
            start_q = list(self.current_q)
            steps = max(int(duration / 0.02), 5)
            for step in range(steps + 1):
                s = step / steps
                poly = 10 * (s**3) - 15 * (s**4) + 6 * (s**5)
                interp = [start_q[i] + poly * (target_pos[i] - start_q[i]) for i in range(6)]
                self.current_q = interp
                self.root.after(0, self.update_all_displays)
                time.sleep(0.02)
        threading.Thread(target=worker, daemon=True).start()

    def start_taught_trajectory(self):
        if len(self.taught_points) < 2:
            messagebox.showwarning("Canh bao", "Ban can day it nhat 2 diem de tao quy dao!")
            return
            
        self.is_running_trajectory = True
        self.btn_play_taught.config(state="disabled")
        self.btn_teach.config(state="disabled")
        self.btn_stop.config(state="normal")
        
        try:
            duration = float(self.time_entry.get())
        except:
            duration = 2.0
            
        loop = self.loop_enabled
        mode = self.interp_mode
        
        threading.Thread(target=self.taught_trajectory_loop, args=(duration, loop, mode), daemon=True).start()

    def stop_trajectory(self):
        self.is_running_trajectory = False
        self.btn_play_taught.config(state="normal")
        self.btn_teach.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("Trang thai: Da dung quy dao.")

    def taught_trajectory_loop(self, duration, loop, mode):
        wp_idx = 0
        while self.is_running_trajectory:
            next_idx = (wp_idx + 1) % len(self.taught_points)
            p_start = self.taught_points[wp_idx]
            p_target = self.taught_points[next_idx]
            
            if p_start.get("vacuum", False) != self.is_vacuum_on:
                self.root.after(0, self.toggle_vacuum)
            if p_start.get("gripper", False) != self.is_gripper_clamped:
                self.root.after(0, self.toggle_gripper)
                
            self.status_var.set(f"> Di chuyen: {p_start['name']} -> {p_target['name']}...")
            
            steps = int(duration / 0.02)
            
            if mode == "linear":
                pos_start = np.array(p_start["pos_mm"])
                pos_end = np.array(p_target["pos_mm"])
                rpy_start = np.array(p_start["rpy_deg"])
                rpy_end = np.array(p_target["rpy_deg"])
                tcp_type = p_target.get("tcp", "suction")
                
                for step in range(steps + 1):
                    if not self.is_running_trajectory:
                        break
                    s = step / steps
                    poly = 10 * (s**3) - 15 * (s**4) + 6 * (s**5)
                    interp_pos = pos_start + poly * (pos_end - pos_start)
                    interp_rpy = rpy_start + poly * (rpy_end - rpy_start)
                    q_step = inverse_kinematics(interp_pos, interp_rpy, self.current_q, tcp_type)
                    self.current_q = list(q_step)
                    self.root.after(0, self.update_all_displays)
                    time.sleep(0.02)
            else:
                q_start = list(p_start["joints"])
                q_end = list(p_target["joints"])
                for step in range(steps + 1):
                    if not self.is_running_trajectory:
                        break
                    s = step / steps
                    poly = 10 * (s**3) - 15 * (s**4) + 6 * (s**5)
                    interp = [q_start[i] + poly * (q_end[i] - q_start[i]) for i in range(6)]
                    self.current_q = interp
                    self.root.after(0, self.update_all_displays)
                    time.sleep(0.02)

            time.sleep(0.3)
            wp_idx += 1
            if wp_idx >= len(self.taught_points) - 1 and not loop:
                break
                
        self.stop_trajectory()

    def publish_timer(self):
        try:
            if rclpy.ok():
                self.node.publish_joints(self.current_q)
                self.root.after(20, self.publish_timer)
        except Exception:
            pass

def main():
    rclpy.init()
    ros_node = IndyRosNode()
    root = tk.Tk()
    app = IndyGUIApp(root, ros_node)
    
    def on_closing():
        root.destroy()
        try:
            ros_node.destroy_node()
            rclpy.shutdown()
        except:
            pass
            
    root.protocol("WM_DELETE_WINDOW", on_closing)
    threading.Thread(target=lambda: rclpy.spin(ros_node), daemon=True).start()
    root.mainloop()

if __name__ == '__main__':
    main()
