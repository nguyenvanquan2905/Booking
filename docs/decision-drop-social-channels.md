# Quyết định — Bỏ kênh MXH, chỉ làm web đặt bàn

> **Trạng thái:** CHÍNH THỨC · **Ngày:** 2026-11-18 · **Người quyết định:** chủ dự án
> **Phạm vi ảnh hưởng:** backlog, system design, dữ liệu benchmark, phân công A/D/E

---

## 1. Quyết định

Dự án **chỉ làm web đặt bàn**. Toàn bộ kênh mạng xã hội — **Facebook Fanpage, Zalo OA,
Instagram DM** — **bị loại khỏi phạm vi MVP**.

Lý do: kênh MXH kéo theo chuỗi phụ thuộc nặng nhất của dự án (Camoufox chạy Gecko/Juggler/BiDi
không nối trực tiếp được với thư viện Chrome CDP, profile vault, IP dân cư cố định, ngủ đông
phiên chờ 15–30 phút) trong khi giá trị đo của nó trùng phần lớn với web Loại B.

## 2. Task bị loại khỏi phạm vi

| Task | Nội dung | Owner | Xử lý |
|---|---|---|---|
| **MVP-37** | Luồng đặt bàn qua MXH (Fanpage, Zalo OA, Instagram DM) | D | **Hủy** — không làm |
| **MVP-74** | Profile Vault & cấp phát profile MXH | A | **Hủy** — không làm |
| **MVP-75** | Cấp phát proxy & gán IP cố định | A | **Hủy** — không làm |

Ba task này **không còn trong đường găng**. Ai đã bắt đầu thì dừng lại.

## 3. Task giữ nguyên nhưng đổi phạm vi

| Task | Thay đổi |
|---|---|
| **MVP-23** Camoufox | Vẫn giữ làm engine thứ hai cho **ca khó / anti-bot trên web**, không còn phục vụ MXH |
| **MVP-24** Session persistence + file lock | Vẫn giữ — profile web vẫn cần lưu phiên và khoá |
| **MVP-25** Tích hợp proxy dân cư | Vẫn giữ — web chống anti-bot vẫn cần proxy |
| **MVP-12** Checkpointer | Vẫn giữ — ngủ đông chờ **OTP** (1–5 phút), không còn nhánh chờ tin nhắn MXH |
| **MVP-16** Durable wrapper | Vẫn giữ — timeout OTP 15 phút; bỏ nhánh timeout MXH nhiều giờ/ngày |
| **MVP-18** Bộ 5 bài test E2E | Bài (2) Race Condition Context Lock đổi từ "5 request vào 1 `profile_id` MXH" sang **profile web** |

## 4. Dữ liệu benchmark đã cập nhật (owner E — xong)

| Hạng mục | Trước | Sau |
|---|---|---|
| Site registry | 12 site: 6 chuỗi + 3 độc lập + 3 MXH | **12 site web: 6 chuỗi + 6 độc lập** |
| Quỹ cold (Loại B) | 3 site MXH | **3 site web Loại B**: Saigon Princess, Bình Quới, White Place |
| Ground truth | 2 bộ tiêu chí (web + chat) | **1 bộ tiêu chí web** cho cả 12 site |
| Kịch bản | 2 web + 1 Facebook | **3 kịch bản web form** |
| Tài khoản test | 9 email + 3 SMS (MXH) | **9 email + 3 SMS** (3 chuỗi dùng SMS) |
| Dataset freeze | v1 chứa MXH | **v1 tạo lại, web-only** — `sha256:bd848be3…f7e4f` |

Code đã sửa: `telemetry/sites.py`, `ground_truth.py`, `accounts.py`, `scenarios.py`.
Bỏ `SiteCategory.SOCIAL`, `SuccessSignal.CHAT_REPLY`, `Channel.FACEBOOK/ZALO/INSTAGRAM`.
**303 test pass, ruff sạch.**

## 5. Việc mỗi người cần làm

- **A:** bỏ MVP-74, MVP-75 khỏi kế hoạch. MVP-23/24/25 giữ nguyên nhưng chỉ phục vụ web.
- **D:** bỏ MVP-37. MVP-38 (Success/Failure Detector) chỉ cần nhận diện web.
- **C:** MVP-12/16/18 bỏ nhánh chờ tin nhắn MXH; chỉ còn chờ OTP.
- **E:** đã xong phần dữ liệu; tiếp tục các task benchmark còn lại.
- **F:** API/FE không cần trường kênh MXH.

## 6. Không thay đổi

- Kiến trúc modular monolith, SQLite WAL, bảng prefix module — giữ nguyên.
- Trần tài nguyên: 3–5 sandbox, 2–3 trình duyệt — giữ nguyên.
- 4 cấp điều khiển browser, Guardrails, Live View — giữ nguyên.
