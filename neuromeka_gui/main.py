import sys
import tkinter as tk
from gui import IndyRobotGUI
from client import shutdown_all_clients

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = IndyRobotGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"Ứng dụng dừng: {e}")
    finally:
        shutdown_all_clients()
