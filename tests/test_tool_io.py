"""
KỊCH BẢN KIỂM TRA HỆ THỐNG I/O KHÍ NÉN (TOOL KẸP & GIÁC HÚT)
Robot Neuromeka Indy7 - IndyCB Cụm XS6 / XS7
"""

import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from client import UnifiedIndyClient

def main():
    robot_ip = "192.168.0.10"  # Hoặc thay bằng IP thực tế của IndyCB
    print(f"============================================================")
    print(f"  TEST ĐIỀU KHIỂN KHÍ NÉN TOOL KÉP - ROBOT INDY7")
    print(f"============================================================")
    print(f"Đang kết nối tới Robot tại IP: {robot_ip}...")
    
    indy = UnifiedIndyClient(robot_ip)
    if not indy.connect():
        print(f"❌ Không thể kết nối tới Robot tại {robot_ip}!")
        print("Vui lòng kiểm tra cáp mạng Ethernet và nguồn tủ IndyCB.")
        return

    print("✅ Đã kết nối thành công tới Robot!")
    print(f"   Phiên bản IndyDCP: v{indy.version}\n")

    # Mặc định sử dụng Cụm XS6 (NPN Tool Outputs):
    # - IN1 (Kẹp Mềm): TO_1 -> SmartDO_00 (pin 0)
    # - IN2 (Giác Hút): TO_2 -> SmartDO_01 (pin 1)
    
    try:
        print("--- [BƯỚC 1]: KIỂM TRA TOOL KẸP MỀM (IN1 - TO_1) ---")
        print(">> Đang kích hoạt KẸP LẠI (Grip ON)...")
        indy.set_gripper(True, pin=0)
        time.sleep(2.0)

        print(">> Đang kích hoạt NHẢ KẸP (Release OFF)...")
        indy.set_gripper(False, pin=0)
        time.sleep(1.5)

        print("\n--- [BƯỚC 2]: KIỂM TRA GIÁC HÚT CHÂN KHÔNG (IN2 - TO_2) ---")
        print(">> Đang BẬT HÚT CHÂN KHÔNG (Vacuum ON)...")
        indy.set_vacuum(True, pin=1)
        time.sleep(2.0)

        print(">> Đang TẮT HÚT CHÂN KHÔNG (Vacuum OFF)...")
        indy.set_vacuum(False, pin=1)
        time.sleep(1.5)

        print("\n--- [BƯỚC 3]: ĐỌC TRẠNG THÁI CẢM BIẾN (DI SENSORS) ---")
        dis = indy.get_di()
        print(f"Trạng thái 8 cổng DI đầu tiên: {dis[:8]}")
        print(f"  * Cảm biến Kẹp (DI 1): {'ĐANG CHẠM' if dis[0] else 'CHƯA CHẠM'}")
        print(f"  * Cảm biến Chân Không (DI 2): {'ĐẠT ÁP SUẤT' if dis[1] else 'CHƯA ĐẠT'}")

        print("\n✅ HOÀN TẤT KIỂM TRA I/O KHÍ NÉN!")

    except KeyboardInterrupt:
        print("\n■ Đã dừng kiểm tra theo yêu cầu.")
    finally:
        # Đảm bảo an toàn ngắt các van trước khi ngắt kết nối
        try:
            indy.set_do(0, False)
            indy.set_do(1, False)
        except Exception:
            pass
        indy.disconnect()
        print("Đã đóng kết nối Robot an toàn.")

if __name__ == "__main__":
    main()
