import time
import math
import threading
import logging

logger = logging.getLogger("VirtualIndy7")


class VirtualIndyClient:
    """
    Bộ Giả Lập Robot Neuromeka Indy7 Toàn Phần (Virtual Cobot Engine).
    Hỗ trợ mô phỏng quỹ đạo chuyển động nội suy thực tế, quản lý I/O và an toàn.
    """
    def __init__(self, ip="127.0.0.1"):
        self.ip = ip
        self.version = 2
        self.client = self  # Self reference
        self.is_connected = True
        self.lock = threading.RLock()
        self._abort = threading.Event()
        self.timeout_fault = False
        self.timeout_message = ""
        self.is_executing_path = False

        # Tọa độ khớp và Task ban đầu (Vị trí Safe Retract)
        self.joint_pos = [0.0, -30.0, -110.0, 0.0, -40.0, 0.0]
        self.task_pos = [450.0, 0.0, 320.0, 180.0, 0.0, 0.0] # mm (v2 tự chia 1000 khi cần)
        self.target_joint = list(self.joint_pos)
        self.target_task = list(self.task_pos)
        self.is_moving = False

        # Servo & I/O states
        self.servo_actives = [True] * 6
        self.brake_actives = [False] * 6
        self.do_registers = [0] * 32
        self.di_registers = [1, 1, 1, 1] + [0] * 28  # DI 0: Có tô, DI 1: Kẹp rổ, DI 2: Temp OK, DI 3: Guard OK
        self.virtual_sensors = {0: 1, 1: 1, 2: 1, 3: 1}
        self.simulate_sensors = True

        # Trạng thái hệ thống
        self.robot_status = {
            'ready': 1, 'busy': 0, 'emergency': 0, 'collision': 0,
            'error': 0, 'home': 0, 'zero': 0, 'reset': 0, 'direct_teaching': 0,
            'is_robot_moving': 0, 'is_robot_ready': 1, 'is_emergency_stopped': 0,
            'is_collided': 0, 'is_error_state': 0
        }

        # Caching
        self.cached_joint = list(self.joint_pos)
        self.cached_tcp = [self.task_pos[0]/1000.0, self.task_pos[1]/1000.0, self.task_pos[2]/1000.0, self.task_pos[3], self.task_pos[4], self.task_pos[5]]
        self.cached_servo = (self.servo_actives, self.brake_actives)
        self.cached_status = dict(self.robot_status)
        self.cached_di = list(self.di_registers)

        # Background Motion Simulator Thread
        self.sim_running = True
        self.motion_thread = threading.Thread(target=self._motion_engine_loop, daemon=True)
        self.motion_thread.start()

    def connect(self):
        self.is_connected = True
        logger.info("🤖 Đã kết nối thành công đến Robot Giả Lập Virtual Indy7!")
        return True

    def disconnect(self):
        self.is_connected = False
        return True

    def _motion_engine_loop(self):
        """Vòng lặp nội suy quỹ đạo giả lập mượt mà (50Hz)"""
        while self.sim_running:
            if self.is_moving:
                moved = False
                # Nội suy góc khớp mượt
                for i in range(6):
                    diff = self.target_joint[i] - self.joint_pos[i]
                    if abs(diff) > 0.1:
                        step = max(-1.2, min(1.2, diff * 0.25))
                        self.joint_pos[i] += step
                        moved = True
                    else:
                        self.joint_pos[i] = self.target_joint[i]

                # Nội suy tọa độ TCP
                for i in range(3):
                    diff = self.target_task[i] - self.task_pos[i]
                    if abs(diff) > 0.5:
                        step = max(-6.0, min(6.0, diff * 0.25))
                        self.task_pos[i] += step
                        moved = True
                    else:
                        self.task_pos[i] = self.target_task[i]

                for i in range(3, 6):
                    diff = self.target_task[i] - self.task_pos[i]
                    if abs(diff) > 0.1:
                        step = max(-1.5, min(1.5, diff * 0.25))
                        self.task_pos[i] += step
                        moved = True
                    else:
                        self.task_pos[i] = self.target_task[i]

                if not moved:
                    self.is_moving = False
                    self.robot_status['busy'] = 0
                    self.robot_status['is_robot_moving'] = 0
                else:
                    self.robot_status['busy'] = 1
                    self.robot_status['is_robot_moving'] = 1

            self.cached_joint = list(self.joint_pos)
            self.cached_tcp = [self.task_pos[0]/1000.0, self.task_pos[1]/1000.0, self.task_pos[2]/1000.0, self.task_pos[3], self.task_pos[4], self.task_pos[5]]
            time.sleep(0.02)

    def get_joint_pos(self):
        return list(self.joint_pos)

    def get_task_pos(self):
        # Trả về mét cho XYZ nếu v2
        return [self.task_pos[0]/1000.0, self.task_pos[1]/1000.0, self.task_pos[2]/1000.0, self.task_pos[3], self.task_pos[4], self.task_pos[5]]

    def get_servo_state(self):
        return (list(self.servo_actives), list(self.brake_actives))

    def get_robot_status(self, force_fresh=False):
        return dict(self.robot_status)

    def get_all_states(self):
        return {
            'angles': list(self.joint_pos),
            'tcp': self.get_task_pos(),
            'servo_state': self.get_servo_state(),
            'status': self.get_robot_status()
        }

    def joint_move_to(self, q):
        if len(q) == 6:
            self.target_joint = [float(x) for x in q]
            self.is_moving = True
            return True
        return False

    def joint_move_by(self, dq):
        for i in range(min(6, len(dq))):
            self.target_joint[i] += float(dq[i])
        self.is_moving = True
        return True

    def task_move_to(self, p):
        if len(p) == 6:
            # Nếu đầu vào < 5.0 (tính bằng mét), quy đổi sang mm
            x = p[0]*1000.0 if abs(p[0]) < 5.0 else p[0]
            y = p[1]*1000.0 if abs(p[1]) < 5.0 else p[1]
            z = p[2]*1000.0 if abs(p[2]) < 5.0 else p[2]
            self.target_task = [x, y, z, float(p[3]), float(p[4]), float(p[5])]
            self.is_moving = True
            return True
        return False

    def task_move_by(self, dp):
        # dp có thể là mét
        scale = 1000.0 if abs(dp[0]) < 0.5 and abs(dp[1]) < 0.5 and abs(dp[2]) < 0.5 else 1.0
        self.target_task[0] += float(dp[0]) * scale
        self.target_task[1] += float(dp[1]) * scale
        self.target_task[2] += float(dp[2]) * scale
        for i in range(3, 6):
            self.target_task[i] += float(dp[i])
        self.is_moving = True
        return True

    def start_continuous_jog(self, axis_type: str, axis_idx: int, direction: int, speed_ratio: float = 0.5):
        dir_val = 1 if direction >= 0 else -1
        if axis_type == 'joint':
            dq = [0.0] * 6
            dq[axis_idx] = 1.0 * dir_val * speed_ratio
            self.joint_move_by(dq)
        else:
            dp = [0.0] * 6
            dp[axis_idx] = (3.0 * dir_val * speed_ratio) if axis_idx < 3 else (1.0 * dir_val * speed_ratio)
            self.task_move_by(dp)

    def stop_continuous_jog(self):
        self.stop_motion_light()

    def step_jog(self, axis_type: str, axis_idx: int, direction: int, step_val: float, speed_ratio: float = 0.5):
        dir_val = 1 if direction >= 0 else -1
        if axis_type == 'joint':
            dq = [0.0] * 6
            dq[axis_idx] = step_val * dir_val
            self.joint_move_by(dq)
        else:
            dp = [0.0] * 6
            dp[axis_idx] = step_val * dir_val
            self.task_move_by(dp)

    def stop_motion(self):
        self.is_moving = False
        self.target_joint = list(self.joint_pos)
        self.target_task = list(self.task_pos)
        self.robot_status['busy'] = 0

    def stop_motion_light(self):
        self.stop_motion()

    def emergency_stop(self):
        self.stop_motion()
        self.robot_status['emergency'] = 1
        self.robot_status['ready'] = 0

    def reset_robot(self):
        self.robot_status['emergency'] = 0
        self.robot_status['error'] = 0
        self.robot_status['collision'] = 0
        self.robot_status['ready'] = 1

    def recover_collision(self):
        self.reset_robot()

    def set_servo(self, list_of_booleans):
        val = bool(list_of_booleans[0]) if list_of_booleans else True
        self.servo_actives = [val] * 6
        self.robot_status['ready'] = 1 if val else 0

    def set_direct_teaching(self, enable):
        self.robot_status['direct_teaching'] = 1 if enable else 0

    def go_to_home_pos(self):
        return self.joint_move_to([0.0, -15.0, -90.0, 0.0, -75.0, 0.0])

    def go_to_safe_retract(self):
        return self.joint_move_to(SAFE_RETRACT_POSE)

    def go_to_zero_pos(self):
        return self.joint_move_to([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    def set_do(self, pin, state):
        if 0 <= pin < len(self.do_registers):
            self.do_registers[pin] = 1 if state else 0

    def get_di(self, pin=0):
        if self.simulate_sensors:
            return int(self.virtual_sensors.get(pin, 0))
        return self.di_registers[pin] if pin < len(self.di_registers) else 0

    def get_all_di(self):
        return list(self.di_registers)

    def set_virtual_sensor(self, pin, state):
        self.virtual_sensors[pin] = 1 if state else 0
        if 0 <= pin < len(self.di_registers):
            self.di_registers[pin] = 1 if state else 0

    def set_simulate_sensors(self, enable):
        self.simulate_sensors = bool(enable)

    def set_joint_vel_level(self, level): pass
    def set_task_vel_level(self, level): pass
    def set_tool_frame(self, tpos): return True
    def set_and_start_json_program(self, json_str): return True
    def get_last_error_info(self):
        return {'code': 0, 'msg': 'Robot giả lập hoạt động bình thường', 'joint': None, 'raw': None}

    def wait_for_motion_finish(self, timeout=30.0, cancel_check_cb=None):
        start = time.time()
        while self.is_moving and (time.time() - start < timeout):
            if cancel_check_cb and cancel_check_cb():
                self.stop_motion()
                return False
            time.sleep(0.05)
        return True

    def execute_waypoint_path(self, target_list, cancel_check_cb=None):
        self.is_executing_path = True
        for t in target_list:
            if cancel_check_cb and cancel_check_cb():
                break
            if t.get('type') == 'MoveL':
                self.task_move_to(t['task'])
            else:
                self.joint_move_to(t['joint'])
            self.wait_for_motion_finish(cancel_check_cb=cancel_check_cb)
            time.sleep(0.1)
        self.is_executing_path = False
        return True
