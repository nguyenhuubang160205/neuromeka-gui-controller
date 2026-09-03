import tkinter as tk
import sys

print("[1] Tk() init...", flush=True)
root = tk.Tk()
root.withdraw()

print("[2] Testing font Ubuntu...", flush=True)
try:
    b1 = tk.Button(root, text="Test1", font=("Ubuntu", 9, "bold"))
    print("Ubuntu font button OK!", flush=True)
except Exception as e:
    print("Ubuntu font error:", e, flush=True)

print("[3] Testing font TkDefaultFont...", flush=True)
try:
    b2 = tk.Button(root, text="Test2", font=("TkDefaultFont", 9, "bold"))
    print("TkDefaultFont button OK!", flush=True)
except Exception as e:
    print("TkDefaultFont error:", e, flush=True)

print("[4] Testing font DejaVu Sans...", flush=True)
try:
    b3 = tk.Button(root, text="Test3", font=("DejaVu Sans", 9, "bold"))
    print("DejaVu Sans button OK!", flush=True)
except Exception as e:
    print("DejaVu Sans error:", e, flush=True)

print("[5] Testing font Helvetica...", flush=True)
try:
    b4 = tk.Button(root, text="Test4", font=("Helvetica", 9, "bold"))
    print("Helvetica button OK!", flush=True)
except Exception as e:
    print("Helvetica error:", e, flush=True)

root.destroy()
print("[6] ALL DONE!", flush=True)
