# CẨM NANG VẬN HÀNH GIAO DIỆN ĐIỀU KHIỂN & ĐỒNG BỘ 2 ROBOT INDY7
*(Tài liệu hướng dẫn chi tiết dành cho người vận hành hệ thống)*

Chào mừng bạn đến với hệ thống giao diện điều khiển tích hợp hai robot Neuromeka Indy7. Tài liệu này giải thích chi tiết ý nghĩa vật lý, cách thức hoạt động của từng thành phần trên màn hình giao diện đồ họa (GUI) để bạn làm chủ hoàn toàn quy trình vận hành.

---

## I. Ý Nghĩa Vật Lý Của Thanh Tốc Độ (Đơn Vị mm/s)

Trên màn hình của mỗi Robot, bạn sẽ thấy một thanh trượt **Tốc độ (mm/s)** có dải giá trị từ **50 mm/s đến 900 mm/s** (độ chia nhỏ chi tiết từng bước **10 mm/s**).

### 1. Bản chất vật lý & Cách ánh xạ:
Vì tủ điều khiển Neuromeka nguyên bản nhận cấp độ tốc độ từ 1 đến 9 (tương ứng từ 10% đến 90% giới hạn phần cứng), phần mềm tự động ánh xạ tuyến tính mượt mà dải tốc độ `mm/s` này sang 9 cấp độ phần cứng.
* **Tốc độ 50 - 100 mm/s:** Ánh xạ xuống mức 1 (~ 10% tốc độ tối đa). Thích hợp cho việc dạy điểm bằng tay, chạy nhích thử điểm mới (Dry run) để đảm bảo an toàn, tránh va chạm.
* **Tốc độ 200 mm/s đến 500 mm/s:** Ánh xạ xuống mức 2 đến mức 5 (~ 20% - 50%). Thích hợp cho các chu kỳ nhúng bánh phở sôi hoặc di chuyển múc nước lèo để hạn chế tối đa quán tính rung lắc, làm sóng sánh bát nước lèo.
* **Tốc độ 600 mm/s đến 800 mm/s:** Ánh xạ xuống mức 6 đến mức 8 (~ 60% - 80%). Dùng cho việc di chuyển robot ở những vùng thoáng khí để rút ngắn chu kỳ làm việc.
* **Tốc độ 900 mm/s:** Ánh xạ xuống mức 9 (~ 90% - 100% tốc độ tối đa của hệ thống). Robot di chuyển với vận tốc nhanh nhất.

### 2. Nút "Áp Dụng Hết" (Sync Speed):
Nằm ngay cạnh thanh trượt tốc độ chung, nút **Áp Dụng Hết** có tính năng đồng bộ hóa tốc độ nhanh:
* Khi bạn kéo thanh trượt tốc độ chung đến mức mong muốn (ví dụ `350 mm/s`) và nhấn nút **Áp Dụng Hết**, tốc độ của **tất cả** các điểm trong danh sách sẽ lập tức được thay thế và đồng bộ về mức `350 mm/s`. 
* Điều này giúp bạn thiết lập tốc độ hàng loạt cực kỳ nhanh mà không cần phải đi sửa từng điểm một. Nếu không nhấn nút này, bạn vẫn có thể chỉnh tốc độ riêng biệt cho từng điểm bình thường.

### 3. Tốc độ này áp dụng cho những chuyển động nào?
1. Chuyển động **Jog khớp** (Jog Joint) hoặc **Jog tọa độ** (Jog Task) khi bạn nhấn giữ nút `JOG -` hoặc `JOG +`.
2. Tốc độ mặc định của hệ thống khi chạy chu trình.
3. **Quy tắc chạy Fillet:** Khi bạn bật chế độ **Chạy Fillet** (chạy liên tục không dừng giữa các điểm), do tính chất thuật toán gom điểm liên tục của tủ điều khiển robot, chu trình Fillet sẽ sử dụng **tốc độ được cài đặt cho điểm đầu tiên (P1)** của chu trình đó.

---

## II. Hướng Dẫn Vận Hành Tab 1 & Tab 2 (Điều Khiển & Dạy Điểm Độc Lập)

Tab 1 và Tab 2 là hai vùng làm việc riêng biệt của **Robot 1 (Nấu & Nhúng Phở)** và **Robot 2 (Nước Lèo & Giao Hàng)**. Hai tab này đóng vai trò **kiểm tra vùng hoạt động** và **dạy (lưu) điểm**.

### 1. Khu vực Kết Nối & Trạng Thái Hệ Thống:
* **IP Robot:** Địa chỉ mạng của từng robot (mặc định R1 là `192.168.0.10` và R2 là `192.168.0.11`). Bấm `Connect` để khởi động kết nối và kết xuất trạng thái.
* **Các nhãn đèn LED giám sát (Badge):**
  * `READY` (Xanh/Xám): Báo hiệu Robot đã sẵn sàng nhận lệnh chuyển động hay chưa.
  * `EMG` (Đỏ/Xanh): Đèn báo trạng thái dừng khẩn cấp (Emergency Stop).
  * `COLLISION` (Đỏ/Xanh): Đèn báo nếu robot va chạm vật cản, cảm biến lực phản hồi phát hiện quá tải.
  * `ERROR` (Đỏ/Xanh): Robot gặp lỗi động cơ hoặc phần mềm bên trong.
* **Tọa độ khớp (J1 - J6) & Thanh Cảnh báo Giới hạn:** Hiển thị góc quay thực tế của 6 khớp. Thanh trượt chuyển màu đỏ/cam cảnh báo trực quan khi khớp của robot di chuyển quá gần giới hạn vật lý tối đa.
* **Tọa độ đề-các (X, Y, Z, Rx, Ry, Rz):** Hiển thị vị trí thực tế của đầu kẹp Robot (mm) và góc xoay của dụng cụ kẹp.
* **🎯 Hiệu Chuẩn TCP (4 Điểm):** Dò tìm chính xác tâm điểm làm việc của dụng cụ kẹp/hút (Tool Center Point) bằng 4 tư thế nghiêng khác nhau.
* **📐 Dựng Hệ Trục Ref Frame (3 Điểm):** Căn chỉnh lại hệ tọa độ tham chiếu (User Frame / Work Object) theo mặt bàn thực tế bằng 3 điểm (Gốc O, Hướng +X, Mặt XY), khắc phục triệt để hiện tượng Jog Task bị xéo/lệch so với mép bàn.
* **💾 Lưu & 📂 Tải File Cấu Hình Reference Frame (.json):** Cho phép lưu lại toàn bộ 3 điểm và kết quả ma trận xoay thành tệp `.json` (Ví dụ `RefFrame_Robot1.json`). Khi đổi ca làm việc hoặc thiết lập lại máy, bạn chỉ cần bấm **Tải Từ Tệp (.json)** và nạp ngay xuống Robot Controller mà không cần phải căn chỉnh hay dạy lại 3 điểm!
* **🔄 Reset về Gốc Base:** Cho phép hoàn tác nhanh Reference Frame về gốc mặc định của chân đế Robot [0, 0, 0, 0, 0, 0].

### 2. Khu vực Điều Khiển Thủ Công:
* **SERVO ON/OFF:** Bật/Tắt điện vào các cuộn dây động cơ khớp. (Phải bật ON thì robot mới khóa lực và di chuyển được).
* **BẬT CHẾ ĐỘ CẦM TAY (Direct Teach):** Khi bật nút này, robot sẽ thả lỏng hoàn toàn các phanh giữ. Bạn có thể dùng tay cầm trực tiếp vào tay robot và kéo đến các góc mong muốn (vị trí lấy bánh phở, vị trí nồi nước sôi...) cực kỳ nhẹ nhàng.
* **TẮT (KHÓA LẠI):** Khóa phanh của robot lại sau khi đã kéo robot đến điểm mong muốn. Bạn phải bấm nút này thì robot mới sẵn sàng nhận lệnh tự động.
* **Nút JOG + / JOG - (Nhấn giữ):** Di chuyển nhích nhẹ từng khớp hoặc tịnh tiến tịnh lùi đầu kẹp theo tọa độ không gian để căn chỉnh điểm chuẩn xác từng milimet.

### 3. Khu vực Dạy Điểm & Chạy Độc Lập (Chu trình Robot):
* **Lưu Điểm (Save Point):** Lấy tọa độ hiện tại của robot và lưu vào danh sách điểm (`P1`, `P2`, `P3`...). Trước khi lưu, bạn có thể:
  * Chọn kiểu chuyển động (`MoveJ` hoặc `MoveL`).
  * **Cấu hình tốc độ chạy điểm riêng biệt (mm/s):** Kéo thanh trượt **Tốc độ điểm (mm/s)** (từ 50 đến 900 mm/s, độ chia nhỏ chi tiết 10 mm/s) để cài đặt tốc độ mong muốn cho điểm này. Tốc độ này sẽ được đính kèm trực tiếp vào điểm và tự động kích hoạt khi robot chạy đến điểm đó (cả khi chạy đơn lẻ hay chạy đồng bộ ở Tab 3).
* **Sửa Điểm (Edit Point):** Chọn một điểm bất kỳ trong danh sách, di chuyển robot đến vị trí mới, điều chỉnh lại tốc độ trên thanh trượt và bấm nút này để ghi đè tọa độ & tốc độ mới lên điểm đã chọn.
* **Xóa Điểm (Delete Selected Point):** Chọn 1 điểm bị dạy lỗi và bấm nút này để xóa đi. Hệ thống sẽ tự động dồn danh sách và đánh lại số thứ tự từ trên xuống dưới (Ví dụ xóa P2 thì P3 cũ sẽ tự động trở thành P2 mới) để tránh nhầm lẫn.
* **Đi Tới Điểm (Move to Point):** **(Tính năng mới thêm)** Khi bạn bấm chuột chọn một điểm bất kỳ trong danh sách điểm, rồi nhấn nút màu tím **Đi Tới Điểm**, robot sẽ tự động di chuyển trực tiếp đến đúng tọa độ của điểm đó bằng kiểu chuyển động và tốc độ đã lưu. Tính năng này vô cùng hữu ích để kiểm tra lại (verify) điểm có chuẩn xác hay không trước khi chạy tự động.
* **Xóa Hết (Clear All):** Xóa toàn bộ danh sách điểm của robot đó để dạy lại từ đầu.
* **Chạy Chu Trình / Chạy Fillet:** Chạy thử riêng robot đó đi qua toàn bộ các điểm từ `P1` đến điểm cuối để kiểm tra xem quỹ đạo di chuyển có bị va quẹt hoặc vướng dây nhợ gì hay không.

---

## III. Hướng Dẫn Vận Hành Tab 3 (Lập Trình Chu Trình Robot - Programming Studio)

Tab 3 là **"Trung tâm lập trình tự động hóa cao cấp"** cho phép bạn xây dựng các quy trình làm việc phức tạp của Robot Indy7 bằng 2 chế độ linh hoạt: **🧩 Khối Lệnh Trực Quan (Visual Block)** hoặc **🐍 Mã Nguồn Python (.py Engine)**.

---

### 1. Chế độ 1: 🧩 Lập Trình Khối Lệnh Trực Quan (Visual Block Program)

Cho phép lập trình kéo thả/chọn khối lệnh phân cấp cây (Treeview) trực quan mà không cần biết viết code:

```
+------------------------------------------------------------------------------------------------+
|  [ ➕ Thêm Lệnh ] [ ✏ Sửa Lệnh ] [ ❌ Xóa ] [ ▲ Lên ] [ ▼ Xuống ]  [ 💾 Lưu .json ] [ 📂 Tải .json ] [ 🚀 Xuất Python ] |
+------------------------------------------------------------------------------------------------+
|  ▼ 🔁 VÒNG LẶP (LOOP): 5 LẦN (Biến: i)                           | [ BẢNG ĐIỀU KHIỂN THỰC THI ] |
|      ├── 🚀 MoveJ(P1) - Tốc độ: 300 mm/s                         |  [ ▶ CHẠY CHƯƠNG TRÌNH ]     |
|      ├── ⚡ SET DO[0] = ON (Kẹp phôi)                            |  [ ⏸ Tạm Dừng ] [ ■ Dừng Lại]|
|      ├── ⏱️ TẠM DỪNG: 0.50 giây                                  |                              |
|      └── ▼ 🔀 ĐIỀU KIỆN IF: [di(0) == 1]                          | [ GIÁM SÁT BIẾN SỐ (REALTIME)]|
|          ├── ✅ NHÁNH ĐÚNG (THEN):                               |  i = 3                       |
|          │   └── 🚀 MoveL(P2) - Tốc độ: 200 mm/s                 |  counter = 12                |
|          └── ❌ NHÁNH SAI (ELSE):                                |  flag = True                 |
|              └── 🚀 MoveL(P3) - Tốc độ: 200 mm/s (Nhả phôi lỗi)  |                              |
+------------------------------------------------------------------------------------------------+
```

* **Các loại khối lệnh hỗ trợ:**
  * **Chuyển động (Motion):** `MoveJ(Point)` (Chuyển động khớp tới P1, P2...), `MoveL(Point)` (Chuyển động thẳng TCP), tùy chỉnh tốc độ mm/s riêng cho từng lệnh.
  * **Vòng lặp (Loops):** `LoopCount` (Lặp lại $N$ lần hoặc vô tận, tự động tăng biến đếm `i`), `While` (Lặp theo biểu thức điều kiện).
  * **Rẽ nhánh (Conditionals):** `IfCondition` (Kiểm tra tín hiệu cảm biến `di(0) == 1`, giá trị biến `counter < 10`... chia 2 nhánh THEN và ELSE rõ ràng).
  * **Ngõ vào/ra số (Digital I/O):** `SetDO` (Bật/Tắt van khí, giác hút, kẹp gripper), `WaitDI` (Chờ tín hiệu cảm biến kèm cài đặt Timeout).
  * **Biến số & Thời gian:** `SetVar` (Tính toán gán biến số `counter = counter + 1`), `WaitTime` (Dừng nghỉ), `Log` (Ghi thông báo).
  * **Điều khiển luồng:** `Break` (Thoát vòng lặp), `Continue` (Bỏ qua bước lặp), `StopProgram` (Dừng chương trình an toàn).
* **Tính năng:**
  * **Con trỏ thực thi (Step Highlighter):** Tự động highlight màu xanh dòng lệnh đang chạy thực tế theo thời gian thực.
  * **Lưu & Tải công thức (.json):** Lưu toàn bộ cây lệnh thành tệp `.json` để sử dụng lại bất cứ lúc nào.
  * **🚀 Xuất sang Python:** Chuyển đổi toàn bộ cây lệnh thành mã nguồn Python `.py` chuẩn chỉ bằng 1 cú click!

---

### 2. Chế độ 2: 🐍 Trình Soạn Thảo & Nạp Script Python (.py Studio)

Cho phép **nạp trực tiếp file mã nguồn Python `.py` từ ổ cứng** hoặc soạn thảo mã Python tùy biến với đầy đủ thư viện API Robot:

* **Thanh công cụ:**
  * **`📂 NẠP FILE PYTHON (.py)`**: Mở bất kỳ file script Python `.py` có sẵn trên máy tính để nạp vào hệ thống.
  * **`💾 LƯU FILE SCRIPT (.py)`**: Lưu mã nguồn trong trình soạn thảo ra file `.py`.
  * **`📜 CHỌN TEMPLATE MẪU`**: Cung cấp sẵn các mẫu chuẩn công nghiệp:
    1. *Chu trình Lặp Gắp Thả & Kiểm tra Cảm biến DI*.
    2. *Chu trình Xếp Pallet Ma Trận (2 Hàng x 3 Cột) tính toán tọa độ Offset*.
    3. *Chu trình Chờ Cảm Biến Băng Tải kích hoạt (Industrial Sensor Trigger)*.
  * **`▶ CHẠY SCRIPT PYTHON` / `■ DỪNG SCRIPT`**: Khởi chạy script trên luồng bảo vệ độc lập, ngắt an toàn tức thì khi bấm dừng.
* **Bộ Thư Viện API Robot Tích Hợp Sẵn trong Script Python (Hỗ trợ Bo góc Zone chuẩn ABB):**
  ```python
  robot.move_j("P1", 400.0, z10)            # Di chuyển khớp lướt qua P1 với bo góc 10mm
  robot.move_l("P2", 400.0, z20)            # Di chuyển thẳng lướt qua P2 với bo góc 20mm
  robot.move_l("P3", 400.0, fine)           # Dừng chính xác tại P3 (fine = 0mm)
  robot.set_do(pin=0, state=True)           # Bật ngõ ra DO 0 (Kẹp)
  val = robot.get_di(pin=0)                 # Đọc ngõ vào DI 0 (trả về 0 hoặc 1)
  robot.wait(0.5)                           # Tạm dừng nghỉ 0.5 giây
  robot.wait_di(pin=0, state=1, timeout=30) # Chờ cảm biến DI 0 kích hoạt
  robot.set_speed(250)                      # Đổi tốc độ vận hành (mm/s)
  robot.go_home()                           # Đưa robot về vị trí Home an toàn
  robot.log("Thông báo tiến trình...")       # Ghi log ra màn hình Console & HMI
  robot.is_stopped()                        # Kiểm tra người dùng có bấm dừng hay không
  points["P1"]                              # Truy cập dữ liệu tọa độ các điểm đã dạy
  ```
  *(Các hằng số Zone hỗ trợ: `fine` (0mm), `z0` (0.3mm), `z1` (1mm), `z5` (5mm), `z10` (10mm), `z15`, `z20`, `z30`, `z50`, `z100`, `z200`)*
* **Cửa sổ Terminal Output Console:** Hiển thị trực tiếp mọi thông báo `log()`, `print()`, thời gian chu trình và thông báo lỗi chi tiết theo thời gian thực.

---

## IV. Hướng Dẫn Cân Tải & Điều Khiển Bù Lực Tool (Payload & Force Compensation)

Tính năng **⚖️ Cân & Bù Lực Tool** được tích hợp sẵn ở Tab 1 & Tab 2 của từng Robot để xử lý triệt để hiện tượng **trục 4 (J4) hoặc cổ tay robot tự động xoay/trôi khi bật chế độ cầm tay (Direct Teaching)**.

### 1. Nguyên nhân & Cách khắc phục hiện tượng Trục 4 tự xoay:
* Khi bật **BẬT CHẾ ĐỘ CẦM TAY**, robot nhả phanh và dùng thuật toán **Bù Trọng Lực (Gravity Compensation)**. Nếu khối lượng Tool hoặc Tâm trọng lực (CoG $X, Y, Z$) chưa được khai báo chính xác, bộ điều khiển sẽ hiểu nhầm mô-men trọng lực là lực đẩy của người dùng, dẫn đến trục 4 tự xoay để triệt tiêu lực ảo.
* Ngoài ra, việc trôi điểm Zero cảm biến (Sensor Drift) cũng làm phát sinh nhiễu mô-men ở khớp 4.

### 2. Cách sử dụng cửa sổ "⚖️ Cân & Điều Khiển Bù Lực Tool":
1. Bấm nút màu tím **`⚖️ Cân & Bù Lực Tool`** ở ô thông số tọa độ.
2. **Cân Tải & CoG Tự Động:** Bấm nút **`⚡ Cân & Đo CoG Tự Động`** để robot tự tính toán khối lượng thực tế (kg) và tọa độ tâm trọng lực CoG ($X, Y, Z$ mm) từ cảm biến.
3. **Cài đặt Mức Bù Ma Sát Khớp:** Điều chỉnh mức bù cho 6 khớp (từ level 1 đến 5). Khuyên dùng **J4 = 5** để triệt tiêu ma sát và giúp robot hoàn toàn đứng yên khi thả tay.
4. **Triệt Trôi Khớp 4 (Zero Sensor Offset):** Khi robot dừng ở vị trí thả lỏng tĩnh, bấm nút **`🎯 Zero Cảm Biến Lực & Mô-men Offset`** để xóa sạch giá trị trôi của khớp 4.
5. Bấm **`💾 Ghi & Áp Dụng Cấu Hình Bù Lực Down Robot`** để cập nhật thông số xuống bộ điều khiển.

---

## V. Điều kiện và cách kiểm tra Jog

Trước khi Jog, cần bảo đảm:

1. Robot đã `CONNECTED`.
2. `READY: YES`, Servo đã bật và chế độ Cầm tay đã tắt.
3. `EMG: NORMAL`, `COLLISION: NO`, `ERROR: NO`.
4. Thử ở tốc độ thấp và vùng làm việc không có người/vật cản.

### Jog liên tục (Hold)

- Nhấn và giữ `JOG -` hoặc `JOG +` để chạy.
- Nhả chuột hoặc kéo con trỏ ra khỏi nút sẽ phát lệnh dừng.
- Phần mềm chỉ gửi vi bước tiếp theo sau khi controller không còn `busy`; không gửi dồn lệnh vào buffer.

### Jog bước (Step)

- Nhập bước theo `độ` đối với khớp và các trục xoay `Rx/Ry/Rz`.
- Nhập bước theo `mm` đối với `X/Y/Z`. Phần mềm tự đổi mm sang mét trước khi gọi IndyDCP2.
- Mỗi lần bấm chỉ phát đúng một lệnh; sự kiện nhả chuột không phát `stop_motion` để tránh tự hủy lệnh Step.

### Nếu vẫn không Jog được

Kiểm tra thông báo trên giao diện và log terminal theo thứ tự:

1. Controller có báo `READY: NO`, `EMG`, `Collision` hoặc lỗi giới hạn khớp không.
2. Phiên bản Python Neuromeka SDK có đúng với controller (DCP2/DCP3) không.
3. IP, kết nối LAN và chế độ vận hành trên teaching pendant.
4. Thử `Step` với J1 ở bước 0,5–1° trước, sau đó mới thử `Task X/Y/Z` ở bước 1–3 mm.
