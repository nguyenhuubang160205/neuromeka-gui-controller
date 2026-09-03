#!/usr/bin/env bash
# ==============================================================================
# Script Cài Đặt Môi Trường Tự Động Cho Robot Neuromeka GUI Trên Linux Ubuntu
# Hỗ trợ: Ubuntu 20.04 LTS, Ubuntu 22.04 LTS, Ubuntu 24.04 LTS
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 ĐANG KHỞI TẠO CÀI ĐẶT NEUROMEKA GUI TRÊN LINUX UBUNTU"
echo "=========================================================="

# 1. Cập nhật danh sách gói phần mềm
echo "[1/4] Đang cập nhật gói phần mềm hệ thống (apt update)..."
sudo apt update -y

# 2. Cài đặt Python3, Tkinter và các thư viện hệ thống cần thiết
echo "[2/4] Đang cài đặt Python3, Python3-Tk, pip và net-tools..."
sudo apt install -y python3 python3-pip python3-tk python3-dev build-essential net-tools iproute2

# 3. Cài đặt các thư viện Python
echo "[3/4] Đang cài đặt các thư viện Python chuyên dụng (neuromeka, numpy, paramiko, psutil)..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt --break-system-packages || python3 -m pip install -r requirements.txt

# 4. Cấp quyền thực thi cho các file script
echo "[4/4] Đang phân quyền thực thi cho các tệp script..."
chmod +x run_linux.sh
chmod +x setup_ubuntu.sh

echo "=========================================================="
echo "✅ CÀI ĐẶT HOÀN TẤT THÀNH CÔNG 100%!"
echo "👉 Bạn có thể khởi động giao diện bằng lệnh:"
echo "   ./run_linux.sh"
echo "   hoặc: python3 main.py"
echo "=========================================================="
