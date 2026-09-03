"""
Script Python di chuyển Robot Indy7 theo danh sách 5 điểm MoveL (Fillet Radius = 10mm)
- Dùng trực tiếp trong Tab 3 (Python Script Studio) của phần mềm GUI.
"""

# ==============================================================================
# 1. DANH SÁCH 5 ĐIỂM TARGET (Từ bảng dạy điểm của bạn)
# ==============================================================================
TARGET_POINTS = [
    {
        "name": "P1",
        "type": "MoveL",
        "joint": [6.891015, -53.1199, -87.5304, -2.39703, -42.0914, -69.8443],
        "tcp": [0.025738, -0.00134, -0.002, -4.12512, -177.022, 49.16922],
        "speed": 200.0,
        "fillet": True,
        "radius": 10.0
    },
    {
        "name": "P2",
        "type": "MoveL",
        "joint": [13.04086, -76.3533, -30.6563, -1.35018, -76.0076, -65.1728],
        "tcp": [0.242952, -0.00119, -0.00568, -4.25276, -176.963, 49.19697],
        "speed": 200.0,
        "fillet": True,
        "radius": 10.0
    },
    {
        "name": "P3",
        "type": "MoveL",
        "joint": [33.57935, -61.0706, -66.5867, -0.24056, -55.5541, -44.8468],
        "tcp": [0.237531, 0.258374, -0.00494, -4.18266, -176.992, 49.18712],
        "speed": 200.0,
        "fillet": True,
        "radius": 10.0
    },
    {
        "name": "P4",
        "type": "MoveL",
        "joint": [35.58808, -45.0871, -110.553, -0.17573, -27.638, -42.8161],
        "tcp": [0.034975, 0.260454, -0.00338, -4.22754, -176.949, 49.18453],
        "speed": 200.0,
        "fillet": True,
        "radius": 10.0
    },
    {
        "name": "P5",
        "type": "MoveL",
        "joint": [6.891379, -53.1228, -87.5306, -2.3966, -42.0913, -69.8443],
        "tcp": [0.025727, -0.00133, -0.00203, -4.12809, -177.022, 49.16935],
        "speed": 200.0,
        "fillet": True,
        "radius": 10.0
    }
]


# ==============================================================================
# 2. HÀM THỰC THI CHÍNH
# ==============================================================================
def main():
    log("🚀 Bắt đầu thực thi chu trình 5 điểm MoveL...")
    
    # Cách A: Chạy mượt mà toàn bộ quỹ đạo liên tục bằng Waypoint Fillet (Bán kính 10mm)
    log("▶ Đang chạy liên tục quỹ đạo Waypoint Fillet (Radius 10mm)...")
    execute_waypoint_path(TARGET_POINTS)

    log("✓ Đã hoàn tất toàn bộ chu trình di chuyển!")


# Tự động gọi hàm main() khi chạy trong phần mềm
main()
