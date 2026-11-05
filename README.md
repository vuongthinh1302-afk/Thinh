# CapCut Template Builder

Tạo template CapCut chuẩn từ một file JSON:

1. **Kiểm tra chuẩn**: khung hình, fps, thời lượng, số slot, chữ có tràn hay sát mép không, beat có khớp điểm cắt không.
2. **Xuất draft CapCut PC**: thư mục dự án có sẵn timeline (slot ảnh giữ chỗ, chữ, chuyển cảnh, nhạc, beat).
3. **Dựng video xem trước** (`preview.mp4`) bằng ffmpeg để duyệt nhịp và bố cục.

Chỉ cần Python 3.10+. Muốn có preview thì cài thêm ffmpeg.

## Cách dùng nhanh

```bash
# 1. Tạo file mô tả mẫu
python -m capcut_templates new templates/cua-toi.json --name "Template của tôi"

# 2. Sửa file JSON, rồi kiểm tra
python -m capcut_templates validate templates/cua-toi.json

# 3. Xuất draft + preview vào ./output
python -m capcut_templates build templates/cua-toi.json

#    Hoặc xuất thẳng vào thư mục draft của CapCut PC (Windows/macOS)
python -m capcut_templates build templates/cua-toi.json --install
```

Thư mục draft của CapCut PC (nếu không dùng `--install` thì chép thư mục xuất ra vào đây):

- Windows: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
- macOS: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft`

## Từ draft thành template trên CapCut

1. Mở CapCut PC, dự án mới sẽ có trong danh sách.
2. Xem `template_info.json` để biết slot nào thay được và chữ nào sửa được.
3. Thêm hiệu ứng, bộ lọc hoặc nhạc bản quyền của CapCut nếu muốn.
4. Đăng template bằng tính năng **Template / Publish as template** (cần tài khoản CapCut Template Creator). Khi đăng, đánh dấu các slot ảnh/video là "có thể thay thế".

## Định dạng file JSON

```jsonc
{
  "name": "Tên template",
  "description": "Mô tả ngắn",
  "tags": ["beat", "trend"],
  "aspect": "9:16",          // 9:16 | 16:9 | 1:1 | 4:5
  "fps": 30,                 // 24 | 25 | 30 | 50 | 60
  "background": "#000000",
  "slots": [                 // các ô ảnh/video người dùng thay vào
    {"duration": 1.5, "kind": "photo", "label": "Ảnh mở đầu",
     "transition": "fade",   // none | fade | slide_left | slide_up | zoom | flash
     "zoom": 1.1}            // 1.0-2.0, hiệu ứng zoom chậm
  ],
  "texts": [
    {"text": "Tiêu đề", "start": 0, "duration": 1.5, "size": 14,
     "color": "#FFFFFF", "y": -0.5,       // -1 trên cùng .. 1 dưới cùng
     "animation": "fade_in",              // none | fade_in | zoom_in | slide_up | typewriter
     "editable": true}
  ],
  "music": {"path": "nhac.mp3", "start": 0, "volume": 1.0,
            "beats": [0, 1.5, 2.5]}       // mốc beat (giây)
}
```

Mẹo: đặt `"slots_from_beats": true` để tự chia slot theo `music.beats`. Danh sách `slots` lúc đó chỉ là mẫu kiểu (lặp vòng). Xem `templates/beat-sync-6-anh.json`.

## Mẫu có sẵn

| File | Mô tả |
|---|---|
| `templates/beat-sync-6-anh.json` | 6 ảnh chuyển theo beat, 9:16 |
| `templates/travel-vlog.json` | Vlog du lịch 5 cảnh, 9:16 |
| `templates/quote-1-1.json` | Trích dẫn trên nền ảnh, 1:1 |

## Lưu ý

- CapCut không công bố định dạng draft và không có API tạo template. Draft ở đây dựa trên cấu trúc `draft_content.json` của CapCut PC bản cũ (chưa mã hoá). **CapCut PC bản mới có thể mã hoá draft và không mở được draft tạo từ bên ngoài**; khi đó dùng `preview.mp4`, `template_info.json` và ảnh giữ chỗ làm bản thiết kế để dựng lại trong CapCut.
- Tên chuyển cảnh/hiệu ứng được ghi theo tên trong CapCut nhưng không kèm file tài nguyên; CapCut có thể yêu cầu chọn lại hiệu ứng.

## Chạy test

```bash
python -m unittest discover -s tests
```
