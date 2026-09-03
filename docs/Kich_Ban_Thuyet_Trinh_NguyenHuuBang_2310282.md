# KỊCH BẢN THUYẾT TRÌNH BÁO CÁO THỰC TẬP NGOÀI TRƯỜNG (29 SLIDE)

> **CƠ SỞ ĐÀO TẠO:** TRƯỜNG ĐẠI HỌC BÁCH KHOA - ĐHQG TP.HCM  
> **KHOA / BỘ MÔN:** KHOA ĐIỆN - ĐIỆN TỬ — BỘ MÔN TỰ ĐỘNG HÓA  
> **SINH VIÊN THỰC HIỆN:** Nguyễn Hữu Bằng — **MSSV:** 2310282  
> **CHUYÊN NGÀNH:** Kỹ thuật Điều khiển và Tự động hóa — Khóa 2023 (Học kỳ 252)  
> **GIẢNG VIÊN HƯỚNG DẪN:** TS. Nguyễn Hoàng Giáp  
> **CÁN BỘ HƯỚNG DẪN DOANH NGHIỆP:** KS. Nguyễn Duy Kha  
> **ĐƠN VỊ THỰC TẬP:** Công ty Cổ phần Giải pháp Tự động hóa ETEK  

---

### **SLIDE 1: TRANG BÌA BÁO CÁO**
> *"Kính thưa quý Thầy Cô trong Hội đồng chấm Báo cáo Thực tập tốt nghiệp Khoa Điện - Điện tử, Trường Đại học Bách Khoa - ĐHQG TP.HCM. Em tên là Nguyễn Hữu Bằng, sinh viên lớp Kỹ thuật Điều khiển và Tự động hóa Khóa 2023, MSSV 2310282. Dưới sự hướng dẫn của TS. Nguyễn Hoàng Giáp cùng sự bảo trợ chuyên môn từ Kỹ sư Nguyễn Duy Kha tại Công ty Cổ phần Giải pháp Tự động hóa ETEK, hôm nay em xin phép được báo cáo kết quả đợt Thực tập Ngoài trường Học kỳ 252. Em xin phép được bắt đầu phần trình bày của mình."*

---

### **SLIDE 2: NỘI DUNG BÁO CÁO TIẾN ĐỘ THỰC TẬP THEO TUẦN (TUẦN 1 – TUẦN 8)**
> *"Kính thưa Hội đồng, toàn bộ quá trình thực tập 8 tuần của em được chia thành các giai đoạn logic và bám sát dự án công nghiệp thực tế: Từ Tuần 1 đến Tuần 3, em thực hiện khảo sát dây chuyền tự động hóa tốc độ cao Unilever, lập trình thị giác máy AI Cognex và robot công nghiệp ABB. Đến Tuần 4, em tham gia triển khai giải pháp Intralogistics tại Triển lãm Quốc tế VILOG 2026. Trọng tâm từ Tuần 5 đến Tuần 8, em trực tiếp thiết kế bản vẽ điện EPLAN Pro Panel, xử lý ảnh công nghiệp HIKROBOT VisionMaster và thi công, tích hợp chạy thử nghiệm hệ thống máy cấp kẹo Orion. Sau đây em xin đi vào chi tiết từng nội dung."*

---

### **SLIDE 3: CHƯƠNG 1: TỔNG QUAN DOANH NGHIỆP ETEK & VỊ TRÍ THỰC TẬP**
> *"Về đơn vị tiếp nhận, Công ty Cổ phần Giải pháp Tự động hóa ETEK là đơn vị tổng thầu uy tín hàng đầu tại Việt Nam trong lĩnh vực tích hợp hệ thống Robot, Machine Vision và giải pháp Nhà máy thông minh. Trong đợt thực tập này, em được phân công tại Phòng Kỹ thuật & Dự án, trực tiếp tham gia cùng các kỹ sư doanh nghiệp vào quy trình thiết kế phần cứng, lập trình phần mềm và tích hợp thực tế tại xưởng chế tạo."*

---

### **SLIDE 4: TUẦN 1: KHẢO SÁT HỆ THỐNG PUMP SORTER 140 (UNILEVER)**
> *"Trong Tuần 1, em được giao nhiệm vụ khảo sát hệ thống máy Pump Sorter 140 chế tạo cho khách hàng Unilever Việt Nam. Yêu cầu kỹ thuật của dây chuyền là tự động cấp nắp vòi pump và siết đóng nắp chai với năng suất rất cao, lên tới 140 sản phẩm/phút chạy liên tục 24/7. Tủ điện điều khiển trung tâm sử dụng PLC Mitsubishi dòng Q hiệu năng cao kết hợp mạng truyền thông công nghiệp để điều phối toàn bộ các trạm chấp hành."*

---

### **SLIDE 5: TUẦN 1: ROBOT DELTA ABB PICKMASTER & MOTION BUFFER SERVO**
> *"Để đáp ứng tốc độ 140 sản phẩm/phút, hệ thống bố trí cụm 3 Robot Delta ABB PickMaster chạy song song. Camera thị giác máy bên trên sẽ chụp định vị tọa độ và hướng quay của từng nắp vòi pump trên băng tải cấp liệu. Nhờ thuật toán Conveyor Tracking, 3 robot delta bám đuổi theo chuyển động liên tục của băng chuyền, phân chia vùng gắp mượt mà mà không làm dừng băng tải."*

---

### **SLIDE 6: TUẦN 1: CỤM MOTION BUFFER SERVO & CÔNG ĐOẠN CẤP NẮP**
> *"Tiếp theo, Robot Delta sẽ thả nắp vào cụm Motion Buffer dẫn động bằng Servo Mitsubishi đa trục. Cụm đệm này có nhiệm vụ đồng tốc hoàn toàn với miệng chai đang chạy bên dưới, đưa nắp vào đúng vị trí cổ chai một cách êm dịu, triệt tiêu hoàn toàn hiện tượng rung lắc hay lệch tâm cơ khí trước khi chuyển sang công đoạn siết nắp."*

---

### **SLIDE 7: TUẦN 1: VẬN HÀNH ROBOT ABB IRB6700 SIẾT NẮP CHAI CHUẨN LỰC**
> *"Tại công đoạn đóng siết cuối cùng, hệ thống ứng dụng Robot công nghiệp 6 bậc tự do ABB IRB6700 mang cụm động cơ Servo siết ren chuyên dụng. Bộ điều khiển giám sát chính xác lực siết momen xoắn và độ sâu ren, đảm bảo 100% nắp chai được đóng kín khít tuyệt đối theo đúng tiêu chuẩn xuất xưởng nghiêm ngặt của Unilever."*

---

### **SLIDE 8: TUẦN 2: HUẤN LUYỆN THỊ GIÁC MÁY AI COGNEX IN-SIGHT 2800**
> *"Sang Tuần 2, em thực hiện nghiên cứu và huấn luyện camera thông minh Cognex In-Sight 2800 tích hợp công nghệ AI Edge Learning trên phần mềm In-Sight Vision Suite. Em đã trực tiếp tinh chỉnh tiêu cự ống kính, cấu hình thời gian phơi sáng Exposure và thu thập tập dữ liệu mẫu để huấn luyện mô hình phân loại sản phẩm GOOD/NG ngay tại trạm kiểm tra."*

---

### **SLIDE 9: TUẦN 2: KẾT QUẢ PHÂN LOẠI GOOD NẮP CHAI ĐẠT CHUẨN**
> *"Đây là kết quả khi kiểm tra sản phẩm đạt chuẩn chất lượng (GOOD). Camera AI nhận diện chính xác vòi pump đã vào đúng ren, không bị xước, thẳng đứng và nắp chai nằm khít hoàn toàn với gờ cổ chai."*

---

### **SLIDE 10: TUẦN 2: PHÁT HIỆN LỖI NG (THIẾU NẮP & LỆCH VÒI)**
> *"Đối với các trường hợp sản phẩm lỗi (NG): Thuật toán phát hiện tức thời trường hợp chai bị thiếu nắp vòi pump hoặc nắp bị xoay lệch góc, chưa ăn khớp ren. Thời gian xử lý của mô hình AI chỉ mất dưới 80ms, hoàn toàn đáp ứng nhịp chuyền 140 sản phẩm/phút."*

---

### **SLIDE 11: TUẦN 2: PHÁT HIỆN LỖI NG (KÊNH REN & BUNG VÒI) & LIÊN ĐỘNG PLC**
> *"Bên cạnh đó, các lỗi phức tạp như kênh ren chéo (kenh_nap) và bung khớp vòi (bung_voi) cũng được phân loại chính xác. Khi phát hiện lỗi NG, camera lập tức xuất tín hiệu Digital I/O kích hoạt ngõ vào PLC để điều khiển xilanh khí nén gạt phế phẩm ra khỏi băng chuyền chính."*

---

### **SLIDE 12: TUẦN 3: LẬP TRÌNH MÔ PHỎNG ABB ROBOTSTUDIO**
> *"Bước sang Tuần 3, em thực hiện mô phỏng trạm làm việc của Robot trên phần mềm ABB RobotStudio. Em đã tiến hành dựng mô hình không gian 3D, định nghĩa hệ tọa độ tay gắp Tool Data, vùng làm việc WorkObject, lập trình ngôn ngữ RAPID và kiểm tra tránh va chạm trước khi nạp chương trình vào robot thật."*

---

### **SLIDE 13: TUẦN 3: VẬN HÀNH THỰC TẾ ROBOT ABB IRB1200 TẠI XƯỞNG**
> *"Sau khi mô phỏng đạt yêu cầu, em trực tiếp sử dụng tay cầm FlexPendant để dạy điểm (Teach Point) cho cánh tay Robot ABB IRB1200 thật tại xưởng. Em đã cấu hình ngõ ra Digital Output điều khiển van điện từ khí nén, vận hành chu trình robot gắp và đặt phôi mẫu in 3D với độ lặp lại vị trí chính xác tuyệt đối."*

---

### **SLIDE 14: TUẦN 4: TRIỂN KHAI TẠI TRIỂN LÃM QUỐC TẾ VILOG 2026 (SECC Q7)**
> *"Tại Tuần 4, em có cơ hội được tham gia cùng đội ngũ kỹ sư ETEK trực tiếp lắp đặt và vận hành demo giải pháp Intralogistics tại Triển lãm Quốc tế VILOG 2026 tổ chức tại Trung tâm Hội chợ SECC Quận 7. Hệ thống trình diễn giải pháp kho vận thông minh kết hợp băng tải con lăn và robot tự hành AGV/AMR phục vụ khách tham quan chuyên ngành."*

---

### **SLIDE 15: TUẦN 4: CAMERA COGNEX DATAMAN & BĂNG TẢI INTEROLL**
> *"Tại gian hàng, em trực tiếp cấu hình camera công nghiệp Cognex DataMan trên phần mềm DataMan Setup Tool để đọc tự động mã vạch 1D và mã QR Code 2D dán trên các thùng hàng chuyển động. Dữ liệu mã quét được truyền qua giao thức TCP/IP lên phần mềm máy tính, tự động phân luồng kiện hàng trên hệ thống con lăn thông minh Interoll RollerDrive và xuất tệp dữ liệu thời gian thực cho hệ thống quản lý kho WMS."*

---

### **SLIDE 16: TUẦN 5 – 6: THIẾT KẾ BẢN VẼ ĐIỆN EPLAN DỰ ÁN MÁY CẤP KẸO ORION**
> *"Từ Tuần 5 đến Tuần 8 là dự án trọng tâm mà em tham gia chế tạo trọn vẹn: Hệ thống máy phân loại và cấp kẹo tự động cho Tập đoàn Thực phẩm Orion. Tổng thể máy gồm: phễu rung cấp phôi, băng tải dẫn hướng, hệ thống camera thị giác máy và cánh tay Robot SCARA gắp kẹo. Em được giao nhiệm vụ chủ trì thiết kế bộ bản vẽ điện trên phần mềm EPLAN Pro Panel và bố trí layout tủ điện."*

---

### **SLIDE 17: TUẦN 5 – 6: EPLAN SINGLE LINE NGUỒN ĐỘNG LỰC 3 PHA 380VAC**
> *"Đây là sơ đồ nguyên lý phân phối nguồn Single Line 3 pha 380VAC. Nguồn tổng đi qua Aptomat khối MCCB, Contactor chính, rơ le bảo vệ thứ tự pha và rẽ nhánh qua các MCB bảo vệ cấp nguồn cho các bộ biến tần điều khiển động cơ băng tải."*

---

### **SLIDE 18: TUẦN 5 – 6: EPLAN SINGLE LINE NGUỒN ĐIỀU KHIỂN 220VAC & 24VDC**
> *"Tiếp theo là sơ đồ nguồn điều khiển: Sơ đồ phân phối nguồn 1 pha 220VAC cấp cho quạt hút tản nhiệt, đèn chiếu sáng tủ, ổ cắm và bộ nguồn xung tổ ong. Sơ đồ phân phối nguồn 24VDC ổn áp cấp cho bộ điều khiển PLC Mitsubishi FX5U, màn hình HMI, Switch mạng công nghiệp, Camera và đèn tháp cảnh báo."*

---

### **SLIDE 19: TUẦN 5 – 6: EPLAN MULTI LINE BẢO VỆ PHA & ĐẤU NỐI I/O PLC**
> *"Về mạch điều khiển chi tiết Multi Line: Hệ thống tích hợp Rơ le bảo vệ mất pha, đảo pha nhằm triệt để bảo vệ động cơ và robot khi có sự cố lưới điện. Bản vẽ thể hiện chi tiết các chân tín hiệu cảm biến quang, nút nhấn dừng khẩn E-Stop về các kênh đầu vào số (DI) của PLC và cầu đấu dây Terminal TM19."*

---

### **SLIDE 20: TUẦN 7: THỊ GIÁC MÁY HIK VISIONMASTER NHẬN DẠNG KẸO DẺO ORION**
> *"Bước sang Tuần 7, em giải quyết bài toán xử lý ảnh trên phần mềm HIKROBOT VisionMaster 4.4.30. Thách thức kỹ thuật lớn nhất ở đây là kẹo dẻo mềm có biên dạng bất định, dễ biến dạng gồm 2 chủng loại: kẹo hình sâu (uốn lượn bất đối xứng) và kẹo hình bạch tuộc. Mục tiêu là phải tính toán chính xác tâm gắp và góc xoay Rz để robot không làm nát kẹo."*

---

### **SLIDE 21: TUẦN 7: LƯU ĐỒ THUẬT TOÁN NHẬN DIỆN VISIONMASTER**
> *"Để xử lý, em đã thiết kế lưu đồ thuật toán trên phần mềm: Sau khi chụp ảnh từ camera, một đoạn Python Script sẽ kiểm tra mã sản phẩm từ PLC để phân nhánh điều khiển. Tùy loại kẹo mà thuật toán rẽ nhánh sang chuỗi khối Contour của kẹo sâu hoặc kẹo bạch tuộc, chuyển đổi tọa độ Pixel sang mm và đóng gói dữ liệu truyền qua cổng mạng Ethernet."*

---

### **SLIDE 22: TUẦN 7: NHẬN DIỆN ĐUÔI KẸO SÂU & VIỀN BẠCH TUỘC**
> *"Chi tiết thuật toán: Với kẹo hình sâu, thân kẹo bị cong ngẫu nhiên, nên em sử dụng thuật toán Pattern Matching bắt chính xác vùng đuôi đặc trưng để làm gốc tham chiếu tọa độ gắp ổn định. Với kẹo hình bạch tuộc, em sử dụng công cụ Contour trích xuất toàn bộ đường bao đối xứng để tính toán tâm hình học và góc xoay Rz."*

---

### **SLIDE 23: TUẦN 7: HIỆU CHUẨN CALIB & TRUYỀN TỌA ĐỘ TCP CLIENT**
> *"Để robot hiểu được vị trí gắp, em tiến hành Hiệu chuẩn Calib 9 điểm để chuyển đổi ma trận tọa độ Pixel ảnh sang tọa độ thế giới thực Milimet (mm). Dữ liệu tọa độ (X, Y, Rz) sau khi tính toán được đóng gói thành chuỗi ký tự chuẩn công nghiệp và truyền qua giao thức TCP/IP Socket Client gửi thẳng về bộ điều khiển Robot SCARA với độ trễ cực thấp."*

---

### **SLIDE 24: TUẦN 8: ĐẤU NỐI CƠ ĐIỆN TỦ ĐIỀU KHIỂN THEO BẢN VẼ EPLAN**
> *"Trong Tuần 8, em trực tiếp thi công đấu nối tủ điện theo đúng bản vẽ EPLAN đã thiết kế. Em đã lắp đặt thanh DIN rail, máng cáp lược, bấm đầu cosse bọc nhựa và đánh số dây (Ferrules) chuẩn xác theo từng trang bản vẽ; đồng thời thực hiện đo kiểm tra thông mạch và tiếp địa an toàn trước khi cấp nguồn."*

---

### **SLIDE 25: TUẦN 8: TÍCH HỢP NGOẠI VI: PHỄU RUNG, CAMERA HIK & ROBOT SCARA**
> *"Sau khi hoàn thiện tủ điện, em tiến hành tích hợp toàn bộ ngoại vi: Kết nối bộ điều khiển phễu rung biến tần để cấp kẹo trải đều ra băng chuyền. Lắp đặt giá treo camera HIKROBOT kết hợp bộ đèn chiếu sáng vòm (Dome Light) chống hiện tượng lóa bề mặt kẹo. Thiết lập tín hiệu đồng bộ Ready/Trigger giữa Camera, PLC và Robot SCARA."*

---

### **SLIDE 26: TUẦN 8: CHẠY THỬ NGHIỆM VẬN HÀNH THỰC TẾ & NGHIỆM THU DỰ ÁN**
> *"Hệ thống được đưa vào vận hành chạy thử nghiệm tự động liên tục. Kết quả kiểm tra thực tế cho thấy thuật toán nhận diện ảnh hoạt động vô cùng ổn định ngay cả khi các viên kẹo bị xoay góc hoặc dính nhẹ; tỷ lệ gắp chính xác đạt trên 98%, đáp ứng trọn vẹn toàn bộ yêu cầu kỹ thuật khắt khe của Tập đoàn Orion để bàn giao nghiệm thu."*

---

### **SLIDE 27: TUẦN 8: VIDEO VẬN HÀNH THỰC TẾ MÁY CẤP KẸO ORION**
> *"Kính mời quý Thầy Cô cùng theo dõi đoạn video ghi lại quá trình vận hành thực tế của máy cấp kẹo Orion tại xưởng ETEK: Kẹo từ phễu rung đi ra băng tải, Camera HIK chụp nhận diện, hệ thống tính toán tọa độ và góc xoay, Robot SCARA hạ đầu hút chân không gắp chính xác từng viên kẹo xếp vào vỉ theo đúng chu trình tự động hóa hoàn toàn."*

---

### **SLIDE 28: CHƯƠNG 3: TỔNG KẾT KẾT QUẢ & BÀI HỌC KINH NGHIỆM**
> *"Qua 8 tuần thực tập thực tế, em đã thu hoạch được 3 giá trị cốt lõi: Về Kỹ thuật chuyên môn: Làm chủ quy trình thiết kế bản vẽ điện chuẩn quốc tế trên EPLAN Pro Panel; lập trình mô phỏng robot ABB và ứng dụng thành thạo thị giác máy AI Cognex, HIKROBOT. Về Kỹ năng làm việc: Rèn luyện tác phong kỷ luật, kỹ năng làm việc nhóm, quản lý tiến độ và xử lý sự cố thực tế tại xưởng chế tạo. Về Định hướng tương lai: Đây là nền tảng thực tiễn vững chắc giúp em tự tin hoàn thành Đồ án Tốt nghiệp và định hướng trở thành Kỹ sư Tự động hóa chuyên nghiệp sau khi ra trường."*

---

### **SLIDE 29: LỜI CẢM ƠN**
> *"Để đạt được kết quả này, em xin bày tỏ lòng biết ơn sâu sắc đến quý Thầy Cô Khoa Điện - Điện tử, đặc biệt là Thầy TS. Nguyễn Hoàng Giáp cùng Ban Lãnh đạo và các anh chị Kỹ sư tại Công ty Cổ phần Giải pháp Tự động hóa ETEK đã tận tình hướng dẫn và tạo điều kiện tốt nhất cho em trong suốt thời gian qua. Em xin chân thành cảm ơn quý Thầy Cô trong Hội đồng đã chú ý lắng nghe. Em rất mong nhận được những nhận xét và câu hỏi phản biện từ quý Thầy Cô để hoàn thiện đề tài tốt hơn. Em xin trân trọng cảm ơn!"*

---
