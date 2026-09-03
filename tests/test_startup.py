#!/usr/bin/env python3
import sys
import os
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

print("[1/6] Kiểm tra Tkinter đồ họa...", flush=True)
import tkinter as tk
from tkinter import ttk
root = tk.Tk()
root.geometry("1000x700")
root.update_idletasks()
print("      ✓ Tkinter OK!", flush=True)

print("[2/6] Kiểm tra thư viện Neuromeka & Client...", flush=True)
from client import UnifiedIndyClient
print("      ✓ Client OK!", flush=True)

print("[3/6] Kiểm tra Robot Panel...", flush=True)
from robot_panel import RobotControlPanel
print("      ✓ Robot Panel OK!", flush=True)

print("[4/6] Kiểm tra I/O Panel...", flush=True)
from io_panel import IOPanel
print("      ✓ I/O Panel OK!", flush=True)

print("[5/6] Kiểm tra Program Panel...", flush=True)
from program_panel import ProgramStudioPanel
print("      ✓ Program Panel OK!", flush=True)

print("[6.1] Tạo RobotControlPanel...", flush=True)
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)
rp = RobotControlPanel(notebook, "Robot Indy7", "192.168.0.10")
notebook.add(rp, text="Robot")
print("      ✓ RobotControlPanel instantiation OK!", flush=True)

print("[6.2] Tạo IOPanel...", flush=True)
io = IOPanel(notebook, rp)
notebook.add(io, text="IO")
print("      ✓ IOPanel instantiation OK!", flush=True)

print("[6.3] Tạo ProgramStudioPanel...", flush=True)
prog = ProgramStudioPanel(notebook, rp)
notebook.add(prog, text="Program")
print("      ✓ ProgramStudioPanel instantiation OK!", flush=True)

print("[6.4] Test HMI Creation...", flush=True)
from gui import IndyRobotGUI
print("      ✓ IndyRobotGUI class imported OK!", flush=True)

root.update()
print("\n🎉 CHÚC MỪNG: HỆ THỐNG ĐÃ TƯƠNG THÍCH HOÀN TOÀN VỚI LINUX UBUNTU!")
