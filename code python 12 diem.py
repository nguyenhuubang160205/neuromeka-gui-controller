# ==============================================================================
# Chương trình Robot: Chu Trình Tự Động Indy7 (Cú Pháp ABB Zone / Fillet Chuẩn)
# Mô tả: 5 chu trình lặp lại, bo góc mượt mà theo từng tham số z10, z30, z30
# ==============================================================================

def run_workflow(robot, points):
    robot.log("🚀 Bắt đầu thực thi chương trình (5 chu trình)...")
    
    for loop in range(1, 6):
        robot.log(f"--- Đang thực hiện chu trình {loop}/5 ---")
        
        # ----------------------------------------------------------------------
        # 1. TIẾP CẬN VÀ GẮP PHÔI (Lướt mượt P1, P2 -> Dừng chính xác tại P3)
        # ----------------------------------------------------------------------
        robot.move_j("P1", 700.0, fine)
        robot.move_l("P3", 700.0, fine)  # z30: Dừng cố định tại vị trí gắp
        
        # Thao tác Kẹp / Hút tại P3
        robot.set_do(0, True)
        robot.wait(0.5)
        robot.set_do(0, False)
        
        # ----------------------------------------------------------------------
        # 2. VẬN CHUYỂN PHÔI (Lướt liên tục qua P12, P10, P11, P4, P5, P6, P7 -> Dừng tại P8)
        # ----------------------------------------------------------------------
        robot.move_l("P12", 700.0, z30)
        robot.move_l("P10", 700.0, z30)
        robot.move_l("P11", 700.0, z30)
        robot.move_l("P5", 700.0, z30)
        robot.move_l("P6", 700.0, z30)
        robot.move_l("P7", 700.0, z30)
        robot.move_l("P8", 700.0, z30)  # z30: Dừng cố định tại vị trí nhả
        
        # Thao tác Nhả phôi tại P8
        robot.set_do(1, True)
        robot.wait(0.5)
        robot.set_do(1, False)
        
        # ----------------------------------------------------------------------
        # 3. RÚT VỀ VỊ TRÍ AN TOÀN P9
        # ----------------------------------------------------------------------
        robot.move_j("P9", 700.0, fine)
        
    robot.log("✓ Đã hoàn tất toàn bộ 5 chu trình thành công!")


# Thực thi chương trình
run_workflow(robot, points)




