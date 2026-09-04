"""
Module SafetyZoneManager - Quản lý Vùng Giao Thoa An Toàn & Khóa Liên Động (Spatial Mutex / Interlock)
Dành cho Hệ thống Robot Nấu Phở Tự Động Neuromeka Indy7.
Tuân thủ tiêu chuẩn an toàn không gian làm việc dùng chung theo ISO 10218-2.
"""

import time
import threading
import logging

logger = logging.getLogger("RobotSafetyZone")


class SafetyZoneManager:
    """
    Bộ quản lý vùng an toàn không gian (Spatial Safety Zones).
    Ngăn chặn 2 cánh tay robot va chạm tại các khu vực giao thoa:
    1. ZONE_BOWL_STATION: Khu vực Tô Phở / Bàn ra món (Overlapping Workcell)
    2. ZONE_BOILING_POT: Nồi Nước Sôi Nhúng Phở (Robot 1)
    3. ZONE_BROTH_POT: Nồi Nước Dùng Chan Phở (Robot 2)
    """

    # Danh mục các vùng an toàn chuẩn
    ZONE_BOWL_STATION = "ZONE_BOWL_STATION"
    ZONE_BOILING_POT = "ZONE_BOILING_POT"
    ZONE_BROTH_POT = "ZONE_BROTH_POT"

    def __init__(self):
        self._lock = threading.RLock()
        # Trạng thái vùng: {zone_name: {'owner': robot_id | None, 'entered_at': float | None}}
        self._zones = {
            self.ZONE_BOWL_STATION: {"owner": None, "entered_at": None, "desc": "Khu vực Tô Phở & Bàn Ra Món"},
            self.ZONE_BOILING_POT: {"owner": None, "entered_at": None, "desc": "Khu vực Nồi Nước Sôi Nhúng Phở"},
            self.ZONE_BROTH_POT: {"owner": None, "entered_at": None, "desc": "Khu vực Nồi Nước Dùng Chan Phở"},
        }
        self._listeners = []
        # Tự động giải phóng vùng sau thời gian tối đa để chống Deadlock (mặc định 60s)
        self.max_zone_hold_sec = 60.0

    def add_listener(self, callback):
        """Đăng ký callback nhận thông báo khi trạng thái vùng thay đổi."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self):
        for cb in list(self._listeners):
            try:
                cb(self.get_all_zone_status())
            except Exception as e:
                logger.error(f"Lỗi callback SafetyZoneManager: {e}")

    def request_zone_entry(self, robot_id: str, zone_name: str, timeout_sec: float = 15.0, cancel_cb=None) -> bool:
        """
        Robot yêu cầu xin quyền vào Vùng An Toàn.
        - Nếu vùng đang trống: Cấp quyền ngay lập tức (True).
        - Nếu robot đang chiếm chính vùng này: Cấp quyền (True).
        - Nếu vùng đang bị robot khác chiếm: Chờ trong timeout_sec cho đến khi vùng được giải phóng.
        - Trả về False nếu hết thời gian chờ hoặc bị hủy khẩn.
        """
        start_time = time.time()
        logger.info(f"[{robot_id}] Đang YÊU CẦU xin quyền vào {zone_name} (timeout={timeout_sec}s)...")

        while time.time() - start_time < timeout_sec:
            if cancel_cb and cancel_cb():
                logger.warning(f"[{robot_id}] Hủy xin quyền vào {zone_name} do nhận tín hiệu Cancel!")
                return False

            with self._lock:
                zone = self._zones.get(zone_name)
                if not zone:
                    logger.error(f"Vùng {zone_name} không tồn tại!")
                    return False

                current_owner = zone["owner"]
                # Kiểm tra chống Deadlock nếu chủ cũ chiếm quá lâu
                if current_owner is not None and zone["entered_at"]:
                    hold_duration = time.time() - zone["entered_at"]
                    if hold_duration > self.max_zone_hold_sec:
                        logger.critical(f"PHÁT HIỆN DEADLOCK: [{current_owner}] chiếm {zone_name} quá {hold_duration:.1f}s! Tự động cưỡng chế thu hồi vùng!")
                        zone["owner"] = None
                        zone["entered_at"] = None
                        current_owner = None

                if current_owner is None:
                    # Cấp quyền thành công
                    zone["owner"] = robot_id
                    zone["entered_at"] = time.time()
                    logger.info(f"🟢 CẤP QUYỀN THÀNH CÔNG: [{robot_id}] đã CHIẾM GIỮ {zone_name} an toàn.")
                    self._notify_listeners()
                    return True
                elif current_owner == robot_id:
                    # Đã sở hữu vùng từ trước
                    return True

            time.sleep(0.08)  # Polling nhẹ nhàng 12.5Hz

        logger.warning(f"🔴 [{robot_id}] TIMEOUT {timeout_sec}s khi chờ vào {zone_name}! Vùng vẫn đang bị [{self._zones[zone_name]['owner']}] chiếm giữ.")
        return False

    def release_zone(self, robot_id: str, zone_name: str) -> bool:
        """
        Robot rời khỏi vùng an toàn và giải phóng quyền cho các robot khác.
        """
        with self._lock:
            zone = self._zones.get(zone_name)
            if not zone:
                return False

            if zone["owner"] == robot_id:
                zone["owner"] = None
                zone["entered_at"] = None
                logger.info(f"⚪ [{robot_id}] đã GIẢI PHÓNG {zone_name}. Vùng hiện đang TRỐNG (FREE).")
                self._notify_listeners()
                return True
            elif zone["owner"] is None:
                return True
            else:
                logger.warning(f"[{robot_id}] cố gắng giải phóng {zone_name} nhưng vùng đang thuộc về [{zone['owner']}]!")
                return False

    def release_all_zones_for_robot(self, robot_id: str):
        """Giải phóng toàn bộ vùng đang bị chiếm giữ bởi robot này (dùng khi ngắt kết nối hoặc EMG)."""
        with self._lock:
            changed = False
            for z_name, z_data in self._zones.items():
                if z_data["owner"] == robot_id:
                    z_data["owner"] = None
                    z_data["entered_at"] = None
                    changed = True
                    logger.info(f"⚪ Đã giải phóng khẩn cấp {z_name} cho [{robot_id}].")
            if changed:
                self._notify_listeners()

    def emergency_reset_all_zones(self):
        """Reset toàn bộ vùng về trạng thái rỗng trong tình huống Dừng khẩn cấp."""
        with self._lock:
            for z_data in self._zones.values():
                z_data["owner"] = None
                z_data["entered_at"] = None
            logger.critical("🚨 EMERGENCY: Đã thu hồi và reset toàn bộ Vùng An Toàn về trạng thái RỖNG!")
            self._notify_listeners()

    def get_zone_owner(self, zone_name: str):
        with self._lock:
            return self._zones.get(zone_name, {}).get("owner", None)

    def is_zone_free(self, zone_name: str) -> bool:
        with self._lock:
            return self._zones.get(zone_name, {}).get("owner") is None

    def get_all_zone_status(self) -> dict:
        with self._lock:
            return {
                z_name: {
                    "owner": z_info["owner"],
                    "entered_at": z_info["entered_at"],
                    "desc": z_info["desc"],
                    "is_free": (z_info["owner"] is None),
                }
                for z_name, z_info in self._zones.items()
            }


# Instance Singleton toàn cục để mọi module cùng chia sẻ trạng thái vùng an toàn
global_zone_manager = SafetyZoneManager()
