# code_neuromeka_fixed

Phiên bản đã sửa lỗi Jog và UI Freeze cho giao diện điều khiển hai robot Neuromeka Indy7.

## Chạy ứng dụng

```bash
python -m pip install -r requirements.txt
python main.py
```

Nếu hệ thống đang dùng bộ IndySDK/PlatformSDK được Neuromeka cấp riêng, hãy
giữ đúng môi trường và phiên bản SDK tương thích controller thay vì tự ý nâng
phiên bản trên máy vận hành.

## Chạy kiểm thử logic

```bash
python -m unittest discover -s tests -v
```

Xem phân tích chi tiết trong `AUDIT_REPORT.md` và quy trình vận hành trong `Huong_dan_Giao_dien_GUI.md`.
