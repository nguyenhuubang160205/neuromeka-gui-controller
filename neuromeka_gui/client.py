import os
import sys
import threading
import time

try:
    from neuromeka import IndyDCP2
except Exception as _e2:
    IndyDCP2 = None

try:
    from neuromeka import IndyDCP3
except Exception as _e3:
    IndyDCP3 = None


# Vá lỗi parse_robot_status của Neuromeka SDK để đọc đúng chính xác 100% bitmask từ Controller
def _fixed_parse_robot_status(self, status):
    self.robot_status.is_robot_running        = int(bool(status & (1 << 31)))
    self.robot_status.is_robot_ready          = int(bool(status & (1 << 30)))
    self.robot_status.is_emergency_stop       = int(bool(status & (1 << 29)))
    self.robot_status.is_collided             = int(bool(status & (1 << 28)))
    self.robot_status.is_error_state          = int(bool(status & (1 << 27)))
    self.robot_status.is_busy                 = int(bool(status & (1 << 26)))
    self.robot_status.is_move_finished        = int(bool(status & (1 << 25)))
    self.robot_status.is_home                 = int(bool(status & (1 << 24)))
    self.robot_status.is_zero                 = int(bool(status & (1 << 23)))
    self.robot_status.is_in_resetting         = int(bool(status & (1 << 22)))
    self.robot_status.is_direct_teaching_mode = int(bool(status & (1 << 7)))
    self.robot_status.is_teaching_mode        = int(bool(status & (1 << 6)))
    self.robot_status.is_program_running      = int(bool(status & (1 << 5)))
    self.robot_status.is_program_paused       = int(bool(status & (1 << 4)))
    self.robot_status.is_conty_connected      = int(bool(status & (1 << 3)))

# Vá lỗi check_header của Neuromeka SDK do NumPy 2.x bỏ hàm .tostring()
def _fixed_check_header(self, req=None, res=None, err_code=0):
    if req is None or res is None:
        return 0
    try:
        req_robot_name = bytes(req.val.robotName).decode('utf-8', errors='ignore').rstrip('\x00')
        res_robot_name = bytes(res.val.robotName).decode('utf-8', errors='ignore').rstrip('\x00')
        if req_robot_name != res_robot_name:
            print(f"Header check fail (robotName): Request {req_robot_name}, Response {res_robot_name}")
        if req.val.stepInfo != res.val.stepInfo:
            print(f"Header check fail (stepInfo): Request {req.val.stepInfo}, Response {res.val.stepInfo}")
        if req.val.invokeId != res.val.invokeId:
            print(f"Header check fail (invokeId): Request {req.val.invokeId}, Response {res.val.invokeId}")
        sof_server = getattr(self, '_IndyDCP2__sof_server', 0x12)
        if res.val.sof != sof_server:
            print(f"Header check fail (sof): Request {sof_server}, Response {res.val.sof}")
        if req.val.cmdId != res.val.cmdId:
            print(f"Header check fail (cmdId): Request {req.val.cmdId}, Response {res.val.cmdId}")
        if res.val.cmdId == 9999:  # CMD_ERROR
            try:
                from neuromeka.indydcp2 import err_to_string
                print(err_to_string(err_code))
            except Exception:
                pass
            return err_code
    except Exception as e:
        print(f"Warning check_header: {e}")
    return 0

if IndyDCP2 is not None:
    IndyDCP2.parse_robot_status = _fixed_parse_robot_status
    IndyDCP2.check_header = _fixed_check_header


class UnifiedIndyClient:
    def __init__(self, ip):
        self.ip = ip
        self.version = None
        self.client = None
        # IndyDCP2 dùng một request/response stream trên một socket. Mọi thao tác
        # phải đi tuần tự qua lock này; tuyệt đối không đọc "flush" socket từ
        # một luồng khác vì có thể nuốt response của lệnh đang chạy.
        self.lock = threading.RLock()
        self._disconnecting = False

    @staticmethod
    def _command_ok(result):
        """Chuẩn hóa kiểu trả về khác nhau giữa các phiên bản Indy SDK."""
        if result is None:
            return True
        if isinstance(result, bool):
            return result
        if isinstance(result, int):
            # IndyDCP2 quy ước 0 là thành công.
            return result == 0
        if isinstance(result, dict):
            code = result.get("code", result.get("error_code", 0))
            return code in (0, None, False)
        return True

    def connect(self):
        with self.lock:
            if self.client:
                return True
            self._disconnecting = False
                
            try:
                self.client = IndyDCP2(server_ip=self.ip, robot_name="NRMK-Indy7")
                if self.client.connect():
                    self.version = 2
                    if hasattr(self.client, 'sock_fd') and self.client.sock_fd:
                        try:
                            import socket
                            self.client.sock_fd.settimeout(1.5)
                            self.client.sock_fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        except Exception:
                            pass
                    time.sleep(0.05)
                    return True
            except Exception as e:
                print(f"Lỗi kết nối IndyDCP2: {e}")
                self.client = None
                
            # Nếu thất bại với V2, thử kết nối nhanh với V3
            try:
                self.client = IndyDCP3(robot_ip=self.ip)
                self.client.get_robot_data()
                self.version = 3
                return True
            except Exception as e:
                print(f"Lỗi kết nối gRPC IndyDCP3: {e}")
                self.client = None
                self.version = None
                return False
            return False

    def disconnect(self):
        # Đóng socket/channel trước (KHÔNG dùng lock) để giải phóng các lệnh đang bị block
        import socket
        self._disconnecting = True
        if self.client:
            try:
                if self.version == 2:
                    if hasattr(self.client, 'sock_fd') and self.client.sock_fd:
                        try:
                            self.client.sock_fd.shutdown(socket.SHUT_RDWR)
                        except:
                            pass
                        self.client.sock_fd.close()
                elif self.version == 3:
                    if hasattr(self.client, 'boot_channel') and self.client.boot_channel:
                        self.client.boot_channel.close()
                    if hasattr(self.client, 'control_channel') and self.client.control_channel:
                        self.client.control_channel.close()
                    if hasattr(self.client, 'device_channel') and self.client.device_channel:
                        self.client.device_channel.close()
            except Exception:
                pass

        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.disconnect()
                    elif self.version == 3:
                        # Đảm bảo tắt servo và đóng kết nối channel
                        try:
                            self.client.set_servo_all(False)
                        except:
                            pass
                        if hasattr(self.client, 'config_channel'): self.client.config_channel.close()
                        if hasattr(self.client, 'rtde_channel'): self.client.rtde_channel.close()
                        if hasattr(self.client, 'cri_channel'): self.client.cri_channel.close()
                except Exception:
                    pass
                self.client = None
                self.version = None
                self._disconnecting = False

    def get_joint_pos(self):
        with self.lock:
            if self.client:
                if self.version == 2:
                    return self.client.get_joint_pos()
                elif self.version == 3:
                    data = self.client.get_robot_data()
                    return data.get('q', [0.0]*6)
            return [0.0]*6

    def get_task_pos(self):
        with self.lock:
            if self.client:
                if self.version == 2:
                    return self.client.get_task_pos()
                elif self.version == 3:
                    data = self.client.get_robot_data()
                    return data.get('p', [0.0]*6)
            return [0.0]*6

    def get_servo_state(self):
        with self.lock:
            if self.client:
                if self.version == 2:
                    return self.client.get_servo_state()
                elif self.version == 3:
                    data = self.client.get_servo_data()
                    servo_actives = [bool(s) for s in data.get('servo_actives', [False]*6)]
                    brake_actives = [bool(b) for b in data.get('brake_actives', [True]*6)]
                    return (servo_actives, brake_actives)
            return ([False]*6, [True]*6)

    def _flush_socket(self):
        """
        Khôi phục timeout nhưng KHÔNG tự đọc bỏ byte khỏi socket.

        IndyDCP2 là giao thức request/response; recv() thủ công có thể lấy mất
        response mà SDK đang chờ, làm mọi lệnh sau đó lệch khung và treo. Nếu
        lỗi truyền thông lặp lại, vòng giám sát sẽ chủ động disconnect/reconnect.
        """
        if self.version == 2 and self.client and hasattr(self.client, 'sock_fd') and self.client.sock_fd:
            try:
                self.client.sock_fd.settimeout(1.5)
            except Exception:
                pass

    def get_all_states(self):
        """
        Đọc trạng thái từng phần bằng các lock ngắn riêng biệt.
        Mỗi lệnh TCP chỉ giữ lock ~50-150ms, nhả giữa các lệnh
        để luồng Jog có cửa sổ chen vào sử dụng socket.
        """
        if not self.client:
            return None
        try:
            # Mỗi hàm dưới đây đã tự khóa/nhả lock riêng
            angles = self.get_joint_pos()
            tcp = self.get_task_pos()
            servo_state = self.get_servo_state()
            status = self.get_robot_status()
            return {
                'angles': angles,
                'tcp': tcp,
                'servo_state': servo_state,
                'status': status
            }
        except Exception as e:
            err_str = str(e)
            if "10038" not in err_str and "10054" not in err_str:
                print(f"Lỗi đọc trạng thái gộp: {e}")
            return None

    def set_servo(self, list_of_booleans):
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.set_servo(list_of_booleans)
                    elif self.version == 3:
                        enable = any(list_of_booleans)
                        self.client.set_servo_all(enable)
                except Exception as e:
                    print(f"Lỗi set_servo: {e}")
                    self._flush_socket()

    def joint_move_by(self, q):
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self._command_ok(self.client.joint_move_by(q))
                    elif self.version == 3:
                        return self._command_ok(self.client.movej(jtarget=q, base_type=1))
                except Exception as e:
                    print(f"Lỗi joint_move_by: {e}")
                    self._flush_socket()
                    return False
        return False

    def try_joint_move_by(self, q):
        """Thực thi joint_move_by không nghẽn lock cho luồng stream jog tần số cao"""
        if self.lock.acquire(blocking=False):
            try:
                if self.client:
                    if self.version == 2:
                        return self._command_ok(self.client.joint_move_by(q))
                    elif self.version == 3:
                        return self._command_ok(self.client.movej(jtarget=q, base_type=1))
            except Exception as e:
                print(f"Lỗi try_joint_move_by: {e}")
                self._flush_socket()
            finally:
                self.lock.release()
        return False

    def joint_move_to(self, q):
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        try:
                            self.client.joint_waypoint_clean()
                        except Exception:
                            pass
                        return self.client.joint_move_to(q)
                    elif self.version == 3:
                        return self.client.movej(jtarget=q, base_type=0)
                except Exception as e:
                    print(f"Lỗi joint_move_to: {e}")
                    self._flush_socket()
                    return False
        return False

    def task_move_by(self, p):
        """
        Di chuyển Task tương đối.

        API nội bộ của ứng dụng dùng mét cho X/Y/Z và độ cho Rx/Ry/Rz.
        IndyDCP3 nhận phần tịnh tiến theo mm nên cần đổi đơn vị tại biên SDK.
        """
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self._command_ok(self.client.task_move_by(p))
                    elif self.version == 3:
                        p_mm = [p[0] * 1000.0, p[1] * 1000.0, p[2] * 1000.0,
                                p[3], p[4], p[5]]
                        return self._command_ok(self.client.movel(ttarget=p_mm, base_type=1))
                except Exception as e:
                    print(f"Lỗi task_move_by: {e}")
                    self._flush_socket()
                    return False
        return False

    def try_task_move_by(self, p):
        """Thực thi task_move_by không nghẽn lock cho luồng stream jog tần số cao"""
        if self.lock.acquire(blocking=False):
            try:
                if self.client:
                    if self.version == 2:
                        return self._command_ok(self.client.task_move_by(p))
                    elif self.version == 3:
                        p_mm = [p[0] * 1000.0, p[1] * 1000.0, p[2] * 1000.0,
                                p[3], p[4], p[5]]
                        return self._command_ok(self.client.movel(ttarget=p_mm, base_type=1))
            except Exception as e:
                print(f"Lỗi try_task_move_by: {e}")
                self._flush_socket()
            finally:
                self.lock.release()
        return False

    def task_move_to(self, p):
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        try:
                            self.client.task_waypoint_clean()
                        except Exception:
                            pass
                        return self.client.task_move_to(p)
                    elif self.version == 3:
                        p_mm = [p[0]*1000.0, p[1]*1000.0, p[2]*1000.0, p[3], p[4], p[5]]
                        return self.client.movel(ttarget=p_mm, base_type=0)
                except Exception as e:
                    print(f"Lỗi task_move_to: {e}")
                    self._flush_socket()
                    return False
        return False

    def stop_motion_light(self):
        """Dừng nhẹ (chỉ stop_motion, KHÔNG gọi stop_emergency). Dùng cho Jog release."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self._command_ok(self.client.stop_motion())
                    return self._command_ok(self.client.stop_motion(stop_category=0))
                except Exception as e:
                    print(f"Lỗi stop_motion_light: {e}")
        return False

    def reset_robot(self):
        with self.lock:
            if self.client:
                if self.version == 2:
                    self.client.reset_robot()
                elif self.version == 3:
                    self.client.reset()

    def set_direct_teaching(self, enable: bool):
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        if hasattr(self.client, 'direct_teaching'):
                            self.client.direct_teaching(enable)
                        elif hasattr(self.client, 'set_direct_teaching'):
                            self.client.set_direct_teaching(enable)
                    elif self.version == 3:
                        if hasattr(self.client, 'set_direct_teaching'):
                            self.client.set_direct_teaching(enable)
                        elif hasattr(self.client, 'direct_teaching'):
                            self.client.direct_teaching(enable)
                    return True
                except Exception as e:
                    print(f"Lỗi Chế độ Cầm tay: {e}")
                    return False
            return False
            return False

    def set_tool_payload(self, mass: float, cog: list = [0.0, 0.0, 0.05]):
        """Cài đặt Khối lượng (kg) và Tâm trọng lực CoG [x, y, z] (mét) xuống Tủ điều khiển Robot."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.set_tcp_comp([mass, cog[0], cog[1], cog[2], 0.0, 0.0])
                    elif self.version == 3:
                        self.client.set_tool_property(
                            mass=mass,
                            center_of_mass=cog,
                            inertia=[0.01, 0.01, 0.01, 0.0, 0.0, 0.0]
                        )
                    return True
                except Exception as e:
                    print(f"Lỗi thiết lập Tool Payload: {e}")
                    return False
            return False

    def set_friction_compensation(self, ctrl_levels: list = [3, 3, 3, 3, 3, 3], dt_levels: list = [5, 5, 5, 5, 5, 5]):
        """Cấu hình cấp độ bù ma sát khớp (Friction Compensation) cho 6 khớp."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 3 and hasattr(self.client, 'set_friction_comp'):
                        self.client.set_friction_comp(
                            control_comp=True,
                            control_comp_levels=ctrl_levels,
                            dt_comp=True,
                            dt_comp_levels=dt_levels
                        )
                        self.client.set_friction_comp_state(True)
                    return True
                except Exception as e:
                    print(f"Lỗi thiết lập Bù ma sát khớp: {e}")
                    return False
            return False

    def zero_ft_sensor(self):
        """Reset / Zero điểm 0 cho cảm biến lực/mô-men (FT Sensor) để triệt trôi khớp 4 & cổ tay."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        if hasattr(self.client, 'zero_ft_sensor'):
                            self.client.zero_ft_sensor()
                        elif hasattr(self.client, 'reset_ft_sensor'):
                            self.client.reset_ft_sensor()
                    elif self.version == 3:
                        if hasattr(self.client, 'zero_ft_sensor'):
                            self.client.zero_ft_sensor()
                        elif hasattr(self.client, 'reset_ft_sensor'):
                            self.client.reset_ft_sensor()
                        elif hasattr(self.client, 'set_ft_sensor_bias'):
                            self.client.set_ft_sensor_bias()
                    return True
                except Exception as e:
                    print(f"Lỗi Zero Cảm biến Lực (FT Sensor): {e}")
                    return False
            return False

    def auto_estimate_payload(self):
        """
        Tự động đo và ước tính Khối lượng Tool (kg) và CoG (mm) 
        dựa trên phản hồi mô-men khớp / lực cảm biến ở vị trí hiện tại.
        """
        with self.lock:
            if not self.client:
                return False, 2.0, [0.0, 0.0, 50.0]
            try:
                # Nếu tủ Indy hỗ trợ hàm đo tự động nguyên bản
                if hasattr(self.client, 'measure_payload'):
                    res = self.client.measure_payload()
                    if isinstance(res, (list, tuple)) and len(res) >= 4:
                        return True, float(res[0]), [float(res[1])*1000.0, float(res[2])*1000.0, float(res[3])*1000.0]
                elif hasattr(self.client, 'get_joint_torque'):
                    # Đo từ mô-men khớp 4 & 5
                    torques = self.client.get_joint_torque()
                    if len(torques) >= 6:
                        # Ước lượng thô mô-men khớp 4, 5
                        t4 = abs(torques[3])
                        t5 = abs(torques[4])
                        est_mass = round(max(0.5, min(7.0, (t4 + t5) / 9.81 * 0.8)), 2)
                        return True, est_mass, [0.0, 0.0, 55.0]
            except Exception as e:
                print(f"Lỗi tự động ước tính Payload: {e}")
        
        # Mặc định an toàn nếu không đo được tự động
        return True, 2.0, [0.0, 0.0, 50.0]

    def set_tool_frame(self, fpos):
        """
        Ghi tọa độ TCP tool frame [x, y, z, rx, ry, rz] xuống Robot Controller.
        x, y, z tính bằng mét (m), rx, ry, rz tính bằng độ (deg).
        """
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.set_default_tcp(fpos)
                    elif self.version == 3:
                        self.client.set_tool_frame(fpos)
                    return True
                except Exception as e:
                    print(f"Lỗi thiết lập Tool Frame (TCP): {e}")
                    return False
            return False

    def set_reference_frame(self, fpos):
        """
        Ghi tọa độ Reference Frame (User Frame) [x, y, z, rx, ry, rz] xuống Robot Controller.
        x, y, z tính bằng mét (m), rx, ry, rz tính bằng độ (deg).
        """
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.set_reference_frame(fpos)
                    elif self.version == 3:
                        if hasattr(self.client, 'set_ref_frame'):
                            self.client.set_ref_frame(fpos)
                        elif hasattr(self.client, 'set_reference_frame'):
                            self.client.set_reference_frame(fpos)
                    return True
                except Exception as e:
                    print(f"Lỗi thiết lập Reference Frame: {e}")
                    return False
            return False

    def reset_reference_frame(self):
        """Reset Reference Frame về mặc định của Base Frame [0, 0, 0, 0, 0, 0]."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.reset_reference_frame()
                    elif self.version == 3:
                        if hasattr(self.client, 'reset_ref_frame'):
                            self.client.reset_ref_frame()
                        elif hasattr(self.client, 'set_ref_frame'):
                            self.client.set_ref_frame([0.0] * 6)
                    return True
                except Exception as e:
                    print(f"Lỗi reset Reference Frame: {e}")
                    return False
            return False

    def get_reference_frame(self):
        """Đọc tọa độ Reference Frame hiện tại [x, y, z, rx, ry, rz] từ Robot Controller."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self.client.get_reference_frame()
                    elif self.version == 3:
                        if hasattr(self.client, 'get_ref_frame'):
                            return self.client.get_ref_frame()
                except Exception as e:
                    print(f"Lỗi đọc Reference Frame: {e}")
            return [0.0] * 6

    def set_home_zero(self):
        """Đặt vị trí hiện tại của Robot làm mốc Gốc Zero (0 độ) cho tất cả các khớp Encoder."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        if hasattr(self.client, 'set_home_zero'):
                            self.client.set_home_zero()
                    elif self.version == 3:
                        if hasattr(self.client, 'reset_home'):
                            self.client.reset_home()
                    return True
                except Exception as e:
                    print(f"Lỗi reset gốc Zero Encoder: {e}")
                    return False
            return False

    def set_speed_ratio(self, ratio: int):
        """Thiết lập tỷ lệ tốc độ di chuyển (1..100%)."""
        with self.lock:
            if self.client:
                try:
                    ratio = int(max(1, min(100, ratio)))
                    if self.version == 2:
                        lvl = int(max(1, min(9, round((ratio / 100.0) * 8.0 + 1.0))))
                        if hasattr(self.client, 'set_joint_vel_level'):
                            self.client.set_joint_vel_level(lvl)
                        if hasattr(self.client, 'set_task_vel_level'):
                            self.client.set_task_vel_level(lvl)
                    elif self.version == 3:
                        if hasattr(self.client, 'set_speed_ratio'):
                            self.client.set_speed_ratio(ratio)
                    return True
                except Exception as e:
                    print(f"Lỗi set_speed_ratio: {e}")
        return False

    def set_joint_vel_level(self, level):
        with self.lock:
            if self.client:
                if self.version == 2:
                    self.client.set_joint_vel_level(level)
                elif self.version == 3:
                    self.client.set_speed_ratio(int((level / 9.0) * 100.0))

    def set_task_vel_level(self, level):
        with self.lock:
            if self.client:
                if self.version == 2:
                    self.client.set_task_vel_level(level)

    def set_collision_level(self, level: int):
        """Thiết lập độ nhạy va chạm từ 1 (ít nhạy/chống va chạm giả) đến 5 (rất nhạy)."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self.client.set_collision_level(int(level))
                    elif self.version == 3:
                        if hasattr(self.client, 'set_collision_level'):
                            return self.client.set_collision_level(int(level))
                except Exception as e:
                    print(f"Lỗi set_collision_level: {e}")
        return False

    def get_collision_level(self):
        """Đọc độ nhạy va chạm hiện tại của Controller."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self.client.get_collision_level()
                    elif self.version == 3:
                        if hasattr(self.client, 'get_collision_level'):
                            return self.client.get_collision_level()
                except Exception as e:
                    print(f"Lỗi get_collision_level: {e}")
        return 3

    def set_do(self, pin: int, state: bool):
        """Bật/Tắt cổng Digital Output (0..31)"""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        return self._command_ok(self.client.set_do(pin, bool(state)))
                    elif self.version == 3:
                        return self._command_ok(self.client.set_do([(pin, bool(state))]))
                except Exception as e:
                    print(f"Lỗi set_do {pin}: {e}")
                    self._flush_socket()
                    return False
        return False

    def set_digital_output(self, pin, state):
        return self.set_do(pin, state)

    def get_di(self, pin=None):
        """Đọc 32 ngõ vào Digital Input"""
        with self.lock:
            if not self.client:
                return 0 if pin is not None else [0] * 32
            try:
                if self.version == 2:
                    res = self.client.get_di()
                    if isinstance(res, (list, tuple)):
                        dis = [int(v) for v in res[:32]] + [0] * max(0, 32 - len(res[:32]))
                    elif isinstance(res, int):
                        dis = [(res >> i) & 1 for i in range(32)]
                    else:
                        dis = [0] * 32
                    if pin is not None:
                        return dis[pin] if 0 <= pin < len(dis) else 0
                    return dis
                elif self.version == 3:
                    if hasattr(self.client, 'get_di'):
                        res = self.client.get_di()
                        if isinstance(res, dict):
                            if pin is not None:
                                return int(res.get(pin, 0))
                            return [int(res.get(i, 0)) for i in range(32)]
                        elif isinstance(res, (list, tuple)):
                            dis = [int(v) for v in res[:32]]
                            if pin is not None:
                                return dis[pin] if 0 <= pin < len(dis) else 0
                            return dis
            except Exception as e:
                print(f"Lỗi get_di: {e}")
        return 0 if pin is not None else [0] * 32

    def get_do(self, pin=None):
        """Đọc 32 ngõ ra Digital Output"""
        with self.lock:
            if not self.client:
                return 0 if pin is not None else [0] * 32
            try:
                if self.version == 2:
                    res = self.client.get_do()
                    if isinstance(res, (list, tuple)):
                        dos = [int(v) for v in res[:32]] + [0] * max(0, 32 - len(res[:32]))
                    elif isinstance(res, int):
                        dos = [(res >> i) & 1 for i in range(32)]
                    else:
                        dos = [0] * 32
                    if pin is not None:
                        return dos[pin] if 0 <= pin < len(dos) else 0
                    return dos
                elif self.version == 3:
                    if hasattr(self.client, 'get_do'):
                        res = self.client.get_do()
                        if isinstance(res, dict):
                            if pin is not None:
                                return int(res.get(pin, 0))
                            return [int(res.get(i, 0)) for i in range(32)]
                        elif isinstance(res, (list, tuple)):
                            dos = [int(v) for v in res[:32]]
                            if pin is not None:
                                return dos[pin] if 0 <= pin < len(dos) else 0
                            return dos
            except Exception as e:
                print(f"Lỗi get_do: {e}")
        return 0 if pin is not None else [0] * 32

    def emergency_stop(self):
        return self.stop_emergency()

    def stop_emergency(self):
        with self.lock:
            if not self.client:
                return False
            try:
                if self.version == 2:
                    return self._command_ok(self.client.stop_emergency())
                return self._command_ok(self.client.stop_motion(stop_category=0))
            except Exception as e:
                print(f"Lỗi stop_emergency: {e}")
                return False

    def get_last_error_info(self):
        with self.lock:
            if not self.client:
                return {'code': 0, 'msg': 'Chưa kết nối Robot', 'joint': None, 'raw': None}
            try:
                if self.version == 2 and hasattr(self.client, 'get_last_emergency_info'):
                    emg_info = self.client.get_last_emergency_info()
                    if isinstance(emg_info, (tuple, list)) and len(emg_info) >= 3:
                        ret_code = emg_info[0]
                        int_arr = emg_info[1]
                        joint_idx = int_arr[0] if isinstance(int_arr, (list, tuple)) and len(int_arr) > 0 and 0 <= int_arr[0] < 6 else None
                        err_map = {
                            1: "Lỗi quá giới hạn vị trí phần mềm",
                            2: "Lỗi quá tốc độ cho phép",
                            3: "Lỗi quá gia tốc cho phép",
                            4: "Lỗi va chạm phát hiện bởi mô-men",
                            5: "Lỗi ngắt nút khẩn cấp EMG",
                            6: "Lỗi quá tải Servo",
                            16: "Lỗi Servo Driver",
                            32: "Lỗi sai lệch vị trí bám khớp",
                            64: "Lỗi quá tải mô-men khớp",
                        }
                        desc = err_map.get(ret_code, f"Lỗi hệ thống DCP2 (Mã lỗi {ret_code})")
                        joint_str = f" [Khớp J{joint_idx + 1}]" if joint_idx is not None else ""
                        return {'code': ret_code, 'msg': f"{desc}{joint_str}", 'joint': joint_idx, 'raw': emg_info}
            except Exception as e:
                print(f"Lỗi get_last_error_info: {e}")
        return {'code': 0, 'msg': 'Không phát hiện lỗi', 'joint': None, 'raw': None}

    def get_robot_status(self):
        with self.lock:
            if self.client:
                if self.version == 2:
                    try:
                        st = self.client.get_robot_status()
                        if isinstance(st, dict):
                            is_moving = st.get('is_robot_moving', st.get('busy', 0))
                            st['busy'] = 1 if is_moving else 0
                            st['emergency'] = st.get('is_emergency_stopped', st.get('emergency', 0))
                            st['collision'] = st.get('is_collided', st.get('collision', 0))
                            st['error'] = st.get('is_error_state', st.get('error', 0))

                            ready_flag = getattr(self.client.robot_status, 'is_robot_ready', 0)
                            st['ready'] = 1 if (ready_flag and st['emergency'] == 0 and st['error'] == 0 and st['collision'] == 0) else 0

                            if st['error'] == 1 or st['emergency'] == 1 or st['collision'] == 1:
                                st['error_info'] = self.get_last_error_info()
                            else:
                                st['error_info'] = {'code': 0, 'msg': 'Hệ thống hoạt động bình thường', 'joint': None, 'raw': None}
                            return st
                        return st
                    except Exception as e:
                        print(f"Lỗi get_robot_status: {e}")
                        self._flush_socket()
                elif self.version == 3:
                    try:
                        data = self.client.get_robot_data()
                        op_state = data.get('op_state', 0)
                        ready = 1 if op_state in [5, 6, 7, 10, 17] else 0
                        emergency = 1 if op_state in [2, 9, 15] else 0
                        collision = 1 if op_state == 8 else 0
                        error = 1 if op_state in [2, 3, 4, 8, 15] else 0
                        st = {
                            'ready': ready,
                            'emergency': emergency,
                            'collision': collision,
                            'error': error,
                            'busy': 1 if op_state == 6 or data.get('is_robot_moving', False) else 0
                        }
                        if error == 1 or emergency == 1 or collision == 1:
                            st['error_info'] = self.get_last_error_info()
                        else:
                            st['error_info'] = {'code': 0, 'msg': 'Hệ thống hoạt động bình thường', 'joint': None, 'raw': None}
                        return st
                    except Exception:
                        pass
            return {
                'ready': 0,
                'emergency': 0,
                'collision': 0,
                'error': 0,
                'busy': 0,
                'error_info': {'code': 0, 'msg': 'Robot chưa kết nối', 'joint': None, 'raw': None}
            }

    def execute_waypoint_path(self, targets, blend_radius_j=10.0, blend_radius_t=0.05, cancel_check_cb=None):
        if not targets:
            return True
            
        # Chia các điểm thành các phân đoạn theo Loại Chuyển Động (MoveJ hoặc MoveL)
        segments = []
        current_segment = [targets[0]]
        
        for t in targets[1:]:
            if t['type'] == current_segment[-1]['type']:
                current_segment.append(t)
            else:
                segments.append(current_segment)
                current_segment = [t]
        segments.append(current_segment)
        
        # Thực thi từng phân đoạn
        for seg in segments:
            if cancel_check_cb and cancel_check_cb():
                self.stop_motion()
                return False
                
            mtype = seg[0]['type']
            seg_speed = seg[0].get('speed', 200)
            
            # Cài đặt tốc độ
            level = max(1, min(9, int(round(1.0 + (seg_speed - 50.0) * 8.0 / 850.0))))
            self.set_joint_vel_level(level)
            self.set_task_vel_level(level)
            time.sleep(0.05)
            
            # Nếu phân đoạn chỉ có đúng 1 điểm, dùng lệnh Move đơn lẻ (vì Waypoint yêu cầu tối thiểu 2 điểm)
            if len(seg) == 1:
                t = seg[0]
                if mtype == "MoveJ":
                    self.joint_move_to(t['joint'])
                else:
                    self.task_move_to(t['tcp'])
                if not self._wait_for_busy(cancel_check_cb):
                    return False
                continue

            if self.version == 2:
                with self.lock:
                    if not self.client: return False
                    old_timeout = self.client.time_out
                    self.client.set_timeout_sec(60.0)
                    
                    try:
                        try:
                            self.client.stop_motion()
                            time.sleep(0.05)
                        except Exception:
                            pass
                            
                        if mtype == "MoveJ":
                            res_clean = self.client.joint_waypoint_clean()
                            if res_clean:
                                raise Exception(f"Clean Joint Waypoints failed: {res_clean}")
                            for idx, t in enumerate(seg):
                                is_last = (idx == len(seg) - 1)
                                if is_last or not t.get('fillet', True):
                                    r_val = 0.0
                                else:
                                    r_val = float(t.get('radius', blend_radius_j))
                                res_app = self.client.joint_waypoint_append(t['joint'], 0, r_val)
                                if res_app:
                                    raise Exception(f"Append Joint Waypoint {idx+1} failed: {res_app}")
                            res_exec = self.client.joint_waypoint_execute()
                            if res_exec:
                                raise Exception(f"Execute Joint Waypoints failed: {res_exec}")
                        else:
                            res_clean = self.client.task_waypoint_clean()
                            if res_clean:
                                raise Exception(f"Clean Task Waypoints failed: {res_clean}")
                            for idx, t in enumerate(seg):
                                is_last = (idx == len(seg) - 1)
                                if is_last or not t.get('fillet', True):
                                    r_val_m = 0.0
                                else:
                                    r_val_raw = float(t.get('radius', 10.0))
                                    # Chuyển đổi mm sang mét nếu nhập đơn vị mm (ví dụ 10.0mm -> 0.010m)
                                    r_val_m = (r_val_raw / 1000.0) if r_val_raw >= 0.5 else r_val_raw
                                res_app = self.client.task_waypoint_append(t['tcp'], 0, r_val_m)
                                if res_app:
                                    raise Exception(f"Append Task Waypoint {idx+1} failed: {res_app}")
                            res_exec = self.client.task_waypoint_execute()
                            if res_exec:
                                raise Exception(f"Execute Task Waypoints failed: {res_exec}")
                    except Exception as e:
                        self._flush_socket()
                        raise
                    finally:
                        if self.client and hasattr(self.client, 'set_timeout_sec'):
                            self.client.set_timeout_sec(old_timeout)
            elif self.version == 3:
                with self.lock:
                    if not self.client: return False
                    if mtype == "MoveJ":
                        self.client.clear_joint_waypoint()
                        for t in seg:
                            self.client.add_joint_waypoint(t['joint'])
                        self.client.move_joint_waypoint()
                    else:
                        self.client.clear_task_waypoint()
                        for t in seg:
                            p = t['tcp']
                            p_mm = [p[0]*1000.0, p[1]*1000.0, p[2]*1000.0, p[3], p[4], p[5]]
                            self.client.add_task_waypoint(p_mm)
                        self.client.move_task_waypoint()
            
            # Đợi kết thúc phân đoạn
            if not self._wait_for_busy(cancel_check_cb):
                return False

        # Dọn sạch bộ đệm waypoint sau khi kết thúc toàn bộ chuỗi để giải phóng controller về chế độ thường
        if self.version == 2 and self.client:
            with self.lock:
                try:
                    self.client.joint_waypoint_clean()
                except Exception:
                    pass
                try:
                    self.client.task_waypoint_clean()
                except Exception:
                    pass
        elif self.version == 3 and self.client:
            with self.lock:
                try:
                    self.client.clear_joint_waypoint()
                    self.client.clear_task_waypoint()
                except Exception:
                    pass
        return True

    def stop_motion(self):
        """Dừng chuyển động tiêu chuẩn (KHÔNG gọi stop_emergency để tránh EMG Stop)."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        self.client.stop_motion()
                    elif self.version == 3:
                        self.client.stop_motion(stop_category=0)
                except Exception as e:
                    print(f"Lỗi stop_motion: {e}")
                    self._flush_socket()

    def stop_motion_full(self):
        """Dừng nặng + xóa waypoint queue. Chỉ dùng cho dừng chu trình (cycle stop)."""
        with self.lock:
            if self.client:
                try:
                    if self.version == 2:
                        try:
                            self.client.stop_motion()
                        except Exception:
                            pass
                        try:
                            self.client.joint_waypoint_clean()
                        except Exception:
                            pass
                        try:
                            self.client.task_waypoint_clean()
                        except Exception:
                            pass
                    elif self.version == 3:
                        try:
                            self.client.stop_motion(stop_category=0)
                        except Exception:
                            pass
                        try:
                            self.client.clear_joint_waypoint()
                        except Exception:
                            pass
                        try:
                            self.client.clear_task_waypoint()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Lỗi stop_motion_full: {e}")
                    self._flush_socket()

    def _wait_for_busy(self, cancel_check_cb=None):
        """Chờ robot bắt đầu và hoàn tất toàn bộ chuyển động phân đoạn."""
        # Pha 1: Chờ robot khởi tạo và bắt đầu di chuyển (tối đa 1.5s)
        start_init = time.time()
        while time.time() - start_init < 1.5:
            if cancel_check_cb and cancel_check_cb():
                self.stop_motion()
                return False
            status = self.get_robot_status()
            if status.get('busy', 0) == 1 or status.get('is_robot_moving', 0) == 1:
                break
            time.sleep(0.1)

        # Pha 2: Chờ robot hoàn tất toàn bộ chuyển động đến khi dừng hẳn (tối đa 60s)
        timeout = 60.0
        elapsed = 0.0
        while elapsed < timeout:
            if cancel_check_cb and cancel_check_cb():
                print("Phát hiện DỪNG CHU TRÌNH! Phát lệnh stop_motion ngắt robot lập tức...")
                self.stop_motion()
                return False
            status = self.get_robot_status()
            is_moving = status.get('busy', 0) == 1 or status.get('is_robot_moving', 0) == 1
            if not is_moving:
                break
            time.sleep(0.15)
            elapsed += 0.15
            
        if cancel_check_cb and cancel_check_cb():
            print("Phát hiện DỪNG CHU TRÌNH (sau khi đợi)! Phát lệnh ngắt...")
            self.stop_motion()
            return False
            
        time.sleep(0.1)
        return True

    def upload_json_program(self, program_json_str):
        with self.lock:
            if not self.client:
                return False
            try:
                if self.version == 2:
                    if hasattr(self.client, 'set_json_program'):
                        return self.client.set_json_program(program_json_str)
                elif self.version == 3:
                    # gRPC v3 support
                    if hasattr(self.client, 'play_program'):
                        pass
                return True
            except Exception as e:
                print(f"Lỗi nạp kịch bản xuống controller: {e}")
                return False
