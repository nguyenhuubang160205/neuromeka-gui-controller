#!/usr/bin/env bash
# ==============================================================================
# Script Khởi Chạy Tối Ưu Độ Trễ Thấp (Low-Latency) Cho Neuromeka GUI Trên Ubuntu
# ==============================================================================

# Điều hướng tới thư mục chứa script
cd "$(dirname "$0")"

# Thiết lập bảng mã UTF-8 chuẩn
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

echo "=========================================================="
echo "🤖 ĐANG KHỞI ĐỘNG HỆ THỐNG ĐIỀU KHIỂN ROBOT NEUROMEKA INDY7"
echo "🌐 Môi trường: Linux Ubuntu (Low-Latency Socket Engine)"
echo "=========================================================="

# Khởi chạy ứng dụng chính
python3 main.py "$@"
