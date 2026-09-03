import tkinter as tk
from tkinter import ttk
import sys
import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

print("[DBG 1] Initializing Tk root...", flush=True)
root = tk.Tk()
root.geometry("1000x700")
root.update_idletasks()

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

print("[DBG 2] Importing RobotControlPanel...", flush=True)
from robot_panel import RobotControlPanel

print("[DBG 3] Creating RobotControlPanel instance...", flush=True)
rp = RobotControlPanel(notebook, "Robot Indy7", "192.168.0.10")
print("[DBG 4] RobotControlPanel created successfully!", flush=True)
notebook.add(rp, text="Robot")
print("[DBG 5] Added to notebook!", flush=True)

print("[DBG 6] Calling root.update()...", flush=True)
root.update()
print("[DBG 7] SUCCESS! ALL DONE!", flush=True)
