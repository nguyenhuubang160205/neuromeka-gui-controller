#!/usr/bin/env python3
# ==============================================================================
# Script Tự Động Đẩy Toàn Bộ Mã Nguồn Sang Tủ Robot Linux (192.168.0.10)
# ==============================================================================

import os
import sys
import paramiko

ROBOT_IP = "192.168.0.10"
ROBOT_USER = "root"
ROBOT_PASS = "root"
REMOTE_PATH = "/home/user/code_neu_claude"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

def deploy():
    print(f"🚀 Đang kết nối SSH tới Tủ Robot Linux tại {ROBOT_IP}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(ROBOT_IP, username=ROBOT_USER, password=ROBOT_PASS, timeout=5.0)
        print("✓ Đã kết nối thành công SSH vào Robot!")
    except Exception as e:
        print(f"❌ Không thể kết nối tới {ROBOT_IP}: {e}")
        print("👉 Vui lòng đảm bảo dây mạng LAN đã cắm từ máy tính vào tủ Robot và đặt IP máy tính cùng lớp mạng (192.168.0.100).")
        return False

    sftp = client.open_sftp()
    try:
        sftp.mkdir(REMOTE_PATH)
    except Exception:
        pass

    files = [f for f in os.listdir(LOCAL_DIR) if os.path.isfile(os.path.join(LOCAL_DIR, f)) and not f.endswith('.pyc')]
    print(f"📦 Đang truyền {len(files)} tệp mã nguồn sang {REMOTE_PATH}...")
    
    for f in files:
        local_f = os.path.join(LOCAL_DIR, f)
        remote_f = f"{REMOTE_PATH}/{f}"
        sftp.put(local_f, remote_f)
        print(f"  ✓ Đã chép: {f}")

    sftp.close()

    # Phân quyền thực thi trên Linux
    client.exec_command(f"chmod +x {REMOTE_PATH}/*.sh {REMOTE_PATH}/*.py")
    
    print("\n==========================================================")
    print("✅ ĐÃ LƯU & SAO CHÉP TOÀN BỘ MÃ NGUỒN VÀO LINUX ROBOT THÀNH CÔNG!")
    print(f"📁 Thư mục trên Robot: {REMOTE_PATH}")
    print("==========================================================")
    client.close()
    return True

if __name__ == "__main__":
    deploy()
