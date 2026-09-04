"""
Module Trình Chạy Script Python Ngoài (.py Runner Engine)
Cho phép nạp file Python từ bên ngoài, soạn thảo và thực thi script an toàn với đầy đủ API Robot.
"""

import sys
import io
import time
import traceback
import threading
from typing import Optional, Callable, Dict, Any


class RobotScriptAPI:
    """Đối tượng API tiện ích truyền vào namespace của Script Python."""
    def __init__(self, client_provider, saved_targets_provider: Callable[[], dict],
                 log_callback: Optional[Callable[[str], None]] = None,
                 stop_event: Optional[threading.Event] = None):
        self._client_provider = client_provider
        self._saved_targets_provider = saved_targets_provider
        self._log_callback = log_callback
        self._stop_event = stop_event if stop_event is not None else threading.Event()
        self._motion_buffer = []  # Hàng đợi Lookahead gom cụm Fillet Waypoint tự động theo chuẩn ABB

    @property
    def client(self):
        if callable(self._client_provider):
            return self._client_provider()
        return self._client_provider

    def is_stopped(self) -> bool:
        """Kiểm tra xem người dùng có bấm dừng hoặc ngắt khẩn cấp hay không."""
        return self._stop_event.is_set()

    def check_interrupt(self):
        if self._stop_event.is_set():
            raise KeyboardInterrupt("Người dùng đã yêu cầu dừng Script Python!")

    def log(self, message: str):
        """In thông báo ra cửa sổ Console và nhật ký vận hành."""
        if self._log_callback:
            self._log_callback(f"[{time.strftime('%H:%M:%S')}] {message}")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def is_connected(self) -> bool:
        c = self.client
        return bool(c and getattr(c, 'client', None))

    def _resolve_point_data(self, target) -> dict:
        """Tìm dữ liệu điểm từ tên (ví dụ 'P1') hoặc danh sách tọa độ."""
        if isinstance(target, dict):
            return target

        targets = {}
        if callable(self._saved_targets_provider):
            res = self._saved_targets_provider()
            if isinstance(res, dict):
                targets = res
            elif isinstance(res, list):
                targets = {f"P{i+1}": pt for i, pt in enumerate(res)}

        if isinstance(target, str):
            if target in targets:
                return targets[target]
            if target.startswith("P") and target[1:].isdigit():
                idx = int(target[1:]) - 1
                if callable(self._saved_targets_provider):
                    raw = self._saved_targets_provider()
                    if isinstance(raw, list) and 0 <= idx < len(raw):
                        return raw[idx]
            raise ValueError(f"Không tìm thấy điểm '{target}' trong danh sách điểm dạy!")

        elif isinstance(target, (list, tuple)) and len(target) >= 6:
            return {'type': 'MoveL', 'joint': list(target), 'tcp': list(target), 'speed': 200.0}

        raise ValueError(f"Tham số điểm không hợp lệ: {target}")

    def _parse_zone_val(self, zone=None, **kwargs) -> float:
        """Trích xuất bán kính bo góc (mm). fine / 0 = Dừng chính xác tại đích."""
        val = zone
        if val is None:
            val = kwargs.get('z', kwargs.get('radius', kwargs.get('fillet', None)))
        if val is None:
            return 0.0
        if isinstance(val, bool):
            return 10.0 if val else 0.0
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("fine", "0", "z0"):
                return 0.0
            if s.startswith("z") and s[1:].replace('.', '', 1).isdigit():
                return float(s[1:])
        return 0.0

    def _flush_motion_buffer(self):
        """Thực thi toàn bộ các lệnh chuyển động đang chờ trong hàng đợi Lookahead."""
        if not self._motion_buffer:
            return

        self.check_interrupt()
        queue = list(self._motion_buffer)
        self._motion_buffer.clear()

        # Trường hợp 1: Chỉ có đúng 1 điểm trong hàng đợi -> Chạy Move đơn trực tiếp siêu nhanh
        if len(queue) == 1:
            item = queue[0]
            mtype = item['type']
            target = item['target_name']
            speed = item['speed']
            pt_data = item['pt_data']

            if not self.is_connected():
                self.log(f"⚠️ Robot chưa kết nối ở Tab 1! (Đang chạy mô phỏng {mtype} -> {target})")
                self.wait(0.3)
                return

            c = self.client
            c.set_speed_ratio(int(max(5, min(100, (speed / 900.0) * 100))))
            if mtype == "MoveJ":
                c.joint_move_to(pt_data['joint'])
            else:
                c.task_move_to(pt_data['tcp'])
            self.wait_motion_done()
            return

        # Trường hợp 2: Có từ 2 điểm trở lên -> Thực thi chuỗi Fillet Waypoint tự động
        names = [it['target_name'] for it in queue]
        path_str = " -> ".join(names)
        self.log(f"▶ Chạy Fillet liên tục: {path_str}")

        if not self.is_connected():
            self.log(f"⚠️ Robot chưa kết nối ở Tab 1! (Mô phỏng Fillet: {path_str})")
            self.wait(1.0)
            return

        targets = []
        for i, it in enumerate(queue):
            pt = dict(it['pt_data'])
            pt['name'] = it['target_name']
            pt['type'] = it['type']
            pt['speed'] = it['speed']
            is_last = (i == len(queue) - 1)
            pt['fillet'] = (not is_last) and (it['radius'] > 0)
            pt['radius'] = 0.0 if is_last else it['radius']
            targets.append(pt)

        c = self.client
        c.execute_waypoint_path(targets, cancel_check_cb=self.is_stopped)

    def offset(self, target, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
               drx: float = 0.0, dry: float = 0.0, drz: float = 0.0) -> dict:
        """
        Tạo điểm mới từ điểm gốc với độ lệch tọa độ TCP (đơn vị mm cho dx, dy, dz; độ cho drx, dry, drz).
        Ví dụ: offset("P1", dy=-123.0) hoặc robot.offset("P3", dy=-123.0)
        """
        base_data = self._resolve_point_data(target)
        new_data = dict(base_data)

        # Sao chép và bù tọa độ TCP
        if 'tcp' in new_data and len(new_data['tcp']) >= 6:
            tcp = list(new_data['tcp'])
            tcp[0] += (float(dx) / 1000.0)
            tcp[1] += (float(dy) / 1000.0)
            tcp[2] += (float(dz) / 1000.0)
            tcp[3] += float(drx)
            tcp[4] += float(dry)
            tcp[5] += float(drz)
            new_data['tcp'] = tcp
            new_data['type'] = 'MoveL'  # Điểm bù TCP luôn chạy MoveL để đi thẳng chính xác theo không gian đề-các

        t_name = target if isinstance(target, str) else base_data.get('name', 'Pt')
        offset_tag = []
        if dx: offset_tag.append(f"dx:{dx:+.0f}mm")
        if dy: offset_tag.append(f"dy:{dy:+.0f}mm")
        if dz: offset_tag.append(f"dz:{dz:+.0f}mm")
        tag_str = f"[{','.join(offset_tag)}]" if offset_tag else ""
        new_data['name'] = f"{t_name}{tag_str}"
        return new_data

    def move_j(self, target, speed: float = 200.0, zone=None, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, *args, **kwargs):
        """
        Di chuyển khớp tới điểm dạy (ví dụ: 'P1').
        Cú pháp ABB: robot.move_j("P1", 400.0, z10) hoặc robot.move_j("P1", speed=400.0, zone=z10)
        zone: fine (0), z0, z1, z5, z10, z15, z20, z30, z50, z100...
        """
        dx_val = dx or kwargs.pop('dx', 0.0)
        dy_val = dy or kwargs.pop('dy', 0.0)
        dz_val = dz or kwargs.pop('dz', 0.0)
        if dx_val != 0.0 or dy_val != 0.0 or dz_val != 0.0:
            # Nếu có bù tọa độ Cartesian, chuyển hướng sang MoveL với điểm bù
            return self.move_l(target, speed=speed, zone=zone, dx=dx_val, dy=dy_val, dz=dz_val, *args, **kwargs)

        self.check_interrupt()
        pt_data = self._resolve_point_data(target)
        joint = pt_data.get('joint')
        if not joint or len(joint) < 6:
            raise ValueError(f"Dữ liệu góc khớp của '{target}' không hợp lệ!")

        r_val = self._parse_zone_val(zone, **kwargs)
        zone_label = f"z{int(r_val)}" if r_val > 0 else "fine"
        t_name = pt_data.get('name', target if isinstance(target, str) else "Point")
        self.log(f"MoveJ -> {t_name} (Tốc độ: {speed:.0f} mm/s, Zone: {zone_label})")

        # Nếu kiểu trước đó không phải MoveJ -> Xả hàng đợi trước
        if self._motion_buffer and self._motion_buffer[-1]['type'] != 'MoveJ':
            self._flush_motion_buffer()

        self._motion_buffer.append({
            'type': 'MoveJ',
            'target_name': t_name,
            'speed': float(speed),
            'radius': r_val,
            'pt_data': pt_data
        })

        if r_val <= 0.0:
            self._flush_motion_buffer()

    def move_l(self, target, speed: float = 200.0, zone=None, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, *args, **kwargs):
        """
        Di chuyển đường thẳng TCP tới điểm dạy (ví dụ: 'P2') hoặc điểm bù offset.
        Cú pháp ABB: robot.move_l("P2", 400.0, z10) hoặc robot.move_l("P2", 400.0, z10, dy=-123.0)
        zone: fine (0), z0, z1, z5, z10, z15, z20, z30, z50, z100...
        """
        dx_val = dx or kwargs.pop('dx', 0.0)
        dy_val = dy or kwargs.pop('dy', 0.0)
        dz_val = dz or kwargs.pop('dz', 0.0)
        if dx_val != 0.0 or dy_val != 0.0 or dz_val != 0.0:
            target = self.offset(target, dx=dx_val, dy=dy_val, dz=dz_val)

        self.check_interrupt()
        pt_data = self._resolve_point_data(target)
        tcp = pt_data.get('tcp')
        if not tcp or len(tcp) < 6:
            raise ValueError(f"Dữ liệu tọa độ TCP của '{target}' không hợp lệ!")

        r_val = self._parse_zone_val(zone, **kwargs)
        zone_label = f"z{int(r_val)}" if r_val > 0 else "fine"
        t_name = pt_data.get('name', target if isinstance(target, str) else "Point")
        self.log(f"MoveL -> {t_name} (Tốc độ: {speed:.0f} mm/s, Zone: {zone_label})")

        # Nếu kiểu trước đó không phải MoveL -> Xả hàng đợi trước
        if self._motion_buffer and self._motion_buffer[-1]['type'] != 'MoveL':
            self._flush_motion_buffer()

        self._motion_buffer.append({
            'type': 'MoveL',
            'target_name': t_name,
            'speed': float(speed),
            'radius': r_val,
            'pt_data': pt_data
        })

        if r_val <= 0.0:
            self._flush_motion_buffer()

    def execute_waypoint_path(self, points_list):
        """Chạy toàn bộ chuỗi điểm Waypoint Path."""
        self._flush_motion_buffer()
        self.check_interrupt()
        resolved_list = []
        for pt in points_list:
            if isinstance(pt, str):
                resolved_list.append(self._resolve_point_data(pt))
            elif isinstance(pt, dict):
                resolved_list.append(pt)
            else:
                resolved_list.append(self._resolve_point_data(pt))

        self.log(f"▶ Bắt đầu chạy Waypoint Path ({len(resolved_list)} điểm)...")
        if not self.is_connected():
            self.log("⚠️ Robot chưa kết nối ở Tab 1! Vui lòng bấm Kết Nối ở Tab 1 trước.")
            return False

        c = self.client
        return c.execute_waypoint_path(
            resolved_list,
            cancel_check_cb=self.is_stopped
        )

    def set_do(self, pin: int, state: bool):
        """Bật (True) hoặc Tắt (False) ngõ ra số Digital Output (pin 0..31)."""
        self._flush_motion_buffer()
        self.check_interrupt()
        self.log(f"SET DO[{pin}] = {'ON' if state else 'OFF'}")
        if self.is_connected():
            self.client.set_do(pin, state)

    def get_di(self, pin: int) -> int:
        """Đọc trạng thái ngõ vào số Digital Input (pin 0..31), trả về 0 hoặc 1."""
        self._flush_motion_buffer()
        self.check_interrupt()
        if self.is_connected():
            return int(self.client.get_di(pin))
        return 0

    def get_do(self, pin: int) -> int:
        """Đọc trạng thái ngõ ra số Digital Output (pin 0..31), trả về 0 hoặc 1."""
        self._flush_motion_buffer()
        self.check_interrupt()
        if self.is_connected():
            return int(self.client.get_do(pin))
        return 0

    def wait(self, seconds: float):
        """Tạm dừng chương trình an toàn trong khoảng thời gian (giây)."""
        self._flush_motion_buffer()
        end_t = time.time() + float(seconds)
        while time.time() < end_t:
            self.check_interrupt()
            time.sleep(min(0.05, max(0.0, end_t - time.time())))

    def wait_di(self, pin: int, state: int = 1, timeout: float = 30.0) -> bool:
        """
        Chờ ngõ vào số Digital Input (pin) đạt trạng thái (state: 0 hoặc 1).
        timeout: Thời gian chờ tối đa (giây). Nếu quá thời gian sẽ ném TimeoutError.
        """
        self.check_interrupt()
        self.log(f"Đang chờ DI[{pin}] == {state} (Timeout: {timeout:.1f}s)...")
        start_t = time.time()

        while True:
            self.check_interrupt()
            if self.is_connected():
                val = self.get_di(pin)
                if val == state:
                    self.log(f"✓ Đã nhận tín hiệu DI[{pin}] == {state}")
                    return True
            else:
                if time.time() - start_t >= 1.0:
                    self.log(f"[Mô phỏng] Kích hoạt DI[{pin}] == {state}")
                    return True

            if timeout > 0 and (time.time() - start_t) > timeout:
                raise TimeoutError(f"Hết thời gian chờ (Timeout {timeout}s) cho tín hiệu DI[{pin}] == {state}!")

            time.sleep(0.05)

    def wait_motion_done(self, timeout: float = 45.0):
        """Chờ robot kết thúc chuyển động hiện tại."""
        # Pha 1: Chờ robot bắt đầu chạy (tối đa 1.2s)
        start_w = time.time()
        while time.time() - start_w < 1.2:
            self.check_interrupt()
            if not self.is_connected():
                break
            st = self.client.get_robot_status()
            if st.get('busy', 0) == 1 or st.get('is_robot_moving', 0) == 1:
                break
            time.sleep(0.08)

        # Pha 2: Chờ robot hoàn tất và dừng hẳn (busy == 0)
        start_t = time.time()
        while time.time() - start_t < timeout:
            self.check_interrupt()
            if not self.is_connected():
                break
            st = self.client.get_robot_status()
            is_busy = (st.get('busy', 0) == 1 or st.get('is_robot_moving', 0) == 1)
            if not is_busy:
                break
            time.sleep(0.08)
        time.sleep(0.1)

    def set_speed(self, speed_mms: float):
        """Cài đặt tốc độ vận hành chung (mm/s)."""
        if self.is_connected():
            ratio = int(max(5, min(100, (float(speed_mms) / 900.0) * 100)))
            self.client.set_speed_ratio(ratio)

    def go_home(self):
        """Đưa robot về vị trí Home an toàn."""
        self.check_interrupt()
        self.log("Di chuyển về vị trí Home...")
        if self.is_connected():
            self.client.go_home()
            self.wait_motion_done()

    def get_pos(self) -> list:
        """Đọc tọa độ TCP hiện tại [X, Y, Z, Rx, Ry, Rz]."""
        if self.is_connected():
            return self.client.get_task_pos()
        return [0.0] * 6

    def get_joint(self) -> list:
        """Đọc góc 6 khớp hiện tại [J1, J2, J3, J4, J5, J6]."""
        if self.is_connected():
            return self.client.get_joint_pos()
        return [0.0] * 6

    def stop(self):
        """Dừng chuyển động của robot ngay lập tức."""
        if self.is_connected():
            self.client.stop_motion()


class StdoutRedirector(io.StringIO):
    """Bắt các lệnh print() trong script và chuyển ra log của GUI."""
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback
        self._in_write = False

    def write(self, s: str):
        if not self._in_write and s and s.strip():
            self._in_write = True
            try:
                self.callback(s.rstrip())
            finally:
                self._in_write = False
        return len(s)


class PythonScriptRunner:
    """Trình nạp, biên dịch và thực thi file Python (.py) trong môi trường an toàn."""
    def __init__(self, client_provider, saved_targets_provider: Callable[[], dict],
                 log_callback: Optional[Callable[[str], None]] = None,
                 finish_callback: Optional[Callable[[bool, str], None]] = None):
        self.client_provider = client_provider
        self.saved_targets_provider = saved_targets_provider
        self.log_callback = log_callback
        self.finish_callback = finish_callback

        self.is_running = False
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

    def execute_script(self, code_str: str, file_name: str = "<embedded_script>"):
        if self.is_running:
            return

        self.is_running = True
        self.stop_event.clear()

        def run_thread():
            success = False
            msg = ""
            start_time = time.time()

            # Tạo wrapper API
            api = RobotScriptAPI(
                client_provider=self.client_provider,
                saved_targets_provider=self.saved_targets_provider,
                log_callback=self.log_callback,
                stop_event=self.stop_event
            )

            # Tạo dictionary điểm P1, P2...
            points = {}
            if callable(self.saved_targets_provider):
                res = self.saved_targets_provider()
                if isinstance(res, dict):
                    points = res
                elif isinstance(res, list):
                    points = {f"P{i+1}": pt for i, pt in enumerate(res)}

            # Môi trường toàn cục (globals) cho Script
            script_globals = {
                "__name__": "__embedded_studio__",
                "__file__": file_name,
                "robot": api,
                "points": points,
                "time": time,
                # Tiện ích gọi nhanh không cần tiền tố robot.
                "move_j": api.move_j,
                "move_l": api.move_l,
                "offset": api.offset,
                "execute_waypoint_path": api.execute_waypoint_path,
                "set_do": api.set_do,
                "get_di": api.get_di,
                "get_do": api.get_do,
                "wait": api.wait,
                "wait_di": api.wait_di,
                "log": api.log,
                "is_stopped": api.is_stopped,
                # Các hằng số Zone / Fillet theo tiêu chuẩn ABB RAPID
                "fine": 0.0,
                "z0": 0.3,
                "z1": 1.0,
                "z5": 5.0,
                "z10": 10.0,
                "z15": 15.0,
                "z20": 20.0,
                "z30": 30.0,
                "z50": 50.0,
                "z100": 100.0,
                "z200": 200.0,
            }

            old_stdout = sys.stdout
            if self.log_callback:
                sys.stdout = StdoutRedirector(self.log_callback)

            try:
                api.log(f"🚀 BẮT ĐẦU CHẠY SCRIPT: '{file_name}'")
                
                # Biên dịch mã nguồn
                compiled = compile(code_str, file_name, 'exec')
                
                # Thực thi mã nguồn từ trên xuống dưới
                exec(compiled, script_globals)

                # Xả toàn bộ chuyển động còn lại trong buffer nếu có
                api._flush_motion_buffer()

                elapsed = time.time() - start_time
                api.log(f"✓ SCRIPT ĐÃ HOÀN TẤT THÀNH CÔNG trong {elapsed:.2f} giây!")
                success = True
                msg = f"Hoàn tất trong {elapsed:.2f}s"
            except KeyboardInterrupt:
                api.log("■ ĐÃ DỪNG SCRIPT THEO YÊU CẦU CỦA NGƯỜI DÙNG.")
                msg = "Đã dừng bởi người dùng"
            except Exception as e:
                err_tb = traceback.format_exc()
                api.log(f"❌ LỖI KHI THỰC THI SCRIPT:\n{err_tb}")
                msg = str(e)
            finally:
                sys.stdout = old_stdout
                self.is_running = False
                client = self.client_provider() if callable(self.client_provider) else self.client_provider
                if client and getattr(client, 'client', None):
                    try:
                        client.stop_motion()
                    except Exception:
                        pass
                if self.finish_callback:
                    self.finish_callback(success, msg)

        self.worker_thread = threading.Thread(target=run_thread, daemon=True, name="PythonScriptRunner-Worker")
        self.worker_thread.start()

    def stop_script(self):
        if self.is_running:
            self.stop_event.set()
            if self.client and getattr(self.client, 'client', None):
                try:
                    self.client.stop_motion()
                except Exception:
                    pass
            if self.log_callback:
                self.log_callback("■ Đang gửi tín hiệu dừng khẩn cấp tới Script...")


# ==============================================================================
# 6. SCRIPT TEMPLATES LIBRARY
# ==============================================================================

SCRIPT_TEMPLATES = {
    "1. Chu trình Lặp Gắp Thả & Kiểm Tra Cảm Biến DI": '''# ==============================================================================
# MẪU SCRIPT 1: CHU TRÌNH GẮP THẢ VỚI CẢM BIẾN DI
# ==============================================================================

def main():
    log("Bắt đầu chu trình gắp thả tự động...")
    
    # 1. Cài đặt tốc độ vận hành 250 mm/s
    robot.set_speed(250)
    
    # 2. Vòng lặp gắp thả 5 lần
    for cycle in range(1, 6):
        if is_stopped():
            break
            
        log(f"=== Bắt đầu chu trình lần {cycle}/5 ===")
        
        # Di chuyển tới điểm lấy phôi P1
        move_j("P1", speed=300)
        
        # Kẹp tay kẹp (DO 0) và chờ 0.5s
        set_do(0, True)
        wait(0.5)
        
        # Kiểm tra cảm biến kẹp có phôi hay không (DI 0)
        if get_di(0) == 1:
            log("✓ Đã kẹp trúng phôi! Chuyển tới vị trí đóng gói P2")
            move_l("P2", speed=200)
        else:
            log("⚠️ Không phát hiện phôi! Chuyển sang vị trí nhả phôi lỗi P3")
            move_l("P3", speed=200)
            
        # Mở kẹp (DO 0 = OFF) và chờ 0.5s
        set_do(0, False)
        wait(0.5)
        
    log("✓ Hoàn tất toàn bộ 5 chu trình gắp thả!")

main()
''',

    "2. Chu trình Xếp Pallet Ma Trận (2x3)": '''# ==============================================================================
# MẪU SCRIPT 2: XẾP PALLET MA TRẬN 2 HÀNG x 3 CỘT
# ==============================================================================

def main():
    log("Bắt đầu chu trình xếp Pallet 6 vị trí...")
    
    rows = 2
    cols = 3
    spacing_x_mm = 50.0  # Khoảng cách giữa các cột (mm)
    spacing_y_mm = 60.0  # Khoảng cách giữa các hàng (mm)
    
    # Lấy vị trí gốc của điểm Pallet Base (P2)
    p_base = points.get("P2")
    if not p_base:
        log("Cần dạy điểm P2 làm mốc Pallet Base!")
        return
        
    base_tcp = list(p_base['tcp'])  # [x_m, y_m, z_m, rx, ry, rz]
    
    count = 1
    for r in range(rows):
        for c in range(cols):
            if is_stopped():
                return
                
            log(f"--- Đang xếp vị trí {count}/6 (Hàng {r+1}, Cột {c+1}) ---")
            
            # 1. Lấy sản phẩm tại P1
            move_j("P1", speed=300)
            set_do(0, True)  # Kẹp phôi
            wait(0.5)
            
            # 2. Tính toán tọa độ offset cho vị trí Pallet
            target_tcp = list(base_tcp)
            target_tcp[0] += (c * spacing_x_mm) / 1000.0  # Offset X (mét)
            target_tcp[1] += (r * spacing_y_mm) / 1000.0  # Offset Y (mét)
            
            # 3. Di chuyển thẳng MoveL tới vị trí Pallet
            move_l(target_tcp, speed=200)
            set_do(0, False)  # Nhả phôi
            wait(0.5)
            
            count += 1
            
    log("✓ Đã hoàn tất xếp đầy Pallet 6 vị trí!")

main()
''',

    "3. Chu trình Chờ Cảm Biến Bắt Đầu (Industrial Sensor Trigger)": '''# ==============================================================================
# MẪU SCRIPT 3: CHỜ TÍN HIỆU CẢM BIẾN BĂNG TẢI (DI 1)
# ==============================================================================

def main():
    log("Hệ thống sẵn sàng ở vị trí Home. Đang chờ phôi trên băng tải...")
    robot.go_home()
    
    while not is_stopped():
        log("Chờ cảm biến băng tải DI 1 kích hoạt (ON)...")
        
        try:
            # Chờ tín hiệu cảm biến DI 1 = 1 (Timeout 60s)
            wait_di(pin=1, state=1, timeout=60.0)
        except TimeoutError:
            log("Chưa có phôi sau 60s, tiếp tục chờ...")
            continue
            
        log("Đã phát hiện phôi! Robot bắt đầu gắp...")
        move_j("P1", speed=300)
        set_do(0, True)
        wait(0.5)
        
        move_l("P2", speed=250)
        set_do(0, False)
        wait(0.5)
        
        robot.go_home()

main()
''',

    "4. Chu trình 5 Điểm MoveL (Fillet 10mm)": '''# ==============================================================================
# MẪU SCRIPT 4: CHU TRÌNH 5 ĐIỂM MOVEL (FILLET 10mm)
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

def main():
    log("🚀 Bắt đầu chạy liên tục quỹ đạo 5 điểm MoveL...")
    execute_waypoint_path(TARGET_POINTS)
    log("✓ Hoàn tất chu trình 5 điểm!")

main()
'''
}
