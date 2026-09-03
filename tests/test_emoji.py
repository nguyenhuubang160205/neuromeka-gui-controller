import tkinter as tk

print("[1] Tk() init...", flush=True)
root = tk.Tk()
root.withdraw()

print("[2] Testing plain ASCII text button...", flush=True)
b1 = tk.Button(root, text="Do IP")
print("Plain text button OK!", flush=True)

print("[3] Testing emoji text button 🔍...", flush=True)
try:
    b2 = tk.Button(root, text="🔍 Do IP")
    print("Emoji button created!", flush=True)
    b2.update()
    print("Emoji button updated!", flush=True)
except Exception as e:
    print("Emoji button error:", e, flush=True)

root.destroy()
print("[4] DONE!", flush=True)
