"""
Module Lõi Lập Trình & Thông Dịch Chu Trình Robot (Program Engine)
Hỗ trợ đầy đủ các khối lệnh: MoveJ, MoveL, Loop, While, If-Else, Set DO, Wait DI, Biến số, Log, Break/Continue.
"""

import time
import json
import uuid
import threading
from typing import List, Dict, Any, Optional, Callable


class ExecutionInterrupted(Exception):
    """Ngoại lệ khi người dùng yêu cầu Dừng chương trình."""
    pass


class BreakLoopSignal(Exception):
    """Tín hiệu thoát khỏi vòng lặp (Break)."""
    pass


class ContinueLoopSignal(Exception):
    """Tín hiệu nhảy sang vòng lặp kế tiếp (Continue)."""
    pass


class InstructionFactory:
    """Factory tạo đối tượng Instruction từ dict dữ liệu."""
    _registry = {}

    @classmethod
    def register(cls, type_name):
        def decorator(subclass):
            cls._registry[type_name] = subclass
            return subclass
        return decorator

    @classmethod
    def from_dict(cls, data: dict):
        itype = data.get("type", "")
        subclass = cls._registry.get(itype)
        if subclass:
            return subclass.from_dict(data)
        raise ValueError(f"Loại lệnh không xác định: {itype}")


class BaseInstruction:
    def __init__(self, comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        self.id = id_str if id_str else str(uuid.uuid4())[:8]
        self.comment = comment
        self.enabled = enabled

    @property
    def type(self) -> str:
        return "Base"

    def display_text(self) -> str:
        return "Lệnh cơ sở"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "comment": self.comment,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, d: dict):
        inst = cls(
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )
        return inst

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f" # {self.comment}" if self.comment else ""
        return f"{sp}pass{c}\n"

    def execute(self, context: 'ExecutionContext'):
        raise NotImplementedError


# ==============================================================================
# 1. MOTION INSTRUCTIONS
# ==============================================================================

@InstructionFactory.register("MovePoint")
class MovePointInstruction(BaseInstruction):
    def __init__(self, target_name: str = "P1", motion_type: str = "MoveJ",
                 speed: float = 200.0, wait_done: bool = True,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.target_name = target_name
        self.motion_type = motion_type  # "MoveJ" or "MoveL"
        self.speed = float(speed)
        self.wait_done = wait_done

    @property
    def type(self) -> str:
        return "MovePoint"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"🚀 {self.motion_type}({self.target_name}) - Tốc độ: {self.speed:.0f} mm/s{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "target_name": self.target_name,
            "motion_type": self.motion_type,
            "speed": self.speed,
            "wait_done": self.wait_done
        })
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            target_name=d.get("target_name", "P1"),
            motion_type=d.get("motion_type", "MoveJ"),
            speed=float(d.get("speed", 200.0)),
            wait_done=d.get("wait_done", True),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        if self.motion_type == "MoveJ":
            return f"{sp}robot.move_j(\"{self.target_name}\", speed={self.speed}){c}\n"
        else:
            return f"{sp}robot.move_l(\"{self.target_name}\", speed={self.speed}){c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        targets = context.get_targets()
        pt_data = None

        # Tìm điểm theo tên (ví dụ "P1", "P2"...) hoặc index
        if self.target_name in targets:
            pt_data = targets[self.target_name]
        else:
            # Thử parse số (P1 -> index 0)
            if self.target_name.startswith("P") and self.target_name[1:].isdigit():
                idx = int(self.target_name[1:]) - 1
                raw_list = context.get_raw_targets_list()
                if 0 <= idx < len(raw_list):
                    pt_data = raw_list[idx]

        if not pt_data:
            raise ValueError(f"Không tìm thấy tọa độ của điểm '{self.target_name}' trong danh sách điểm dạy!")

        client = context.client
        if not client or not context.is_connected():
            context.log(f"[Mô phỏng] {self.motion_type} tới {self.target_name} ({self.speed:.0f} mm/s)")
            context.wait_safe(0.5)
            return

        # Cài đặt tốc độ
        client.set_speed_ratio(int(max(5, min(100, (self.speed / 900.0) * 100))))

        mtype = self.motion_type
        if mtype == "MoveJ":
            joint = pt_data.get('joint')
            if not joint or len(joint) < 6:
                raise ValueError(f"Dữ liệu góc khớp của điểm '{self.target_name}' không hợp lệ!")
            client.joint_move_to(joint)
        elif mtype == "MoveL":
            tcp = pt_data.get('tcp')
            if not tcp or len(tcp) < 6:
                raise ValueError(f"Dữ liệu tọa độ TCP của điểm '{self.target_name}' không hợp lệ!")
            client.task_move_to(tcp)

        if self.wait_done:
            context.wait_motion_done()


# ==============================================================================
# 2. I/O & DELAY INSTRUCTIONS
# ==============================================================================

@InstructionFactory.register("SetDO")
class SetDOInstruction(BaseInstruction):
    def __init__(self, pin: int = 0, state: bool = True,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.pin = int(pin)
        self.state = bool(state)

    @property
    def type(self) -> str:
        return "SetDO"

    def display_text(self) -> str:
        st_text = "ON (BẬT)" if self.state else "OFF (TẮT)"
        c = f" // {self.comment}" if self.comment else ""
        return f"⚡ SET DO[{self.pin}] = {st_text}{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"pin": self.pin, "state": self.state})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            pin=int(d.get("pin", 0)),
            state=bool(d.get("state", True)),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        return f"{sp}robot.set_do({self.pin}, {self.state}){c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        client = context.client
        if client and context.is_connected():
            client.set_do(self.pin, self.state)
        context.log(f"SET DO[{self.pin}] = {'ON' if self.state else 'OFF'}")


@InstructionFactory.register("WaitDI")
class WaitDIInstruction(BaseInstruction):
    def __init__(self, pin: int = 0, state: int = 1, timeout: float = 30.0,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.pin = int(pin)
        self.state = int(state)
        self.timeout = float(timeout)

    @property
    def type(self) -> str:
        return "WaitDI"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        to_str = f" (Timeout: {self.timeout:.1f}s)" if self.timeout > 0 else " (Vô hạn)"
        return f"⏳ CHỜ DI[{self.pin}] == {self.state}{to_str}{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"pin": self.pin, "state": self.state, "timeout": self.timeout})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            pin=int(d.get("pin", 0)),
            state=int(d.get("state", 1)),
            timeout=float(d.get("timeout", 30.0)),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        return f"{sp}robot.wait_di({self.pin}, state={self.state}, timeout={self.timeout}){c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        client = context.client
        start_t = time.time()
        context.log(f"Bắt đầu chờ tín hiệu DI[{self.pin}] == {self.state}...")

        while True:
            context.check_interrupt()
            if client and context.is_connected():
                val = client.get_di(self.pin)
                if val == self.state:
                    context.log(f"✓ Đã nhận tín hiệu DI[{self.pin}] == {self.state} sau {time.time()-start_t:.1f}s")
                    break
            else:
                # Mô phỏng: Tự pass sau 1s
                if time.time() - start_t >= 1.0:
                    context.log(f"[Mô phỏng] Tự động kích hoạt DI[{self.pin}] == {self.state}")
                    break

            if self.timeout > 0 and (time.time() - start_t) > self.timeout:
                raise TimeoutError(f"Hết thời gian chờ (Timeout {self.timeout}s) cho tín hiệu DI[{self.pin}] == {self.state}!")

            time.sleep(0.05)


@InstructionFactory.register("WaitTime")
class WaitTimeInstruction(BaseInstruction):
    def __init__(self, seconds: float = 1.0,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.seconds = float(seconds)

    @property
    def type(self) -> str:
        return "WaitTime"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"⏱️ TẠM DỪNG: {self.seconds:.2f} giây{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"seconds": self.seconds})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            seconds=float(d.get("seconds", 1.0)),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        return f"{sp}robot.wait({self.seconds}){c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return
        context.log(f"Dừng nghỉ {self.seconds:.2f}s...")
        context.wait_safe(self.seconds)


# ==============================================================================
# 3. VARIABLES & LOGIC EXPRESSIONS
# ==============================================================================

@InstructionFactory.register("SetVar")
class SetVarInstruction(BaseInstruction):
    def __init__(self, var_name: str = "counter", expression: str = "counter + 1",
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.var_name = var_name.strip()
        self.expression = expression.strip()

    @property
    def type(self) -> str:
        return "SetVar"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"📝 BIẾN: {self.var_name} = {self.expression}{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"var_name": self.var_name, "expression": self.expression})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            var_name=d.get("var_name", "counter"),
            expression=d.get("expression", "counter + 1"),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        return f"{sp}{self.var_name} = {self.expression}{c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        val = context.eval_expression(self.expression)
        context.set_variable(self.var_name, val)
        context.log(f"Gán biến: {self.var_name} = {val}")


@InstructionFactory.register("Log")
class LogInstruction(BaseInstruction):
    def __init__(self, message: str = "Robot đang hoạt động...",
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.message = message

    @property
    def type(self) -> str:
        return "Log"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"💬 LOG: \"{self.message}\"{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"message": self.message})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            message=d.get("message", "Robot đang hoạt động..."),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        return f"{sp}robot.log(\"{self.message}\"){c}\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return
        # Cho phép nội suy biến số trong chuỗi log
        msg = self.message
        for k, v in context.variables.items():
            msg = msg.replace(f"{{{k}}}", str(v))
        context.log(f"[THÔNG BÁO] {msg}")


# ==============================================================================
# 4. CONTROL FLOW: LOOP, WHILE, IF-ELSE, BREAK, CONTINUE, STOP
# ==============================================================================

@InstructionFactory.register("LoopCount")
class LoopCountInstruction(BaseInstruction):
    def __init__(self, count: int = 5, var_name: str = "i",
                 children: Optional[List[BaseInstruction]] = None,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.count = int(count)  # -1 hoặc 0 nghĩa là vô tận
        self.var_name = var_name.strip() if var_name else "i"
        self.children = children if children is not None else []

    @property
    def type(self) -> str:
        return "LoopCount"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        cnt_str = f"{self.count} LẦN" if self.count > 0 else "VÔ TẬN (Infinite)"
        return f"🔁 VÒNG LẶP (LOOP): {cnt_str} (Biến: {self.var_name}){c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "count": self.count,
            "var_name": self.var_name,
            "children": [c.to_dict() for c in self.children]
        })
        return d

    @classmethod
    def from_dict(cls, d: dict):
        insts = []
        for cd in d.get("children", []):
            try:
                insts.append(InstructionFactory.from_dict(cd))
            except Exception as e:
                print(f"Lỗi load child instruction trong Loop: {e}")
        return cls(
            count=int(d.get("count", 5)),
            var_name=d.get("var_name", "i"),
            children=insts,
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        lines = []
        if self.count > 0:
            lines.append(f"{sp}for {self.var_name} in range({self.count}):{c}\n")
        else:
            lines.append(f"{sp}while not robot.is_stopped():{c}\n")

        if not self.children:
            lines.append(f"{sp}    pass\n")
        else:
            for ch in self.children:
                lines.append(ch.to_python(indent + 1))
        return "".join(lines)

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        iteration = 0
        while True:
            context.check_interrupt()
            if self.count > 0 and iteration >= self.count:
                break

            context.set_variable(self.var_name, iteration + 1)
            context.log(f"--- Vòng lặp {self.var_name} = {iteration + 1}" + (f"/{self.count}" if self.count > 0 else "") + " ---")

            try:
                for idx, child in enumerate(self.children):
                    context.check_interrupt()
                    context.notify_step(child)
                    child.execute(context)
            except BreakLoopSignal:
                context.log("Đã nhận lệnh BREAK - Thoát vòng lặp")
                break
            except ContinueLoopSignal:
                context.log("Đã nhận lệnh CONTINUE - Bắt đầu vòng lặp tiếp theo")

            iteration += 1


@InstructionFactory.register("While")
class WhileInstruction(BaseInstruction):
    def __init__(self, condition: str = "di(0) == 1",
                 children: Optional[List[BaseInstruction]] = None,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.condition = condition.strip()
        self.children = children if children is not None else []

    @property
    def type(self) -> str:
        return "While"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"🔄 VÒNG LẶP WHILE: [{self.condition}]{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "condition": self.condition,
            "children": [c.to_dict() for c in self.children]
        })
        return d

    @classmethod
    def from_dict(cls, d: dict):
        insts = []
        for cd in d.get("children", []):
            try:
                insts.append(InstructionFactory.from_dict(cd))
            except Exception as e:
                print(f"Lỗi load child trong While: {e}")
        return cls(
            condition=d.get("condition", "di(0) == 1"),
            children=insts,
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        # Format condition pythonic
        cond_py = self.condition.replace("di(", "robot.get_di(").replace("do(", "robot.get_do(")
        lines = [f"{sp}while {cond_py} and not robot.is_stopped():{c}\n"]
        if not self.children:
            lines.append(f"{sp}    pass\n")
        else:
            for ch in self.children:
                lines.append(ch.to_python(indent + 1))
        return "".join(lines)

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        while True:
            context.check_interrupt()
            is_true = context.eval_condition(self.condition)
            if not is_true:
                break

            try:
                for child in self.children:
                    context.check_interrupt()
                    context.notify_step(child)
                    child.execute(context)
            except BreakLoopSignal:
                break
            except ContinueLoopSignal:
                pass


@InstructionFactory.register("IfCondition")
class IfConditionInstruction(BaseInstruction):
    def __init__(self, condition: str = "di(0) == 1",
                 then_children: Optional[List[BaseInstruction]] = None,
                 else_children: Optional[List[BaseInstruction]] = None,
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.condition = condition.strip()
        self.then_children = then_children if then_children is not None else []
        self.else_children = else_children if else_children is not None else []

    @property
    def type(self) -> str:
        return "IfCondition"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"🔀 ĐIỀU KIỆN IF: [{self.condition}]{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "condition": self.condition,
            "then_children": [c.to_dict() for c in self.then_children],
            "else_children": [c.to_dict() for c in self.else_children]
        })
        return d

    @classmethod
    def from_dict(cls, d: dict):
        then_i = []
        for cd in d.get("then_children", []):
            try:
                then_i.append(InstructionFactory.from_dict(cd))
            except Exception as e:
                print(f"Lỗi load then_child trong If: {e}")
        else_i = []
        for cd in d.get("else_children", []):
            try:
                else_i.append(InstructionFactory.from_dict(cd))
            except Exception as e:
                print(f"Lỗi load else_child trong If: {e}")
        return cls(
            condition=d.get("condition", "di(0) == 1"),
            then_children=then_i,
            else_children=else_i,
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        c = f"  # {self.comment}" if self.comment else ""
        cond_py = self.condition.replace("di(", "robot.get_di(").replace("do(", "robot.get_do(")
        lines = [f"{sp}if {cond_py}:{c}\n"]
        if not self.then_children:
            lines.append(f"{sp}    pass\n")
        else:
            for ch in self.then_children:
                lines.append(ch.to_python(indent + 1))

        if self.else_children:
            lines.append(f"{sp}else:\n")
            for ch in self.else_children:
                lines.append(ch.to_python(indent + 1))

        return "".join(lines)

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if not self.enabled:
            return

        is_true = context.eval_condition(self.condition)
        context.log(f"Kiểm tra IF [{self.condition}] -> Kết quả: {'ĐÚNG (True)' if is_true else 'SAI (False)'}")

        branch = self.then_children if is_true else self.else_children
        for child in branch:
            context.check_interrupt()
            context.notify_step(child)
            child.execute(context)


@InstructionFactory.register("Break")
class BreakInstruction(BaseInstruction):
    @property
    def type(self) -> str:
        return "Break"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"🛑 THOÁT VÒNG LẶP (BREAK){c}"

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        return f"{sp}break\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if self.enabled:
            raise BreakLoopSignal()


@InstructionFactory.register("Continue")
class ContinueInstruction(BaseInstruction):
    @property
    def type(self) -> str:
        return "Continue"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"⏭️ BỎ QUA VÒNG LẶP (CONTINUE){c}"

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        return f"{sp}continue\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if self.enabled:
            raise ContinueLoopSignal()


@InstructionFactory.register("StopProgram")
class StopProgramInstruction(BaseInstruction):
    def __init__(self, message: str = "Hoàn tất chương trình!",
                 comment: str = "", enabled: bool = True, id_str: Optional[str] = None):
        super().__init__(comment, enabled, id_str)
        self.message = message

    @property
    def type(self) -> str:
        return "StopProgram"

    def display_text(self) -> str:
        c = f" // {self.comment}" if self.comment else ""
        return f"⛔ DỪNG CHƯƠNG TRÌNH: \"{self.message}\"{c}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"message": self.message})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            message=d.get("message", "Hoàn tất chương trình!"),
            comment=d.get("comment", ""),
            enabled=d.get("enabled", True),
            id_str=d.get("id")
        )

    def to_python(self, indent: int = 1) -> str:
        sp = "    " * indent
        return f"{sp}robot.log(\"Dừng chương trình: {self.message}\")\n{sp}return\n"

    def execute(self, context: 'ExecutionContext'):
        context.check_interrupt()
        if self.enabled:
            context.log(f"⛔ Lệnh dừng chương trình: {self.message}")
            raise ExecutionInterrupted(self.message)


# ==============================================================================
# 5. EXECUTION CONTEXT & PROGRAM RUNNER
# ==============================================================================

class ExecutionContext:
    def __init__(self, client, saved_targets_provider: Callable[[], dict],
                 log_callback: Optional[Callable[[str], None]] = None,
                 step_callback: Optional[Callable[[BaseInstruction], None]] = None):
        self.client = client
        self.saved_targets_provider = saved_targets_provider
        self.log_callback = log_callback
        self.step_callback = step_callback

        self.variables: Dict[str, Any] = {}
        self.stop_requested = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # set = running, clear = paused

    def get_targets(self) -> dict:
        if callable(self.saved_targets_provider):
            res = self.saved_targets_provider()
            if isinstance(res, dict):
                return res
            elif isinstance(res, list):
                # Map list sang dict P1, P2...
                return {f"P{i+1}": pt for i, pt in enumerate(res)}
        return {}

    def get_raw_targets_list(self) -> list:
        if callable(self.saved_targets_provider):
            res = self.saved_targets_provider()
            if isinstance(res, list):
                return res
            elif isinstance(res, dict):
                return list(res.values())
        return []

    def is_connected(self) -> bool:
        return bool(self.client and getattr(self.client, 'client', None))

    def log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(f"[ProgramLog] {msg}")

    def notify_step(self, instruction: BaseInstruction):
        self.pause_event.wait()
        if self.step_callback:
            self.step_callback(instruction)

    def check_interrupt(self):
        self.pause_event.wait()
        if self.stop_requested:
            raise ExecutionInterrupted("Người dùng đã yêu cầu dừng chương trình!")

    def wait_safe(self, seconds: float):
        end_time = time.time() + seconds
        while time.time() < end_time:
            self.check_interrupt()
            time.sleep(min(0.05, max(0.0, end_time - time.time())))

    def wait_motion_done(self, timeout: float = 45.0):
        start_t = time.time()
        time.sleep(0.15)  # Chờ controller bắt đầu nhận lệnh
        while time.time() - start_t < timeout:
            self.check_interrupt()
            if not self.is_connected():
                break
            st = self.client.get_robot_status()
            is_busy = (st.get('busy', 0) == 1 or st.get('is_robot_moving', 0) == 1)
            if not is_busy:
                break
            time.sleep(0.05)

    def set_variable(self, name: str, value: Any):
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def eval_expression(self, expr: str) -> Any:
        safe_env = {
            "di": lambda pin: self.client.get_di(pin) if (self.client and self.is_connected()) else 0,
            "do": lambda pin: self.client.get_do(pin) if (self.client and self.is_connected()) else 0,
            "True": True, "False": False, "None": None,
            "abs": abs, "min": min, "max": max, "round": round, "int": int, "float": float, "str": str, "bool": bool
        }
        safe_env.update(self.variables)
        try:
            return eval(expr, {"__builtins__": {}}, safe_env)
        except Exception as e:
            raise ValueError(f"Lỗi cú pháp biểu thức '{expr}': {e}")

    def eval_condition(self, cond: str) -> bool:
        res = self.eval_expression(cond)
        return bool(res)


class Program:
    """Tập hợp kịch bản chương trình hoàn chỉnh."""
    def __init__(self, name: str = "Chương Trình Robot Indy7", description: str = ""):
        self.name = name
        self.description = description
        self.instructions: List[BaseInstruction] = []
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def add_instruction(self, inst: BaseInstruction):
        self.instructions.append(inst)

    def to_dict(self) -> dict:
        return {
            "title": "Neuromeka Indy Program Workflow",
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "instructions": [inst.to_dict() for inst in self.instructions]
        }

    @classmethod
    def from_dict(cls, data: dict):
        prog = cls(
            name=data.get("name", "Chương Trình Robot"),
            description=data.get("description", "")
        )
        prog.created_at = data.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        prog.instructions = []
        for idata in data.get("instructions", []):
            try:
                inst = InstructionFactory.from_dict(idata)
                prog.instructions.append(inst)
            except Exception as e:
                print(f"Lỗi load instruction: {e}")
        return prog

    def save_to_json(self, file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4, ensure_ascii=False)

    @classmethod
    def load_from_json(cls, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_python_code(self) -> str:
        lines = [
            "# ==============================================================================",
            f"# Chương trình Robot: {self.name}",
            f"# Mô tả: {self.description}",
            f"# Thời gian tạo: {self.created_at}",
            "# ==============================================================================\n",
            "def run_workflow(robot, points):\n",
            "    robot.log(\"Bắt đầu thực thi chương trình...\")\n"
        ]

        if not self.instructions:
            lines.append("    pass\n")
        else:
            for inst in self.instructions:
                lines.append(inst.to_python(indent=1))

        lines.append("    robot.log(\"✓ Chương trình hoàn tất thành công!\")\n\n")
        lines.append("run_workflow(robot, points)\n")
        return "".join(lines)


class ProgramInterpreter:
    """Trình thực thi chương trình hỗ trợ đa luồng và tương tác giao diện."""
    def __init__(self, program: Program, client, saved_targets_provider,
                 log_callback=None, step_callback=None, finish_callback=None):
        self.program = program
        self.client = client
        self.saved_targets_provider = saved_targets_provider
        self.log_callback = log_callback
        self.step_callback = step_callback
        self.finish_callback = finish_callback

        self.context: Optional[ExecutionContext] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return

        self.is_running = True
        self.context = ExecutionContext(
            client=self.client,
            saved_targets_provider=self.saved_targets_provider,
            log_callback=self.log_callback,
            step_callback=self.step_callback
        )

        def worker():
            err = None
            msg = "Thành công"
            try:
                self.context.log(f"▶ KHỞI CHẠY CHƯƠNG TRÌNH: '{self.program.name}' ({len(self.program.instructions)} lệnh)")
                for inst in self.program.instructions:
                    self.context.check_interrupt()
                    self.context.notify_step(inst)
                    inst.execute(self.context)
                self.context.log("✓ CHƯƠNG TRÌNH ĐÃ HOÀN TẤT THÀNH CÔNG!")
            except ExecutionInterrupted as e:
                msg = str(e)
                self.context.log(f"■ Dừng chương trình: {msg}")
            except Exception as e:
                err = e
                msg = f"Lỗi thực thi: {e}"
                self.context.log(f"❌ LỖI TRONG QUÁ TRÌNH THỰC THI: {e}")
            finally:
                self.is_running = False
                if self.finish_callback:
                    self.finish_callback(err is None, msg)

        self.thread = threading.Thread(target=worker, daemon=True, name="ProgramInterpreter-Worker")
        self.thread.start()

    def pause(self):
        if self.context:
            self.context.pause_event.clear()
            self.context.log("⏸️ ĐÃ TẠM DỪNG CHƯƠNG TRÌNH")

    def resume(self):
        if self.context:
            self.context.pause_event.set()
            self.context.log("▶️ TIẾP TỤC CHƯƠNG TRÌNH")

    def stop(self):
        if self.context:
            self.context.stop_requested = True
            self.context.pause_event.set()
        if self.client and getattr(self.client, 'client', None):
            try:
                self.client.stop_motion()
            except Exception:
                pass
