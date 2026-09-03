# CHI TIẾT THUẬT TOÁN CONVEYOR TRACKING TRÊN ROBOT SCARA QKM (BÁM ĐUỔI BĂNG TẢI THỜI GIAN THỰC)

> **TÀI LIỆU KỸ THUẬT CHUYÊN SÂU PHỤC VỤ BẢO VỆ ĐỒ ÁN / BÁO CÁO THỰC TẬP**  
> **TRƯỜNG ĐẠI HỌC BÁCH KHOA - ĐHQG TP.HCM — KHOA ĐIỆN - ĐIỆN TỬ**  
> **BỘ MÔN:** TỰ ĐỘNG HÓA  
> **SINH VIÊN THỰC HIỆN:** Nguyễn Hữu Bằng — **MSSV:** 2310282  
> **CHUYÊN NGÀNH:** Kỹ thuật Điều khiển và Tự động hóa — Khóa 2023  
> **ĐƠN VỊ THỰC TẬP:** Công ty Cổ phần Giải pháp Tự động hóa ETEK  

---

## 1. TỔNG QUAN VỀ CONVEYOR TRACKING & BẢN CHẤT VẬT LÝ

### 1.1. Định nghĩa Conveyor Tracking
**Conveyor Tracking (Đồng bộ bám đuổi băng tải)** là kỹ thuật điều khiển động học thời gian thực (Real-time Dynamic Kinematics) cho phép đầu công tác (Tool Center Point - TCP) của Robot đồng bộ hoàn toàn với chuyển động của vật thể trên băng tải. 

Mục tiêu cốt lõi: **Robot thực hiện thao tác gắp (Pick) hoặc đặt (Place) chính xác tuyệt đối khi băng tải đang chạy liên tục mà không cần dừng băng tải (Zero-stop Continuous Flow)**.

```
                           [CAMERA HIK VISIONMASTER]
                                      │ (Chụp ảnh tĩnh lúc t₀)
  [CẢM BIẾN TRIGGER] ───────────────► │ ──────► [MẠNG ETHERNET TCP/IP]
   (Chốt xung Encoder E₀)             ▼                    │ (Tọa độ gốc X₀, Y₀, Rz₀)
  ──────────────────────────► [BĂNG TẢI CHUYỂN ĐỘNG] ─────►▼
   (Gắn Rotary Encoder)               │            [ROBOT SCARA QKM]
   [ENCODER BĂNG TẢI] ────────────────┘            (Vòng lặp điều khiển 1ms)
                                                   (Đồng tốc & Gắp phôi)
```

### 1.2. Phân tích nguyên lý: Camera 1 lần vs Robot 1000Hz
- **Ngộ nhận thường gặp:** Nhiều người nghĩ rằng camera phải quay video liên tục 1000 khung hình/giây để bám theo vật thể.
- **Thực tế kỹ thuật:**
  1. **Camera chỉ chụp ĐÚNG 1 LẦN** tại thời điểm kích hoạt $t_0$. Thời gian xử lý ảnh (Contour/Pattern Matching) mất khoảng $30 - 80\,\text{ms}$.
  2. **Bộ điều khiển Robot (Motion Controller) chạy vòng lặp ngắt thời gian thực ở tần số 1000Hz (chu kỳ $T_{loop} = 1\,\text{ms}$)**.
  3. Robot liên tục đọc xung phản hồi từ **Encoder** gắn trên trục băng tải để tự động tính toán bù tọa độ theo phương trình động học:
     $$\text{Tọa độ thời gian thực } P(t) = P_0 + \Delta S(t)$$

---

## 2. CƠ CHẾ KHÓA XUNG PHẦN CỨNG (HARDWARE POSITION LATCH)

Độ chính xác của Conveyor Tracking phụ thuộc vào khả năng đồng bộ thời gian giữa **thời điểm chụp ảnh** và **giá trị xung Encoder**.

```
 Tín hiệu cảm biến Trigger (Vật đi qua) ──────┐
                                              ├──► [Mạch ngắt phần cứng (Hardware Latch)] ──► Chốt E₀ (Độ trễ < 1µs)
                                              └──► [Ngõ Trigger Camera] ─────────────────► Chụp ảnh tại t₀
```

1. **Khi vật thể chạm cảm biến quang Trigger:**
   - Một xung mức cao ($24\,\text{VDC}$) kích hoạt chân ngắt cứng của Robot QKM.
   - Thanh ghi đếm xung tốc độ cao (High-Speed Counter) chốt tức thì giá trị xung hiện tại:
     $$E_0 = \text{Encoder\_Counter\_Value}(t_0)$$
   - Độ trễ chốt xung phần cứng chỉ tính bằng **Micro-giây ($\tau_{latch} < 1\,\mu\text{s}$)**.
2. **Camera chụp ảnh và tính toán tọa độ ban đầu:**
   - VisionMaster xử lý và gửi về tọa độ tĩnh ban đầu trong không gian Robot:
     $$P_0 = \begin{bmatrix} X_0 \\ Y_0 \\ Z_0 \\ Rz_0 \end{bmatrix}$$
3. **Cặp dữ liệu "Điểm neo gốc" (Anchor Point):**
   - Bộ điều khiển Robot liên kết $(P_0, E_0)$ thành một thực thể duy nhất đại diện cho viên kẹo đó.

---

## 3. MÔ HÌNH TOÁN HỌC & THUẬT TOÁN NỘI SUY THỜI GIAN THỰC (1ms LOOP)

### 3.1. Thiết lập các Hệ tọa độ (Coordinate Frames)

```
       {O_robot} (Robot Base Frame - Cố định)
           │
           │ Ma trận biến đổi T_Base_Conv(t)
           ▼
       {O_conv(t)} (Hệ quy chiếu băng tải - Di động theo thời gian)
           │
           │ Tọa độ tương đối cố định T_Conv_Candy
           ▼
       {P_target(t)} (Vị trí viên kẹo trong không gian thực)
```

1. **Hệ tọa độ gốc Robot $\{O_{robot}\}$:** Gốc đặt tại tâm trục đế của Robot SCARA QKM.
2. **Hệ tọa độ Camera $\{O_{cam}\}$:** Gốc đặt tại tâm cảm biến quang học của camera.
3. **Hệ tọa độ di động Băng tải $\{O_{conv}(t)\}$:** Gắn trên mặt băng tải, chuyển động tịnh tiến cùng vận tốc với băng tải.

### 3.2. Phương trình động học dịch chuyển dọc băng tải

Tại chu kỳ ngắt thời gian thực thứ $k$ (thời điểm $t_k = k \times 1\,\text{ms}$):

1. **Độ lệch xung từ thời điểm chụp:**
   $$\Delta E(t_k) = E(t_k) - E_0 \quad (\text{xung})$$

2. **Quãng đường di chuyển vật lý của băng tải ($\text{mm}$):**
   $$\Delta S(t_k) = \Delta E(t_k) \times K_{scale}$$
   *Trong đó: $K_{scale}$ là hệ số tỉ lệ quy đổi $(\text{mm/xung})$ thu được sau quá trình Calib băng tải.*

3. **Véc-tơ vị trí tức thời của vật thể trong hệ quy chiếu Robot:**
   Giả sử băng tải chuyển động theo véc-tơ đơn vị hướng $\vec{u} = [\cos\theta, \sin\theta, 0]^T$ (với $\theta$ là góc nghiêng của băng tải so với trục $X$ của Robot):

   $$\begin{cases}
   X_{target}(t_k) = X_0 + \Delta S(t_k) \cdot \cos\theta \\
   Y_{target}(t_k) = Y_0 + \Delta S(t_k) \cdot \sin\theta \\
   Z_{target}(t_k) = Z_{surface} \\
   Rz_{target}(t_k) = Rz_0
   \end{cases}$$

4. **Vận tốc tức thời của băng tải (để bù gia tốc động lực học):**
   $$v_{conv}(t_k) = \frac{E(t_k) - E(t_{k-1})}{T_{loop}} \times K_{scale} \quad (\text{mm/s})$$

---

## 4. GIẢI BÀI TOÁN ĐỘNG HỌC NGƯỢC SCARA (INVERSE KINEMATICS)

Robot SCARA QKM có cấu hình 4 bậc tự do ($RRPR$):
- Khớp 1 ($\theta_1$): Khớp quay vai (Arm 1, chiều dài $L_1$).
- Khớp 2 ($\theta_2$): Khớp quay khuỷu (Arm 2, chiều dài $L_2$).
- Khớp 3 ($d_3$): Khớp tịnh tiến trục $Z$ lên/xuống.
- Khớp 4 ($\theta_4$): Khớp xoay đầu giác hút $Rz$.

```
           (Khớp vai J1) [L1] ──── (Khớp khuỷu J2) [L2] ──── (Trục Z & Rz J3, J4)
               θ1                       θ2                         d3, θ4
```

### 4.1. Động học thuận (Forward Kinematics)
$$\begin{cases}
X = L_1 \cos\theta_1 + L_2 \cos(\theta_1 + \theta_2) \\
Y = L_1 \sin\theta_1 + L_2 \sin(\theta_1 + \theta_2) \\
Z = -d_3 \\
Rz = \theta_1 + \theta_2 + \theta_4
\end{cases}$$

### 4.2. Động học ngược thời gian thực (Real-time Inverse Kinematics)
Tại mỗi mili-giây $t_k$, Robot nhận tọa độ mục tiêu $(X_{target}(t_k), Y_{target}(t_k), Z_{target}(t_k), Rz_{target}(t_k))$ và giải nghiệm góc khớp tức thời:

1. **Tính góc khớp khuỷu $\theta_2$:**
   $$\cos\theta_2 = \frac{X_{target}^2 + Y_{target}^2 - L_1^2 - L_2^2}{2 L_1 L_2}$$
   $$\theta_2 = \text{atan2}\left(\pm\sqrt{1 - \cos^2\theta_2}, \cos\theta_2\right) \quad (\text{Chọn cấu hình Right/Left-arm})$$

2. **Tính góc khớp vai $\theta_1$:**
   $$\theta_1 = \text{atan2}(Y_{target}, X_{target}) - \text{atan2}\left(L_2 \sin\theta_2, L_1 + L_2 \cos\theta_2\right)$$

3. **Tính trục trượt $d_3$ và khớp xoay $\theta_4$:**
   $$d_3 = -Z_{target}$$
   $$\theta_4 = Rz_{target} - (\theta_1 + \theta_2)$$

---

## 5. CẤU TRÚC DỮ LIỆU & QUẢN LÝ HÀNG ĐỢI VẬT THỂ (OBJECT FIFO QUEUE)

Để xử lý trường hợp trên băng tải có đồng thời **nhiều viên kẹo nối đuôi nhau**, bộ điều khiển QKM duy trì một **Hàng đợi FIFO Tracking (Tracking Queue)**.

```c
// Cấu trúc dữ liệu cho một vật thể theo vết (Object Tracking Struct)
typedef struct {
    uint32_t object_id;       // ID định danh duy nhất (1, 2, 3...)
    double x_init;            // Tọa độ gốc X0 (mm)
    double y_init;            // Tọa độ gốc Y0 (mm)
    double z_init;            // Tọa độ gốc Z0 (mm)
    double rz_init;           // Góc xoay ban đầu Rz0 (độ)
    int64_t encoder_latch;    // Giá trị xung Encoder lúc chốt E0
    uint8_t candy_type;       // Loại kẹo: 1 = Sâu, 2 = Bạch tuộc
    uint8_t status;           // 0: WAITING, 1: IN_WINDOW, 2: TRACKING, 3: PICKED, 4: ABANDONED
} TrackingObject_t;
```

### Sơ đồ chuyển trạng thái của vật thể (State Machine):
```
 [TRIGGER & CHỤP] ──► WAITING (Đang trôi về phía Robot)
                          │
                          ▼ (Khi X(t) > Vạch bắt đầu)
                     IN_WINDOW (Nằm trong vùng đón bắt)
                          │
                          ▼ (Robot tiếp cận & đồng tốc)
                     TRACKING (Khóa đồng tốc v_robot = v_conv)
                          │
                          ▼ (Hạ hút chân không thành công)
                      PICKED (Đã gắp -> Nhấc lên đưa sang khay)
```

- **Cơ chế chống tràn hàng đợi:** Nếu một viên kẹo trôi qua hết tầm với của Robot mà chưa gắp được (vượt quá vạch *Downstream Limit*), trạng thái chuyển sang `ABANDONED` và được tự động giải phóng khỏi bộ nhớ để nhường quyền ưu tiên cho viên kẹo tiếp theo.

---

## 6. QUY TRÌNH HIỆU CHUẨN TOÁN HỌC 2 PHA (TWO-PHASE CALIBRATION)

### 6.1. Pha 1: Hiệu chuẩn Camera $\leftrightarrow$ Robot (Camera Calibration 9 Điểm)
Dùng một tấm phẳng chứa 9 điểm mốc tròn chuẩn (Nine-Point Grid).

- Đọc 9 tọa độ Pixel từ VisionMaster: $(u_i, v_i)$ với $i = 1 \dots 9$.
- Dạy Robot chạm đầu TCP vào 9 điểm tương ứng: $(X_i, Y_i)$ với $i = 1 \dots 9$.
- Giải phương trình hồi quy ma trận Affine 2D:
  $$\begin{bmatrix} X \\ Y \\ 1 \end{bmatrix} = \begin{bmatrix} a_{11} & a_{12} & t_x \\ a_{21} & a_{22} & t_y \\ 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} u \\ v \\ 1 \end{bmatrix}$$

### 6.2. Pha 2: Hiệu chuẩn Băng tải $\leftrightarrow$ Robot (Conveyor Calibration)
1. Dán một điểm mốc $M$ trên mặt băng tải.
2. Dừng băng tải ở vị trí $1$: Dùng Robot rà chạm điểm $M \rightarrow$ Lưu tọa độ $P_1(X_1, Y_1)$ và xung $E_1$.
3. Cho băng tải chạy một đoạn đến vị trí $2$: Rà chạm lại điểm $M \rightarrow$ Lưu tọa độ $P_2(X_2, Y_2)$ và xung $E_2$.
4. **Tính toán thông số đặc trưng:**
   - **Véc-tơ hướng di chuyển băng tải:**
     $$\vec{u} = \frac{P_2 - P_1}{\|P_2 - P_1\|} = [\cos\theta, \sin\theta]^T$$
   - **Hệ số quy đổi xung/mm:**
     $$K_{scale} = \frac{\sqrt{(X_2 - X_1)^2 + (Y_2 - Y_1)^2}}{|E_2 - E_1|} \quad (\text{mm/xung})$$

---

## 7. KIỂM SOÁT VÙNG LÀM VIỆC & AN TOÀN (TRACKING WINDOWS)

Để tránh Robot bị va đập cơ khí hoặc vượt quá giới hạn góc quay (Singularity Point), khu vực băng tải được phân thành 3 vùng giới hạn:

```
  BĂNG TẢI CHẠY ──► [Camera] ──► |  VÙNG CHỜ  | ──► [UPSTREAM LIMIT] ──► |  VÙNG GẮP TRACKING  | ──► [DOWNSTREAM LIMIT] ──► | VÙNG BỎ QUA |
                                 (Waiting)          (Vạch bắt đầu)          (Tối ưu độ chính xác)        (Vạch kết thúc)        (Abandoned)
```

1. **Vạch bắt đầu (Upstream Limit / Start Window):** Điểm đầu tiên Robot có thể vươn tới gắp. Khi kẹo vượt qua vạch này, Robot mới kích hoạt tác vụ bám đuổi.
2. **Vùng gắp tối ưu (Tracking Execution Window):** Vùng có độ cứng vững cơ khí cao nhất, góc mở cánh tay SCARA tối ưu ($45^\circ \le \theta_2 \le 135^\circ$).
3. **Vạch kết thúc (Downstream Limit / Abandon Limit):** Nếu kẹo trôi qua vạch này mà chu trình gắp chưa bắt đầu, Robot lập tức hủy lệnh gắp để tránh gập khớp hoặc chạm hành trình.

---

## 8. MÃ GIẢ VÒNG LẶP ĐIỀU KHIỂN THỜI GIAN THỰC (REAL-TIME PSEUDOCODE)

```python
# THUẬT TOÁN ĐIỀU KHIỂN CONVEYOR TRACKING (CHẠY ĐỊNH KỲ 1ms TRÊN CONTROLLER QKM)

def RealTime_Conveyor_Tracking_Loop():
    while System_Running:
        # 1. Đọc giá trị Encoder băng tải hiện tại
        current_encoder = Read_HighSpeed_Encoder_Counter()
        
        # 2. Duyệt qua danh sách vật thể trong hàng đợi FIFO
        for obj in Tracking_Queue:
            if obj.status == STATUS_WAITING or obj.status == STATUS_IN_WINDOW:
                # Tính toán quãng đường trôi
                delta_E = current_encoder - obj.encoder_latch
                delta_S = delta_E * K_scale
                
                # Cập nhật tọa độ tức thời (X, Y)
                obj.current_X = obj.x_init + delta_S * cos(theta_conveyor)
                obj.current_Y = obj.y_init + delta_S * sin(theta_conveyor)
                
                # Kiểm tra ranh giới Tracking Window
                if obj.current_X >= UPSTREAM_LIMIT and obj.current_X <= DOWNSTREAM_LIMIT:
                    obj.status = STATUS_IN_WINDOW
                elif obj.current_X > DOWNSTREAM_LIMIT:
                    obj.status = STATUS_ABANDONED  # Bỏ qua vật thể quá tầm với
                    
        # 3. Lập kế hoạch điều khiển cho Robot
        target_obj = Get_First_Valid_Object_In_Window(Tracking_Queue)
        
        if target_obj != None and Robot_State == STATE_IDLE:
            # Bắt đầu chu trình bám đuổi
            Robot_State = STATE_TRACKING
            
            # Tính toán vận tốc đồng tốc v_robot = v_conveyor
            v_conv = Calculate_Conveyor_Speed(current_encoder)
            
            # Nội suy chuyển động tiếp cận (Trapezoidal / S-Curve Velocity Profile)
            Execute_Sync_Motion(target_obj.current_X, target_obj.current_Y, target_obj.rz_init, v_conv)
            
            # Hạ trục Z và kích hoạt giác hút chân không
            Lower_Z_Axis(Z_PICK_HEIGHT)
            Turn_On_Vacuum_Valve()
            Wait_Vacuum_Sensor_Feedback()
            
            # Nhấc trục Z lên độ cao an toàn và ngắt chế độ bám đuổi
            Raise_Z_Axis(Z_SAFE_HEIGHT)
            target_obj.status = STATUS_PICKED
            Robot_State = STATE_PLACE_MOTION
            
            # Di chuyển sang khay xếp kẹo
            Move_To_Place_Position()
            Turn_Off_Vacuum_Valve()
            Robot_State = STATE_IDLE

        # Nghỉ đúng chu kỳ 1ms
        Sleep_Microseconds(1000)
```

---

## 9. TỔNG KẾT BẢN CHẤT KỸ THUẬT ĐỂ PHẢN BIỆN TRƯỚC HỘI ĐỒNG

| Tiêu chí | Bản chất kỹ thuật trên Robot SCARA QKM |
| :--- | :--- |
| **Bản chất theo vết** | Không phải quay video liên tục, mà là **nội suy động học 1ms** dựa trên hiệu số xung Encoder $\Delta E$. |
| **Độ trễ hệ thống** | Được triệt tiêu nhờ **Hardware Position Latch** (chốt xung $< 1\,\mu\text{s}$ tại lúc phát hiện vật thể). |
| **Xử lý trượt phôi** | Sử dụng băng tải nhám thực phẩm có độ ma sát cao, gia tốc băng tải giữ trong giới hạn $a_{conv} \le 0.5\,\text{m/s}^2$. |
| **Sai số gắp động** | Dưới $\pm 0.5\,\text{mm}$ ở dải tốc độ băng tải $100 - 300\,\text{mm/s}$. |
| **Xử lý biến dạng kẹo** | Bắt mẫu **Pattern Matching tại phần chóp đuôi kẹo sâu** và **Contour toàn thân kẹo bạch tuộc** để giữ gốc tham chiếu tọa độ không bị trôi. |
