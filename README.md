# 🤖 Hệ Thống Điều Khiển Robot Neuromeka Indy7 GUI Controller

Giao diện điều khiển công nghiệp (Dual-Robot Indy7 + Dual-Tool Gripper/Vacuum + CNC Simulator) được tối ưu hóa giao diện Dark Mode, chống đơ UI (Non-blocking Threading), hỗ trợ vận hành song song trên Windows và Linux Ubuntu.

---

## 📁 Cấu Trúc Thư Mục Repository

```plaintext
neuromeka-gui-controller/
├── neuromeka_gui/          # 🚀 Toàn bộ mã nguồn chính để chạy GUI điều khiển Robot
│   ├── main.py             # File khởi động ứng dụng chính
│   ├── gui.py              # Khung giao diện chính (IndyRobotGUI)
│   ├── robot_panel.py      # Bảng điều khiển Jog, tọa độ, trạng thái Robot
│   ├── io_panel.py         # Quản lý I/O khí nén (Gripper, Vacuum, Solenoid)
│   ├── program_panel.py    # Giao diện lập trình chu trình tự động (Program Studio)
│   ├── program_engine.py   # Bộ thực thi lệnh chu trình tự động
│   ├── python_runner.py    # Trình chạy kịch bản Python nhúng
│   ├── client.py           # Client kết nối Robot Neuromeka Indy7 (IndySDK)
│   ├── simulated_client.py # Trình giả lập Robot khi không kết nối phần cứng thực
│   ├── server_api.py       # API Socket Server
│   ├── cnc_3axis_simulator.py # Mô phỏng máy CNC 3 trục
│   ├── zone_manager.py     # Quản lý vùng an toàn và cảnh báo va chạm
│   ├── requirements.txt    # Danh sách thư viện phụ thuộc
│   ├── taught_points.json  # Dữ liệu điểm dạy robot (Teaching points)
│   └── run_linux.sh        # Script khởi chạy nhanh trên Ubuntu Linux
├── cad_models/             # 🛠️ Toàn bộ mô hình 3D CAD (.step, .glb, preview)
│   ├── robot_dual_tool_viewer.html # Trình xem 3D Web tương tác
│   ├── robot_dual_tool_preview.png # Ảnh render cụm cơ cấu Tool
│   └── *.step / *.glb      # Chi tiết cơ khí và lắp ghép Dual-Tool
├── docs/                   # 📚 Tài liệu kỹ thuật, hướng dẫn và báo cáo
│   ├── Huong_dan_Giao_dien_GUI.md # Hướng dẫn chi tiết vận hành GUI
│   ├── Huong_dan_Linux_Ubuntu.md  # Cài đặt và cấu hình mạng trên Linux
│   ├── Thuat_Toan_Conveyor_Tracking_Robot_SCARA_QKM.md # Tài liệu thuật toán
│   └── AUDIT_REPORT.md            # Báo cáo kiểm thử và tối ưu hóa hệ thống
└── tests/                  # 🧪 Các script kiểm thử (Unit tests & Debug)
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Ứng Dụng

### 1. Cài đặt thư viện:
```bash
cd neuromeka_gui
pip install -r requirements.txt
```

### 2. Khởi chạy GUI:
```bash
python main.py
```

*(Hoặc chạy trực tiếp trên Linux với `./run_linux.sh`)*

---

## 👨‍💻 Tác Giả / Liên Hệ
- **Nguyễn Hữu Bằng**
- **Đại học Bách Khoa TP.HCM**
