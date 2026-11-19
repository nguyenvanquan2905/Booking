> Backlog triển khai · Jira-style

# Danh sách task xây dựng MVP Browser Agent Đặt bàn

> 🚫 **QUYẾT ĐỊNH CHÍNH THỨC 2026-11-18 — BỎ KÊNH MXH, CHỈ LÀM WEB ĐẶT BÀN**
>
> **MVP-37, MVP-74, MVP-75 bị hủy** (Facebook Fanpage, Zalo OA, Instagram DM ra khỏi phạm vi).
> MVP-23/24/25 vẫn giữ nhưng chỉ phục vụ web. MVP-12/16/18 bỏ nhánh chờ tin nhắn MXH.
> Chi tiết đầy đủ: [`docs/decision-drop-social-channels.md`](docs/decision-drop-social-channels.md).
> Các mô tả MXH bên dưới được giữ làm **lịch sử**, không còn hiệu lực thi hành.

Backlog gom theo layer kiến trúc và nhóm việc, viết theo chuẩn Jira (Title · Description · Acceptance Criteria · Owner · Estimate · Dependency). Dựng từ bốn tài liệu tầng, tài liệu quyết định MVP và tech stack v1.2. v1.1 bổ sung bốn lớp xuyên tầng còn thiếu. v1.2 gọn lại cho MVP nhanh: bỏ Redis và các hạ tầng nặng, trần 3–5 sandbox và 2–3 trình duyệt. v1.3 gom task theo năm người A–E. v1.4 bổ sung hai task nối agent với browser control: hợp đồng control-plane và bắt tay HITL. v1.5 thêm 9 task bịt các hổng chặn hoạt động: đóng gói một lệnh, Guardrails Lớp 2, Live View UI khách, luồng đặt bàn MXH, Success/Failure Detector, cgroups, seccomp, Browser Allocator và idempotency/hủy bàn. v1.6 rà lại 9 task đó với bốn tài liệu tầng: chỉnh lại phụ thuộc, bổ sung Instagram DM vào luồng MXH và ghi rõ các hổng còn lại. v1.7 rà đề xuất của thành viên hạ tầng browser: bổ sung Xvfb, seed/timezone profile, giới hạn phiên/IP và WebRTC vào task hiện có; giữ nguyên số hiệu; các đề xuất trùng phạm vi D/E không đưa vào. v1.8 rà đề xuất của thành viên phụ trách agent: thêm 4 task (MVP-16 durable wrapper, MVP-17 Guardrails Lớp 3, MVP-18 bộ 5 bài test E2E, MVP-29 token rotation & health_score); bổ sung BAML, Anti-Loop, PostgresSaver, ContextLease, Tiered Hydration, mã trạng thái vào task hiện có; không đổi file lock sang PostgreSQL Lease Lock và không thêm Inngest/Temporal. v1.9 bỏ Lightpanda theo quyết định của chủ dự án: còn 2 engine (Chromium/Patchright và Camoufox), A giảm còn 14,0 pd, số hiệu MVP-21 để trống. v2.0 đồng bộ database với system design v2.1: PostgreSQL → SQLite (`AsyncSqliteSaver`, claim pattern `BEGIN IMMEDIATE`, Alembic SQLite, `VACUUM INTO`); thêm EPIC-11 API layer (4 task, người F mới) và EPIC-12 FE web app (4 task, người F mới); sửa lỗi đếm task EPIC-1 và bảng ưu tiên. **v2.1 bỏ kênh MXH theo quyết định của chủ dự án: hủy MVP-37, MVP-74, MVP-75; chỉ còn web đặt bàn.**

Team: 6 người (A–F) · Thời lượng: 15 ngày làm việc · 13 epic · 74 task · 4 cổng kiểm tra · Người lập: Vũ Ngọc Hùng

## 00 — Quy ước & lưu ý

*Đọc phần này trước khi đưa backlog vào Jira.*

| Trường | Ý nghĩa |
|---|---|
| **Type** | Epic nhóm lớn theo layer · Story hạng mục có giá trị nghiệp vụ, cần demo được · Task việc kỹ thuật nội bộ |
| **Owner** | A Hạ tầng browser (quản lý & cấp phát browser) · B Hạ tầng sandbox (quản lý & cấp phát sandbox/VM) · C Agent (toàn bộ hệ thống agent) · D Browser control (toàn bộ phần điều khiển browser) · E các task còn lại (benchmark, dữ liệu, monitor, harness). Chi tiết ở mục [00d](#assign) |
| **Est** | person-days — **ước lượng đề xuất**, không phải số đã chốt trong tài liệu. Cần team rà lại trước khi gán sprint |
| **Dep** | Task phải xong trước. Dùng để vẽ đường găng (critical path) |
| **AC** | Acceptance Criteria — điều kiện nghiệm thu, viết ở dạng kiểm chứng được |

> ⚠️ **Lưu ý tên tầng — phải nói rõ với team ngay buổi kickoff**
>
> Tệp **"Tầng 2 – Tầng Browser Control"** thực chất là **Hạ tầng Browser**;
> tệp **"Tầng 3 – Tầng Điều khiển browser"** mới là **Điều khiển Browser**.
> Không nói trước, A và D sẽ đọc nhầm tài liệu của nhau.
>
> Thêm nữa, **Layer 1/2/3 trong tài liệu Fingerprint** là *fallback sandbox*,
> khác hoàn toàn **Cấp 1–4** của thác đổ điều khiển. Hai hệ đánh số này rất dễ bị trộn trong báo cáo.

> ℹ️ **Cách đọc backlog này**
>
> Backlog dùng **tên chức năng** của tầng, không dùng số tệp. Mỗi epic tương ứng một layer;
> trong epic, task xếp theo thứ tự phụ thuộc, không theo thứ tự ngày. Có hai cách đọc: **theo layer**
> (các epic bên dưới) và **theo người** (mục [00d](#assign)).

## 00b — Bổ sung v1.1 — Các lớp xuyên tầng còn thiếu

*Bốn tài liệu tầng mô tả logic của từng tầng, nhưng một bản demo chạy được còn cần những lớp không thuộc tầng nào. Đây là phần được bổ sung sau khi rà lại.*

> ⚠️ **Vì sao phải bổ sung**
>
> Backlog v1.0 chỉ phủ đúng 4 layer trong tài liệu kiến trúc. Nhưng để dựng một MVP hoàn chỉnh còn thiếu:
> **cấp phát tài nguyên** (ai tạo VPS, ai cấp sandbox, ai giữ trần phiên), **lưu trữ dữ liệu**
> (đặt bàn, người dùng, artifact, Registry), **lớp monitor riêng ở từng tầng** để thu số liệu benchmark,
> và **lớp benchmark cuối** (harness chạy ma trận + tính số + xuất báo cáo). Thiếu bốn lớp này thì
> hệ thống chạy được trên máy một người nhưng không tái lập được, không đo được, và không bàn giao được.

| Khoảng trống | Nay ở | Vì sao là điều kiện của MVP |
|---|---|---|
| Cấp phát hạ tầng & tài khoản cloud | EPIC-7 | Ngày 1 của kế hoạch 7 ngày đã ghi: khởi tạo VPS, cấu hình Docker Rootless, đăng ký tài khoản cloud — nhưng v1.0 không có task nào cho việc này |
| Cấp phát sandbox & trần phiên | EPIC-7 | Test tải 3–5 phiên song song cần một bộ cấp phát có trần cứng, nếu không sẽ OOM giữa lúc đo |
| Lưu trữ dữ liệu người dùng & đặt bàn | EPIC-8 | Checkpointer, Registry, lịch sử đặt bàn đều cần schema; PII khách hàng cần mã hóa và thời hạn xóa |
| Kho artifact (ảnh, HAR, HTML) | EPIC-8 | Không có artifact thì không chấm được pass/fail, không dựng lại được ca lỗi |
| Monitor riêng từng tầng | EPIC-9 | Telemetry schema đã có từ MVP-01, nhưng chưa có task nào *gắn* nó vào từng tầng và ghi ra cùng một tệp |
| Lớp benchmark cuối | EPIC-10 | MVP-61 chỉ là "chạy benchmark"; còn thiếu harness ma trận, đóng băng dataset, tính số và xuất báo cáo tái lập được |

> ℹ️ **Nguyên tắc khi thêm**
>
> Các task mới **không thay** task cũ và không đổi số hiệu cũ. Chúng đánh số từ `MVP-70` trở đi,
> mỗi epic một dải số riêng, để ai đã gán task cũ vào sprint thì không phải làm lại.

## 00c — Chế độ MVP nhanh — v1.2

*Bỏ Redis và các lớp hạ tầng nặng. Trần tài nguyên: 3–5 sandbox và 2–3 trình duyệt cùng lúc.*

> ✅ **Nguyên tắc của bản gọn**
>
> Mục tiêu là **chạy được một luồng đặt bàn thật, đo được số, và bàn giao được** — không phải dựng
> hạ tầng chịu tải. Vì vậy mọi thứ chỉ đúng khi chạy **một máy** đều được thay bằng phương án đơn giản hơn:
> Redis → SQLite + file lock; MinIO → thư mục local; Prometheus/InfluxDB → tệp CSV/JSONL; hàng đợi → SQLite claim pattern + `asyncio.Semaphore` cho trần sandbox.

### Đã bỏ khỏi MVP nhanh (9 task)

| Task | Nội dung | Lý do bỏ | Thay bằng |
|---|---|---|---|
| **MVP-43** | Snapshot/Restore CRIU/Firecracker | Hạng mục rủi ro nhất, cần quyền kernel và thời gian dựng lâu | Ngủ đông bằng checkpoint SQLite (MVP-12); chỉ đo cold-start |
| **MVP-44** | Đo cold-start sandbox | Trùng nội dung với MVP-26 | Gộp vào MVP-26 |
| **MVP-72** | Quota & concurrency control | Chỉ 3–5 phiên thì không cần hàng đợi và backpressure | Trần cứng đặt ngay trong MVP-71 |
| **MVP-81** | Redis: checkpoint, lock, cache, queue | Bỏ Redis theo yêu cầu | SQLite + file lock + `asyncio.Semaphore` |
| **MVP-85** | Backup & khôi phục | Chưa cần cho demo | `VACUUM INTO 'backup.db'` — snapshot nguyên tử, không cần dừng hệ thống (v2.1) |
| **MVP-92** | Metrics collector & lưu chuỗi thời gian | Prometheus/InfluxDB là hạ tầng thừa cho một máy | Ghi CSV/JSONL như MVP-03 đã làm |
| **MVP-93** | Log pipeline tập trung | Chưa cần khi chỉ có một máy | Log ra tệp theo `trace_id` |
| **MVP-94** | Dashboard theo tầng + cảnh báo | Chưa cần; đọc tệp log bằng script là đủ | Script tổng hợp in ra bảng trong terminal |
| **MVP-95** | Đo tài nguyên tự động theo phiên | Trùng MVP-26 | Gộp vào MVP-26 |

### Đã đơn giản hóa (10 task)

| Task | Trước | Sau |
|---|---|---|
| **MVP-12** | PostgreSQL/Redis | SQLite, dùng `AsyncSqliteSaver` của LangGraph |
| **MVP-16** | PostgreSQL `SKIP LOCKED` + Inngest Dev Server | SQLite claim pattern `BEGIN IMMEDIATE` + bảng `scheduled_wakeups` |
| **MVP-20** | Redis + PostgreSQL trong WSL2 | Không cần service DB — SQLite nhúng trong tiến trình backend |
| **MVP-24** | Redis profile lock | File lock `fcntl.flock` trên thư mục profile |
| **MVP-26** | Đo ở 1 và 25 phiên | Đo ở 1 và 3–5 phiên, gộp thêm cold-start sandbox |
| **MVP-27** | Live View tự dựng noVNC/KasmVNC | Live View có sẵn của Steel, hoặc chụp màn hình định kỳ |
| **MVP-63** | Test tải 10–25 phiên song song | Test tải 3–5 phiên song song |
| **MVP-71** | Allocator + warm pool | Allocator đơn giản, trần 3–5 phiên, không warm pool |
| **MVP-74** | Redis Lock cho profile | File lock |
| **MVP-82** | Artifact Store MinIO | Thư mục local `artifacts/<trace_id>/` |

### Trần tài nguyên của MVP nhanh

| Hạng mục | Trần | Ghi chú |
|---|---|---|
| Sandbox đồng thời | **3–5** | Tạo theo yêu cầu, không giữ pool; vượt trần thì từ chối rõ ràng |
| Trình duyệt đồng thời | **2–3** | Ví dụ 1 Chromium + 1 Camoufox (Lightpanda đã bỏ ở v1.9) |
| Phiên MXH đồng thời | ~~1–2~~ **0** | **Đã bỏ MXH (2026-11-18)** — chỉ còn web đặt bàn |
| Lưu trữ artifact | Đĩa local | Ảnh, HAR, HTML snapshot theo `trace_id` |
| Hàng đợi | `asyncio.Semaphore` | Không cần broker hay Redis |

> ⚠️ **Đánh đổi phải nói rõ trong báo cáo**
>
> Bỏ Redis là mất **lock phân tán**: phương án file lock chỉ đúng khi toàn bộ hệ thống chạy trên
> **một máy**. Nếu sau này tách ra nhiều máy hoặc nhiều container trên nhiều host, phải quay lại
> lock phân tán. Bỏ store chuỗi thời gian cũng có nghĩa là **không có dữ liệu lịch sử dài hạn** —
> mỗi đợt đo là một tệp rời, phải tự đặt tên và lưu trữ cẩn thận.

### Ưu tiên trong 74 task

| Mức | Số task | Task |
|---|---|---|
| Bắt buộc | 34 | MVP-01, 02, 03, 06, 08, 10, 11, 13, 15, 16, 17, 18, 20, 22, 30, 31, 38, 40, 41, 42, 46, 50, 52, 70, 71, 73, 76, 80, 90, 91, 110, 111, 112, 113 |
| Nên có | 37 | MVP-04, 05, 07, 12, 23, 24, 25, 26, 27, 28, 29, 32, 33, 34, 35, 36, 39, 45, 51, 53, 60, 61, 62, 63, 64, 82, 83, 84, 100, 101, 102, 103, 104, 120, 121, 122, 123 |

> **v2.1:** MVP-37, MVP-74, MVP-75 đã hủy (bỏ MXH) — tổng còn **71 task**.

Nhóm **Bắt buộc** là điều kiện để luồng đặt bàn chạy từ đầu đến cuối và có số đo. Nhóm
**Nên có** làm cho kết quả đáng tin và báo cáo đủ sức thuyết phục, nhưng có thể chạy sau khi luồng chính đã thông.

## 00d — Phân công theo người — A đến F

*Sáu người, sáu phạm vi tách bạch. Mỗi task chỉ có một owner; phần giao tiếp giữa các tầng đi qua Interface Spec của MVP-01, không qua người.*

> ℹ️ **Ranh giới phạm vi — phần quan trọng nhất**
>
> **A** chỉ *quản lý và cấp phát browser*. **B** chỉ *quản lý và cấp phát sandbox (VM)*.
> **C** xây toàn bộ hệ thống agent. **D** xây toàn bộ phần browser control. **E** làm các task còn lại.
> **F** xây API layer và FE web app (v2.0).
> A và B là hai người *cung cấp nền*, không viết logic nghiệp vụ; C và D là hai người *tiêu thụ nền* qua API đã khóa ở MVP-01.

| Người | Phạm vi | Số task | Person-days | Tải so với 15 ngày |
|---|---|---|---|---|
| **A** | Quản lý và cấp phát browser | 8 | 14,0 pd | Sát trần |
| **B** | Quản lý và cấp phát sandbox (VM) | 9 | 13,5 pd | Sát trần |
| **C** | Xây dựng toàn bộ hệ thống agent | 17 | 20,5 pd | Quá tải |
| **D** | Xây dựng toàn bộ phần browser control | 12 | 25,0 pd | Quá tải |
| **E** | Các task còn lại | 20 | 36,5 pd | Quá tải |
| **F** | API layer + FE web app | 8 | 16,0 pd | Quá tải nhẹ |

> ⚠️ **Mất cân bằng tải — cần xử lý trước khi gán sprint**
>
> **C**, **D** và **E** vượt trần 15 ngày của một người sau khi thêm 9 task ở v1.5 và 4 task ở v1.8 (C lên 20,5 pd). Sau v1.9, A giảm còn 8 task · 14,0 pd vì bỏ Lightpanda. E nặng nhất vì ôm cả benchmark, dữ liệu, monitor và harness; D nặng thứ hai vì nhận thêm ~~luồng MXH,~~ Success/Failure Detector và Live View UI. **v2.0:** F nhận 8 task API + FE (16,0 pd) — vượt nhẹ trần; nếu F làm một mình thì EPIC-12 (FE) có thể dời sau mốc 15 ngày vì demo CLI/API vẫn chạy được. **v2.1:** bỏ MXH — A giảm 3,5 pd (hủy MVP-74/75), D giảm 3 pd (hủy MVP-37).
> Ba cách xử lý, chọn một: **(1)** tách E thành E1 (dữ liệu + monitor: EPIC-8, EPIC-9) và E2 (benchmark + báo cáo: EPIC-5, EPIC-10);
> **(2)** chuyển EPIC-10 (MVP-100 đến MVP-104) cho C sau khi agent xong ở Ngày 10;
> **(3)** giữ nguyên người nhưng dời EPIC-10 ra sau mốc 15 ngày, vì báo cáo cuối không chặn demo.

> ℹ️ **Bảy task nằm khác epic với người làm**
>
> Vài task thuộc epic của tầng này nhưng về phạm vi lại thuộc người khác. Giữ nguyên số hiệu, chỉ đổi owner:
> **MVP-02** (Gateway CDP) nằm ở EPIC-0 nhưng là việc của **D**;
> **MVP-27** (Live View) nằm ở EPIC-2 nhưng là việc của **D**;
> **MVP-20** (nền WSL2 + Docker Rootless) nằm ở EPIC-2 nhưng là việc của **B**;
> **MVP-74** và **MVP-75** (Profile Vault, cấp phát proxy) nằm ở EPIC-7 nhưng là việc của **A**;
> **MVP-28** (Live View UI khách) nằm ở EPIC-2 nhưng là việc của **D**;
> **MVP-76** (Browser Allocator) nằm ở EPIC-7 nhưng là việc của **A**.
> Khi import Jira, gán theo cột Owner, không gán theo epic.

### Người A — Hạ tầng browser

Dựng và chạy các engine trình duyệt, giữ profile, gán proxy, đo tài nguyên browser. **Không** viết logic điều khiển trang, **không** viết logic agent.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-22** | Chromium/Patchright + Steel self-host | 2 | MVP-20 |
| **MVP-23** | Camoufox (nhân Firefox chống phát hiện) | 2 | MVP-20 |
| **MVP-24** | Session persistence + file lock profile | 2 | MVP-23 |
| **MVP-25** | Tích hợp proxy dân cư | 2 | MVP-24 |
| **MVP-26** | Đo RAM/CPU/cold-start hạ tầng | 1 | MVP-22, MVP-23 |
| **MVP-74** | ~~Profile Vault & cấp phát profile MXH~~ **ĐÃ HỦY** | ~~2~~ 0 | — |
| **MVP-75** | ~~Cấp phát proxy & gán IP cố định~~ **ĐÃ HỦY** | ~~1,5~~ 0 | — |
| **MVP-76** | Browser Allocator (trần 2–3 trình duyệt) | 1,5 | MVP-20, MVP-22, MVP-23 |

### Người B — Hạ tầng sandbox

Nền WSL2 + Docker Rootless, cô lập mạng, vòng đời sandbox, allocator và trần phiên. **Không** chạm vào browser hay agent.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-20** | Nền WSL2 Ubuntu 24.04 + Docker Rootless | 1 | — |
| **MVP-40** | Sandbox cô lập trên Docker Rootless | 2 | MVP-20 |
| **MVP-41** | Chặn SSRF — Zero-Egress Internal Network | 1 | MVP-40 |
| **MVP-42** | Ephemeral lifecycle | 1 | MVP-40 |
| **MVP-70** | Cấp phát hạ tầng nền & tài khoản cloud | 1,5 | — |
| **MVP-71** | Sandbox Allocator đơn giản (trần 3–5 phiên) | 3 | MVP-40, MVP-70 |
| **MVP-73** | Session Lifecycle Manager | 2 | MVP-71 |
| **MVP-45** | Seccomp & hardening container | 1 | MVP-40 |
| **MVP-46** | Giới hạn tài nguyên per-container (cgroups) | 1 | MVP-40 |

### Người C — Agent

State machine LangGraph, guardrails 3 lớp, checkpointer, durable wrapper, router định tuyến cấp, telemetry schema, runner, **hợp đồng control-plane** giao việc xuống browser control, và **30% dữ liệu browser context** (vault, lease, write-back, quota) phối hợp với A và E.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-01** | Khóa Interface Spec + Telemetry Schema | 1,5 | — |
| **MVP-03** | Runner + Logger + Telemetry tự động | 1,5 | MVP-01 |
| **MVP-04** | Ba seam tự học (chưa implement) | 0,5 | MVP-01 |
| **MVP-05** | Khung báo cáo SA | 0,5 | — |
| **MVP-06** | Control-plane contract Agent ↔ Browser Control | 1,5 | MVP-01 |
| **MVP-07** | Bắt tay HITL Agent ↔ Live View (D phối hợp) | 1 | MVP-12, MVP-27 |
| **MVP-10** | LangGraph state machine (sườn tối giản) | 2 | MVP-01 |
| **MVP-11** | Input Guardrails bằng PydanticAI | 1 | MVP-10 |
| **MVP-12** | Checkpointer + interrupt() cho ngủ đông | 2 | MVP-10 |
| **MVP-13** | Master Router định tuyến cấp | 1 | MVP-02, MVP-04 |
| **MVP-08** | Đóng gói một lệnh (compose/Makefile) | 1 | MVP-03, MVP-20 |
| **MVP-15** | Guardrails Lớp 2 — BAML Form Extraction & Injection Guard | 1,5 | MVP-11 |
| **MVP-16** | Outer Durable Wrapper & Webhook Wakeup | 1,5 | MVP-12, MVP-24 |
| **MVP-17** | Guardrails Lớp 3 — Action Risk Classifier & Safety HITL Gate | 1 | MVP-11, MVP-15 |
| **MVP-18** | Bộ 5 bài test E2E nghiệm thu | 1 | MVP-07, MVP-13, MVP-16, MVP-24, MVP-32 |
| **MVP-39** | Idempotency & hủy bàn | 1 | MVP-06, MVP-16, MVP-80 |
| **MVP-29** | Token Rotation & Profile health_score | 1 | MVP-24 |

### Người D — Browser control

Gateway CDP/WebSocket, bốn cấp điều khiển, hot-swap fallback, chuẩn chờ xong, Live View HITL và **đầu nhận bắt tay HITL** từ agent.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-02** | Unified CDP/WebSocket Gateway | 2 | MVP-01 |
| **MVP-27** | Live View HITL mức tối giản | 3 | MVP-22 |
| **MVP-30** | Cấp 1 — Direct API Replay | 2 | MVP-02 |
| **MVP-31** | Cấp 2 — Playwright Workflow tham số hóa | 2 | MVP-30 |
| **MVP-32** | Cấp 3 — Stagehand (AI khám phá DOM/A11y Tree) | 3 | MVP-31, MVP-23 |
| **MVP-33** | Cấp 4 — Browser Use + vision API | 3 | MVP-22 |
| **MVP-34** | Hot-Swap Fallback không gián đoạn | 2 | MVP-30 đến MVP-33 |
| **MVP-35** | Chuẩn hóa "cách chờ xong" | 1 | MVP-31, MVP-32 |
| **MVP-36** | CDP Network Sniffer (seam tự học) | 1 | MVP-32 |
| **MVP-28** | Live View UI cho khách | 1,5 | MVP-27 |
| **MVP-37** | ~~Luồng đặt bàn qua MXH (Fanpage, Zalo OA, Instagram DM)~~ **ĐÃ HỦY** | ~~3~~ 0 | — |
| **MVP-38** | Success/Failure Detector & đường thoát khi 4 cấp fail | 1,5 | MVP-35, MVP-82 |

### Người E — Benchmark & dữ liệu

Benchmark, dữ liệu và PII, monitor, harness ma trận, thống kê, cost model và báo cáo cuối.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-50** | Chốt 10–12 website mục tiêu + nhãn A/B | 1 | — |
| **MVP-51** | Ground truth pass/fail cho từng site | 2 | MVP-50 |
| **MVP-52** | Kịch bản đặt bàn mẫu dạng JSON | 1 | MVP-01 |
| **MVP-53** | Tài khoản test + kênh nhận OTP | 1 | MVP-50 |
| **MVP-60** | Thang điểm độ phức tạp triển khai (9 tiêu chí / 45 điểm) | 1,5 | MVP-02 |
| **MVP-61** | Benchmark 4 trục | 3 | MVP-30 đến MVP-42 |
| **MVP-62** | Kiểm thử anti-bot | 2 | MVP-23 |
| **MVP-63** | Test tải 3–5 phiên song song | 1,5 | MVP-26 |
| **MVP-64** | Báo cáo benchmark + đề xuất tech stack | 2 | MVP-61, MVP-62, MVP-63 |
| **MVP-80** | Schema SQLite + migration | 2 | MVP-20 |
| **MVP-82** | Artifact Store bằng thư mục local: ảnh, HAR, HTML snapshot | 2 | MVP-80 |
| **MVP-83** | Dữ liệu người dùng & PII | 2 | MVP-80 |
| **MVP-84** | Registry API Template & Playwright Workflow | 2 | MVP-80, MVP-04 |
| **MVP-90** | Chuẩn trace_id xuyên tầng | 1 | MVP-01 |
| **MVP-91** | Instrumentation từng tầng | 2,5 | MVP-90 |
| **MVP-100** | Matrix runner | 3 | MVP-61, MVP-71 |
| **MVP-101** | Đóng băng dataset & ground truth | 1,5 | MVP-50, MVP-51 |
| **MVP-102** | Statistics engine | 2 | MVP-100 |
| **MVP-103** | Cost model | 1,5 | MVP-102 |
| **MVP-104** | Report generator + phụ lục tái lập | 2 | MVP-102, MVP-103 |

### Người F — API layer & FE web app (v2.0)

Cổng giao tiếp FE ↔ BE theo mục 7 của system design v2.1: REST, SSE, WebSocket, auth, rate limit, trace middleware, và FE web app đặt bàn. **Không** viết logic agent hay browser control — chỉ gọi qua hợp đồng của C và D.

| Task | Nội dung | Est (pd) | Dep |
|---|---|---|---|
| **MVP-110** | FastAPI skeleton + REST endpoints + error taxonomy | 3 | MVP-01, MVP-80 |
| **MVP-111** | SSE tiến trình + WebSocket Live View | 2 | MVP-110, MVP-07 |
| **MVP-112** | Auth + rate limit + trace_id middleware | 2 | MVP-110, MVP-90 |
| **MVP-113** | Booking API: tạo/tra cứu/hủy/HITL + Idempotency-Key | 2 | MVP-110, MVP-39 |
| **MVP-120** | FE khung web app + form đặt bàn | 3 | MVP-110 |
| **MVP-121** | FE theo dõi tiến trình (SSE) + lịch sử | 2 | MVP-120, MVP-111 |
| **MVP-122** | FE Live View nhập OTP (WS) | 1,5 | MVP-120, MVP-111, MVP-28 |
| **MVP-123** | FE polish: trạng thái lỗi, responsive, a11y | 0,5 | MVP-121, MVP-122 |

> ✅ **Điểm giao giữa các cặp**
>
> **C ↔ D:** đây là biên quan trọng nhất và trước đây bị thiếu — agent *không* nằm trong browser control, nó giao việc qua hợp đồng `execute_tier()` của **MVP-06** và bắt tay HITL qua **MVP-07**.
> **A ↔ D:** D gọi browser qua Gateway của MVP-02, không tự dựng engine. **B ↔ C:** C xin sandbox qua Allocator của MVP-71, không tự tạo container.
> **B ↔ A:** browser chạy *trong* sandbox, nên B khóa nền trước (MVP-20) rồi A mới dựng engine lên trên.
> **E ↔ tất cả:** E chỉ đọc số đo do C và D phát ra theo schema MVP-01, không tự đo lại.
> **F ↔ C/D:** F chỉ gọi API công khai của C (booking, agent) và D (Live View), không đọc thẳng DB hay gọi CDP. FE không nhận thông tin kỹ thuật nội bộ (tên profile, fingerprint seed, proxy IP, đường dẫn artifact).

## EPIC-0 — Nền tảng & Chuẩn chung

*Cross-cutting — làm trước, mọi layer khác chảy ra từ đây.*

**EPIC-0** Nền tảng & Chuẩn chung — Owner: C (+ D) · 9 task · +1 v1.8

#### MVP-01 — Khóa Interface Spec + Telemetry Schema

`Task` · `Owner: C · Agent` · `Est: 1,5 pd` · `Dep: —`

**Description:** Định nghĩa hợp đồng chung cho 3 lớp (sandbox, browser infra, browser control) và schema log telemetry. Spec phải được kiểm chứng bằng **ít nhất 2 công nghệ khác nhân** (ví dụ Chromium CDP vs Camoufox Juggler/BiDi) trước khi đóng băng — không khóa non ngay Ngày 1. **v1.8 bổ sung** hai hợp đồng dữ liệu còn thiếu: `BookingRequest`/`AgentState` (`request_id`, `customer_info`, `target_domain`, `channel`, `tier`, `browser_session_ref`, `step_history[]`, `artifact_refs`, `status`) và **ContextLease API** `acquire`/`heartbeat`/`release` dùng chung giữa C, A và E; schema telemetry thêm `loop_count` và `error_class`.

**AC:** Spec có `open_session()`, `click()`, `screenshot()`; schema log có `tier_used`, `artifact_id`, `cache_hit`, `cold_warm`; đóng băng hết Ngày 2, sau đó không đổi.

#### MVP-02 — Unified CDP/WebSocket Gateway

`Story` · `Owner: D · Browser control` · `Est: 2 pd` · `Dep: MVP-01`

**Description:** Cổng giao tiếp duy nhất `wss://browser-endpoint` để tầng điều khiển không cần biết bên dưới là engine nào. Đọc capability declaration của từng adapter để định tuyến cấp thực thi; adapter thiếu capability phải trả `CapabilityNotSupported`, không được crash. Kèm tài liệu API cho tầng điều khiển.

**AC:** Cùng một script điều khiển được cả 2 endpoint (Chromium/Patchright, Camoufox); lỗi capability phát hiện lúc định tuyến (0 ms), không phải giữa task.

#### MVP-03 — Runner + Logger + Telemetry tự động

`Story` · `Owner: C · Agent` · `Est: 1,5 pd` · `Dep: MVP-01`

**Description:** Khung Python runner nhận JSON đầu vào, chạy task, xuất log CSV/JSON đúng schema. Đo latency bằng **đồng hồ monotonic**, không dùng wall clock; có token counter và script tổng hợp p50/p95.

**AC:** Runner ra file log đúng schema ngay Ngày 1; một lệnh chạy hết từ JSON vào đến kết quả ra.

#### MVP-04 — Ba seam tự học (chưa implement)

`Task` · `Owner: C · Agent` · `Est: 0,5 pd` · `Dep: MVP-01`

**Description:** Chừa sẵn 3 điểm nối để lắp tự học ngược sau mà không phải chạy lại benchmark: (1) 4 trường telemetry để `null`; (2) 2 bảng Registry `api_template` + `playwright_workflow` seed bằng tay; (3) adapter hook `on_task_success(artifact)` dạng hàm rỗng.

**AC:** 3 seam tồn tại trong code, có test chứng minh ghi được vào Registry bằng seed thủ công.

#### MVP-05 — Khung báo cáo SA

`Task` · `Owner: C · Agent` · `Est: 0,5 pd` · `Dep: —`

**Description:** Dựng khung báo cáo từ Ngày 1, không đợi Ngày 15: 4 bảng (hạ tầng, điều khiển, anti-bot, chi phí) + mục khuyến nghị + mục "điều chưa kiểm chứng".

**AC:** Khung có đủ đề mục, số điền sau.

#### MVP-06 — Control-plane contract Agent ↔ Browser Control

`Task` · `Owner: C · Agent` · `Est: 1,5 pd` · `Dep: MVP-01`

**Description:** Định nghĩa hợp đồng giao việc giữa agent và browser control: RPC `execute_tier(tier, task_spec, session_id) -> TaskResult` và schema `TaskResult` (thành công/thất bại, `tier_used`, `artifact_id`, lớp lỗi). Agent **không gọi thẳng CDP**, chỉ gọi qua hợp đồng này; browser control không tự quyết định trượt cấp. D review spec trước khi đóng băng cùng MVP-01. **v1.8 bổ sung** thư viện Pydantic models + async RPC/HTTP client cho hợp đồng này, và bộ mã trạng thái `SUCCESS | NEED_OTP | NEED_USER_CONFIRM | NEED_REASONING | NO_ONLINE_FORM | FALLBACK_FAILED`, kèm `a11y_tree_snapshot` (khi gặp web mới), `detected_channel`, `hitl_trigger`, `failure_code`, `latest_storage_state`.

**AC:** Cùng một node LangGraph chạy được cả 4 cấp mà không đổi code; lỗi cấp dưới trả về đúng lớp lỗi để Master Router quyết định trượt cấp.

#### MVP-07 — Bắt tay HITL Agent ↔ Live View

`Story` · `Owner: C · Agent (+ D)` · `Est: 1 pd` · `Dep: MVP-12, MVP-27`

**Description:** Nối `interrupt()` của agent với Live View của browser control: agent phát tín hiệu dừng và yêu cầu mở màn hình, browser control giữ nguyên trang ở đúng bước chờ, khách nhập OTP/quét QR cọc xong thì phát tín hiệu đánh thức để LangGraph khôi phục đúng bước đang dừng. Đây là biên giới còn thiếu giữa Action Guardrails (Lớp 3) và Live View. **v1.8 tách hai chế độ:** (1) *Short-Wait* — OTP/quét QR cọc 1–5 phút, dừng ở Safety Gate (MVP-15) rồi mở Live View; (2) *Long-Wait Hibernate* — ~~chờ nhà hàng trả lời Fanpage/Zalo 15 phút đến nhiều giờ/ngày~~ **đã bỏ nhánh MXH ở v2.1**; chỉ còn ngủ đông cho trường hợp chờ OTP kéo dài: xuất snapshot, write-back cookies/`cf_clearance`/refresh_token, đóng hẳn browser và sandbox (RAM về 0 MB), rồi `interrupt()`; khi webhook tới thì nạp lại context, mở lại browser và resume đúng bước.

**AC:** Luồng OTP chạy trọn: dừng → khách nhập → chạy tiếp, không mất trạng thái trang và không mở lại phiên mới. ~~Luồng chờ MXH chứng minh RAM browser + RAM agent = 0 MB khi đang ngủ và khôi phục đúng trạng thái phiên khi có webhook.~~ **v2.1:** ngủ đông chờ OTP kéo dài chứng minh RAM browser + RAM agent = 0 MB khi đang ngủ và khôi phục đúng trạng thái phiên khi có webhook.

#### MVP-08 — Đóng gói một lệnh (compose/Makefile)

`Task` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-03, MVP-20`

**Description:** Một lệnh duy nhất dựng toàn bộ stack local (sandbox, browser control, agent, API) bằng `docker compose` + `Makefile`, để người mới chạy lại được môi trường mà không phải làm theo checklist thủ công. **v2.0:** không có service database — SQLite là file nhúng trong tiến trình backend. Đây là lớp xuyên tầng còn thiếu: hiện mỗi người tự dựng môi trường nên kết quả đo không tái lập.

**AC:** `make up` từ máy sạch dựng đủ service và healthcheck xanh; `make down` dọn sạch container và volume tạm.

#### MVP-39 — Idempotency & hủy bàn

`Task` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-06, MVP-80`

**Description:** Bảo đảm một yêu cầu đặt bàn chỉ tạo đúng một bản ghi dù agent retry hoặc chuyển cấp giữa chừng; thêm luồng hủy bàn khi khách đổi ý. Dùng khóa idempotency theo (site, ngày, giờ, `phone_hash`) và ghi trạng thái bản ghi để tránh đặt trùng. Việc xuyên tầng: chạm cả hợp đồng control-plane (MVP-06) lẫn schema dữ liệu (MVP-80). **v1.8 bổ sung:** khóa phải chặn cả trường hợp node bị replay sau crash giữa node (MVP-16); hủy bàn phải giải phóng toàn bộ ContextLease và checkpoint liên quan.

**AC:** Chạy lại cùng một task không sinh bản ghi thứ hai; hủy bàn cập nhật đúng trạng thái và giải phóng tài nguyên phiên. Chạy lại cùng `request_id` hoặc khóa idempotency không sinh bản ghi đặt trùng thứ hai; hủy bàn nhả toàn bộ lease.

## EPIC-1 — Tầng 1 — Agent Orchestration & Guardrails

*Bộ não điều phối: suy luận, lập kế hoạch, chốt chặn an toàn.*

**EPIC-1** Tầng 1 — Agent Orchestration & Guardrails — Owner: C · 9 task

#### MVP-10 — LangGraph state machine (sườn tối giản)

`Story` · `Owner: C · Agent` · `Est: 2 pd` · `Dep: MVP-01`

**Description:** Điều phối tuần tự nhận JSON cố định (ngày, giờ, số người, SĐT), quản lý luồng có chu trình để chuyển cấp 1-2-3-4 mà không đứt phiên. **Guardrails chỉ ở mức tối giản** trong MVP: Lớp 1 (MVP-11), Lớp 2 (MVP-15), Lớp 3 qua HITL (MVP-07); chưa làm bản đầy đủ của Guardrails AI/NeMo. **v1.8 bổ sung** 6 node: `intake_and_normalize`, `acquire_context`, `route_strategy`, `parse_and_guard`, `safety_hitl_gate`, `finalize_and_release`; mọi node idempotent, không giữ state trong biến toàn cục; `AgentState` chỉ lưu `artifact_id` tham chiếu, không nhồi A11y Tree hay ảnh vào checkpoint; kèm **Anti-Loop Detector** (giới hạn `max_steps` + kiểm tra lặp hash trạng thái theo `url`, `a11y_hash`, `last_action`).

**AC:** Chạy được 3 kịch bản mẫu; chuyển cấp không làm mất trạng thái trang. Ghi state 5–15 ms/node, State JSON ≤ 15 KB; lặp trạng thái N lần liên tiếp thì Anti-Loop Detector tự ngắt đúng ngưỡng cấu hình.

#### MVP-11 — Input Guardrails bằng PydanticAI

`Task` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-10`

**Description:** Ép kiểu dữ liệu cứng trước khi mở trình duyệt: `YYYY-MM-DD` (chặn ngày quá khứ), giờ hợp lệ, SĐT Việt Nam chuẩn, `party_size` (int > 0), `allow_deposit_max` (≥ 0). Chặn prompt injection bằng schema khóa đầu ra.

**AC:** Chuỗi injection đưa vào `party_size: int` bị chặn; validate 10.000 JSON dưới 1 giây.

#### MVP-12 — Checkpointer + interrupt() cho ngủ đông

`Story` · `Owner: C · Agent` · `Est: 2 pd` · `Dep: MVP-10`

**Description:** Lưu toàn bộ trạng thái phiên xuống SQLite (dùng `AsyncSqliteSaver` của `langgraph-checkpoint-sqlite`) khi chờ OTP ~~hoặc chờ nhà hàng trả lời tin nhắn MXH~~, giải phóng RAM tiến trình; khôi phục đúng bước đang dừng khi có webhook/khách xác nhận. Không dùng Redis, không dùng PostgreSQL. **v1.8 bổ sung:** ghi sau *mỗi* node (không gộp nhiều node một lần ghi), `thread_id = request_id`, khôi phục qua `Command(resume=...)`. **v2.0:** checkpointer là `AsyncSqliteSaver` trỏ vào `data/app.db` (WAL mode), không phải `PostgresSaver`. **v2.1:** bỏ nhánh chờ tin nhắn MXH.

**AC:** `kill -9` tiến trình, RAM về 0, bản ghi checkpoint còn nguyên và nạp lại được.

#### MVP-13 — Master Router định tuyến cấp

`Story` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-02, MVP-04`

**Description:** Tra Registry để chọn cấp thực thi: có API Template thì Cấp 1; có Playwright Workflow thì Cấp 2; chưa có thì Cấp 3/4. Đọc capability declaration trước khi giao việc. **v1.8 bổ sung:** ~~khi Tầng 3 trả `NO_ONLINE_FORM` kèm link Fanpage/Zalo OA thì tự chuyển sang luồng MXH (MVP-37) và lấy profile MXH~~ **đã bỏ ở v2.1**; tự động hạ cấp (auto-demote) và gắn cờ cảnh báo khi template Cấp 1/2 lỗi liên tiếp.

**AC:** Định tuyến đúng trên 10–12 site; log ghi rõ lý do chọn cấp.

#### MVP-15 — Guardrails Lớp 2 — Context/Extraction

`Task` · `Owner: C · Agent` · `Est: 1,5 pd` · `Dep: MVP-11`

**Description:** Lớp chặn thứ hai sau Input Guardrails: kiểm tra ngữ cảnh và dữ liệu trích xuất từ trang (giá, giờ trống, tên nhà hàng) trước khi agent hành động, chặn khi nội dung trang bị nhiễu hoặc cố tình đánh lừa (prompt injection trong DOM). Bổ sung lớp còn thiếu giữa Input Guardrails (MVP-11) và Action Guardrails (Lớp 3). **v1.8 bổ sung:** node `parse_and_guard` dùng **BAML** (Schema-Aligned Parsing) nhận Accessibility Tree rút gọn (15–35 KB) từ Tầng 3 để ánh xạ trường form đặt bàn (ngày, giờ, số khách, SĐT, chi nhánh, điều kiện đặt cọc) và phát hiện thông tin còn thiếu; tự sửa lỗi JSON nhẹ phía client để tránh phạt trễ retry (+1,5–3,0 s) và tiết kiệm 30–40% token mô tả định dạng. Kèm **Data-Control Isolation**: tách `trusted_user_intent` khỏi `untrusted_web_observation` để chặn Indirect Prompt Injection sửa `party_size`, SĐT, giờ đặt hoặc ép chi tiền ngoài chỉ định.

**AC:** Trang chứa chỉ dẫn độc hại trong DOM bị chặn ở lớp này; dữ liệu trích xuất sai định dạng không được chuyển sang bước đặt bàn. BAML parse được JSON lỗi cú pháp nhẹ phía client (< 0,1 ms) mà không gọi lại LLM; tiết kiệm 30–40% format token so với JSON Schema đầy đủ trên cùng một A11y Tree mẫu; chèn chỉ dẫn độc hại vào DOM giả lập bị chặn 100%, giữ nguyên số khách và SĐT gốc.

#### MVP-16 — Outer Durable Wrapper & Webhook Wakeup (LongTaskRunner)

`Story` · `Owner: C · Agent` · `Est: 1,5 pd` · `Dep: MVP-12, MVP-24`

**Description:** Lớp bọc bền vững bên ngoài LangGraph, bù đúng hai điểm yếu đã ghi ở tài liệu Tầng 1: (1) phục hồi tự động khi worker sập giữa node trước khi kịp ghi checkpoint; (2) hẹn giờ timeout (OTP 15 phút ~~, MXH nhiều giờ/ngày~~) và nhận webhook đánh thức đúng `thread_id`. Đóng gói sau interface trừu tượng `LongTaskRunner` (`start_task`, `wait_event_with_timeout`, `wake_task`). **v2.0:** MVP triển khai bằng **SQLite Durable Queue** — claim pattern trong `BEGIN IMMEDIATE` (SQLite không có `SKIP LOCKED`) + bảng `scheduled_wakeups`, cột `claimed_at`/`claimed_by`. Không cần service mới; giữ đường nâng cấp lên Temporal khi scale mà không viết lại đồ thị LangGraph. **v2.1:** bỏ nhánh timeout MXH.

**AC:** Giả lập `kill -9` worker ngay giữa lúc node đang thực thi (chưa kịp ghi checkpoint) thì LongTaskRunner tự thu hồi và chạy lại node idempotent đó, không treo tác vụ; webhook OTP ~~/MXH~~ bắn sau khi ngủ đánh thức đúng `thread_id`; quá timeout thì đóng phiên sạch và nhả lease.

#### MVP-17 — Guardrails Lớp 3 — Action Risk Classifier & Safety HITL Gate

`Task` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-11, MVP-15`

**Description:** Bộ phân loại rủi ro hành động trước khi agent phát lệnh thực thi xuống Tầng 3. Low-risk (mở trang, chọn ngày/giờ, điền tên/SĐT, kiểm tra giờ trống) chạy tự động 100%. High-risk (xác nhận đặt cọc vượt `allow_deposit_max`, nhập thông tin thẻ, nhập OTP, nút Submit đặt bàn cuối cùng nếu cấu hình yêu cầu duyệt) bị chặn cứng và buộc chuyển qua HITL (MVP-07). Đây là lớp thứ ba trong ba lớp guardrails tối giản của MVP.

**AC:** 100% hành động High-risk không được đẩy xuống Tầng 3 nếu thiếu tín hiệu duyệt từ khách sau `interrupt()`; kiểm tra đúng 3 ca biên tiền cọc: dưới ngưỡng, bằng ngưỡng, trên ngưỡng `allow_deposit_max`.

#### MVP-18 — Bộ 5 bài test E2E nghiệm thu

`Task` · `Owner: C · Agent` · `Est: 1 pd` · `Dep: MVP-07, MVP-13, MVP-16, MVP-24, MVP-32`

**Description:** Tự động hóa và chạy nghiệm thu 5 kịch bản bắt buộc: (1) Crash & Long-Task Recovery — `kill -9` lúc chờ OTP và giữa node, tự khôi phục khi bắn webhook; (2) Race Condition Context Lock — 5 request đồng thời vào 1 `profile_id` ~~MXH~~ **web**, chỉ 1 request lấy được lock; (3) Write-back Preservation — sinh cookie giả lập mới ở lượt 1, hibernate đóng browser, resume lượt 2 nhận đủ cookie mới; (4) Unseen New Website Loại B — trang chưa có trong Registry, đẩy Cấp 3 + BAML extract đúng trường rồi dừng đúng tại Safety Gate; (5) Indirect Prompt Injection — chỉ dẫn độc hại trong HTML bị chặn 100%.

**AC:** 5/5 bài test pytest pass 100% trước Cổng 4 (hết Ngày 12); xuất bảng số đo thực tế theo 4 tiêu chí: latency/bước, token/bước, RAM lúc hibernate, tỷ lệ pass.

#### MVP-29 — Token Rotation Scheduler & Profile health_score Monitor

`Task` · `Owner: C · Agent (+ A)` · `Est: 1 pd` · `Dep: MVP-24`

**Description:** Tiến trình định kỳ (hoặc kiểm tra trước khi cấp context) dùng refresh_token lấy access_token mới trước khi phiên hết hạn để không đứt luồng giữa chừng; cập nhật `health_score` của từng profile sau mỗi phiên và gắn cờ cảnh báo khi refresh thất bại hoặc profile có dấu hiệu bị checkpoint. Đây là task phủ **hổng (1)** đã ghi ở mục Điểm cần xác nhận: phát hiện IP bị ban và ~~nick MXH~~ **profile web** bị checkpoint giữa phiên.

**AC:** Giả lập token sắp hết hạn thì job xoay vòng cập nhật được token mới; giả lập refresh fail thì profile chuyển trạng thái degraded và không được cấp cho tác vụ mới; profile bị checkpoint bị gắn cờ và loại khỏi pool.

## EPIC-2 — Tầng 2 — Hạ tầng Browser

*Chống phát hiện bot, duy trì phiên đăng nhập, hiệu suất bộ nhớ và Live View.*

**EPIC-2** Tầng 2 — Hạ tầng Browser — Owner: A (+ B, D) · 8 task

> 🚫 **v1.9 — Đã bỏ Lightpanda (MVP-21)**
>
> Theo quyết định của chủ dự án ngày 18/11, **Lightpanda không dùng nữa**. Task MVP-21 bị xóa khỏi backlog; số hiệu MVP-21 để trống, không tái sử dụng cho nội dung khác trừ khi có quyết định riêng.
>
> **Hệ quả phải xử lý:** còn **2 engine** là Chromium/Patchright (MVP-22) và Camoufox (MVP-23). **Cấp 1 — Direct API Replay (MVP-30)** trước đây dựa vào Lightpanda để chạy 1–2 giây với RAM thấp; nay phải chạy trên Chromium/Patchright, nên cold-start và RAM tăng và con số 1–2 giây không còn đúng — phải đo lại trong MVP-26 và MVP-61. **Cổng 2** hạ từ 3 endpoint xuống 2 endpoint. **MVP-35** chuẩn hóa chờ xong cho 2 driver thay vì 3.
>
> **Tải người A giảm:** từ 9 task · 15,0 pd xuống **8 task · 14,0 pd**. Đây là chỗ có thể san bớt việc cho C, D hoặc E đang quá tải, nhưng phải do bạn quyết định — backlog không tự đổi owner.
>
> **Còn treo:** tài liệu `tech-stack-mvp-browser-agent.md` vẫn liệt kê Lightpanda trong nhóm công nghệ; cần cập nhật cho khớp nếu bạn muốn hai tài liệu không mâu thuẫn.

> ℹ️ **Đề xuất từ thành viên hạ tầng browser — đã rà ngày 18/11**
>
> Đề xuất gửi ngày 18/11 dùng lại số hiệu MVP-21, 22, 23, 27, 28, 31 cho nội dung khác với backlog này, nên **không import theo số hiệu**. Phần giá trị đã gộp vào task hiện có: Xvfb headed, cách chạy theo loại việc và tự khởi động lại khi vượt RAM → **MVP-22**; seed và timezone trong profile → **MVP-24**; giới hạn phiên/IP, timezone khớp IP, WebRTC không lộ IP → **MVP-25**; Chrome thường làm mốc đo → **MVP-26**; tài liệu API của cổng → **MVP-02**.
>
> Không đưa vào vì trùng phạm vi người khác: *Browser Gateway* đã có ở **MVP-02** (cổng), **MVP-76** (cấp phát trình duyệt) và **MVP-73** (vòng đời phiên); *benchmark vượt bot* thuộc **MVP-62** và **MVP-61** của E; *báo cáo + đề xuất engine* thuộc **MVP-64** của E. *Camoufox có điều kiện* bị loại vì Camoufox đã là engine chốt cho ca khó/anti-bot web ở **MVP-23** (MXH đã bỏ ở v2.1). *CloakBrowser* chưa có trong tech stack v1.2 — chờ quyết định trước khi thêm task.

#### MVP-20 — Nền WSL2 Ubuntu 24.04 + Docker Rootless

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1 pd` · `Dep: —`

**Description:** Dựng nền Linux cho toàn bộ stack trên Windows 11 Pro. Không cài Python/Node bản Windows song song để tránh hai môi trường lệch nhau. Docker Rootless để giảm rủi ro thoát quyền.

**AC:** `wsl -l -v` ra VERSION 2; `docker run --rm hello-world` pass; không cần service DB — SQLite nhúng trong tiến trình backend (v2.0).

#### MVP-22 — Chromium/Patchright + Steel self-host

`Task` · `Owner: A · Hạ tầng browser` · `Est: 2 pd` · `Dep: MVP-20`

**Description:** Dựng endpoint Chromium vá lỗ hổng CDP, bọc Steel self-host để quản lý phiên, tự diệt zombie process và xuất luồng Live View. Chạy **headed trên Xvfb**: mỗi tiến trình một màn hình X ảo riêng để click ở mức hệ điều hành và chụp ảnh không nhầm cửa sổ; font cài theo persona. Cách chạy chia theo loại việc: web nhà hàng dùng 1 tiến trình mở nhiều context; ~~nick Zalo/Facebook dùng mỗi profile một tiến trình, seed cố định, bật humanize~~ **nhánh MXH đã bỏ ở v2.1** — ca khó web vẫn dùng seed cố định và humanize. Tiến trình tự khởi động lại khi RAM vượt ngưỡng.

**AC:** Endpoint chạy độc lập; tự thu hồi tiến trình treo sau khi task kết thúc; hai tiến trình chạy song song không chụp nhầm màn hình của nhau; tiến trình vượt ngưỡng RAM tự khởi động lại.

#### MVP-23 — Camoufox (nhân Firefox chống phát hiện)

`Task` · `Owner: A · Hạ tầng browser` · `Est: 2 pd` · `Dep: MVP-20`

**Description:** Dựng Camoufox cho ~~nhóm MXH và~~ ca khó web. Ghi nhận ràng buộc: chạy Gecko/Juggler/BiDi, **không nối trực tiếp** với thư viện chỉ hỗ trợ Chrome CDP — cần adapter chuyển giao thức. **v2.1:** MXH đã bỏ; Camoufox chỉ còn phục vụ ca khó/anti-bot trên web.

**AC:** Adapter Camoufox khai capability đúng; kết nối được qua Gateway.

#### MVP-24 — Session persistence + file lock profile

`Story` · `Owner: A · Hạ tầng browser` · `Est: 2 pd` · `Dep: MVP-23`

**Description:** Đồng bộ User Data Directory, cookie/token, LocalStorage/IndexedDB, **seed và timezone** gắn với IP dân cư cố định (IP do MVP-25 cấp). File lock (`fcntl.flock`) trên thư mục profile đảm bảo tại một thời điểm chỉ 1 trình duyệt mở một profile — đủ cho 2–3 trình duyệt chạy song song, không cần Redis. **v1.8 bổ sung** mô hình dữ liệu profile (`profile_id`, `account`, `proxy_id`, `fingerprint_seed`, geo/timezone/language, `storage_refs`, `health_score`, `lock_owner`) và kiến trúc **Tiered Hydration**: Hot Context cho web đặt bàn thường (storageState JSON mã hóa AES-GCM trong SQLite); ~~Heavy Profile cho MXH Facebook/Zalo trên Camoufox~~ **đã bỏ ở v2.1**. **v2.1:** bỏ MVP-74/75; IP do MVP-25 cấp trực tiếp.

**AC:** Mở lại profile không bị đăng xuất, seed và timezone nạp đúng; hai tiến trình tranh cùng profile thì một bị chặn. Đọc thẳng database không thấy cookie/token thô (đã mã hóa AES-GCM); log không chứa secret; lượt chạy sau nhận đủ cookie vừa write-back ở lượt trước.

#### MVP-25 — Tích hợp proxy dân cư

`Story` · `Owner: A · Hạ tầng browser` · `Est: 2 pd` · `Dep: MVP-24`

**Description:** Quản lý pool proxy dân cư/4G, xác thực, rotation, **giới hạn số phiên trên mỗi IP**, và **log IP dùng cho từng task**. Timezone của profile phải khớp IP; **WebRTC không được lộ IP thật**. Đây là điều kiện để chạy được thật trên web có anti-bot. ~~MVP-75 lo phần phân bổ IP cố định cho từng profile;~~ task này lo phần tích hợp và kiểm soát. **v1.8 bổ sung:** bộ tham số `max_sessions_per_ip`, `cooldown`, `rotation_threshold` là **cấu hình động**, không hard-code; số thật lấy từ MVP-62 (kiểm thử anti-bot). **v2.1:** MVP-75 đã hủy; task này tự gán IP cố định cho profile.

**AC:** Cấp 3 chạy được trên web có anti-bot; mỗi task có bản ghi IP tương ứng; test WebRTC không lộ IP thật; vượt số phiên cho phép trên một IP thì bị chặn.

#### MVP-26 — Đo RAM/CPU/cold-start hạ tầng

`Task` · `Owner: A · Hạ tầng browser` · `Est: 1 pd` · `Dep: MVP-22, MVP-23`

**Description:** Đo bằng `smem -c pss`, `htop`, `psutil` ở mức 1 phiên và 3–5 phiên song song (trần của MVP nhanh), gộp cả cold-start sandbox. **Lấy Chrome thường làm mốc so sánh.** Chỉ còn 2 engine sau khi bỏ Lightpanda ở v1.9. Số đo phải là số thật, không ước lượng. Việc chốt trần phiên thực tế của máy là của MVP-63.

**AC:** Bảng RAM/phiên và cold-start sandbox cho cả 2 engine và Chrome thường làm mốc, ghi rõ cấu hình máy đo.

#### MVP-27 — Live View HITL mức tối giản

`Story` · `Owner: D · Browser control` · `Est: 3 pd` · `Dep: MVP-22`

**Description:** Dùng Live View có sẵn của Steel nếu chạy được; nếu không thì chụp màn hình định kỳ (1–2 ảnh/giây) đẩy lên web để khách tự nhập OTP/quét QR cọc. Không dựng noVNC/KasmVNC trong MVP nhanh.

**AC:** Khách nhập được OTP qua màn hình này; đo được độ trễ hiển thị.

#### MVP-28 — Live View UI cho khách

`Story` · `Owner: D · Browser control` · `Est: 1,5 pd` · `Dep: MVP-27`

**Description:** Giao diện Live View phía khách: hiển thị màn hình phiên đang chạy để khách nhập OTP/quét QR cọc, kèm nút dừng/tiếp tục. MVP-27 dựng Live View mức tối giản; task này bổ sung lớp UI khách dùng được, tách khỏi màn hình kỹ thuật.

**AC:** Khách mở được Live View trên trình duyệt, nhập OTP xong phiên chạy tiếp; độ trễ hiển thị dưới 200 ms theo mục tiêu của tài liệu Tầng 2; không lộ thông tin kỹ thuật hay profile.

## EPIC-3 — Tầng 3 — Điều khiển Browser (thác đổ 4 cấp)

*Cấp 1 API, Cấp 2 Playwright, Cấp 3 Stagehand, Cấp 4 vision.*

**EPIC-3** Tầng 3 — Điều khiển Browser — Owner: D · 9 task

#### MVP-30 — Cấp 1 — Direct API Replay

`Story` · `Owner: D · Browser control` · `Est: 2 pd` · `Dep: MVP-02`

**Description:** Mở phiên lấy cookie/token hợp lệ rồi bắn thẳng `fetch()` đặt bàn, không tải giao diện. Đọc API Template từ Registry. **v1.9:** sau khi bỏ Lightpanda, Cấp 1 chạy trên Chromium/Patchright thay vì engine siêu nhẹ — cold-start và RAM tăng, mục tiêu 1–2 giây phải đo lại chứ không giữ nguyên giả định.

**AC:** $0 token; ghi nhận rõ khi bị chặn bởi biometric telemetry/nonce/SSR; thời gian chạy thực tế trên Chromium/Patchright được đo và ghi vào bảng benchmark, không dùng lại con số 1–2 giây của Lightpanda.

#### MVP-31 — Cấp 2 — Playwright Workflow tham số hóa

`Story` · `Owner: D · Browser control` · `Est: 2 pd` · `Dep: MVP-30`

**Description:** Chạy kịch bản selector với biến `{{date}}`, `{{time}}`, `{{party_size}}`, `{{phone}}`. Đây là xương sống thực thi chính.

**AC:** Pass trên nhóm web chuỗi lớn; 4–6 giây, $0 token.

#### MVP-32 — Cấp 3 — Stagehand (AI khám phá DOM/A11y Tree)

`Story` · `Owner: D · Browser control` · `Est: 3 pd` · `Dep: MVP-31, MVP-23`

**Description:** Dùng `act()`, `extract()`, `observe()` đọc DOM rút gọn + Accessibility Tree để tự tìm nút đặt bàn, tắt popup, thao tác Datepicker. Ghi lại selector AI tìm được để đẩy lên Cấp 2.

**AC:** Chạy được trên web độc lập; đo token/bước và latency/bước.

#### MVP-33 — Cấp 4 — Browser Use + vision API

`Story` · `Owner: D · Browser control` · `Est: 3 pd` · `Dep: MVP-22`

**Description:** Chế độ nhìn ảnh chụp màn hình thuần cho giao diện mù DOM (`<canvas>`, SVG, DOM làm rối). **Chạy bằng API vision multimodal, không cần GPU rời** — đây là điểm đã chốt ở tech stack v1.2, khác bản quyết định v1.1.

**AC:** Click được trên sơ đồ bàn vẽ canvas; đo token ảnh + latency từng bước.

#### MVP-34 — Hot-Swap Fallback không gián đoạn

`Story` · `Owner: D · Browser control` · `Est: 2 pd` · `Dep: MVP-30 đến MVP-33`

**Description:** Khi cấp trên lỗi giữa task, **không tắt trình duyệt làm lại từ đầu** — giữ nguyên trang ở bước hiện tại và trao quyền cho cấp dưới, xong bước đó trả quyền về.

**AC:** Kịch bản gắn popup giữa luồng Cấp 2 sang Cấp 3 chạy tiếp không mất trạng thái.

#### MVP-35 — Chuẩn hóa "cách chờ xong"

`Task` · `Owner: D · Browser control` · `Est: 1 pd` · `Dep: MVP-31, MVP-32`

**Description:** Mỗi engine có kiểu chờ khác nhau (network idle / DOM stable / pixel stable). Không chuẩn hóa thì latency đo được là vô nghĩa.

**AC:** 2 driver dùng chung một định nghĩa latency.

#### MVP-36 — CDP Network Sniffer (seam tự học)

`Task` · `Owner: D · Browser control` · `Est: 1 pd` · `Dep: MVP-32`

**Description:** Listener bắt request XHR/Fetch lúc bấm "Xác nhận đặt bàn", lưu thô để sau này LLM dịch ngược thành API Template. Trong MVP chỉ ghi, chưa biên dịch.

**AC:** Bắt được payload của ít nhất 1 site; dữ liệu đổ đúng chỗ chờ trong Registry.

#### MVP-37 — ~~Luồng đặt bàn qua MXH (Fanpage, Zalo OA, Instagram DM)~~ **ĐÃ HỦY 2026-11-18**

`Story` · `Owner: D · Browser control` · `Est: ~~3~~ 0 pd` · `Dep: —`

> 🚫 **Task này đã bị hủy theo quyết định chính thức ngày 2026-11-18: bỏ kênh MXH, chỉ làm web đặt bàn.**
> Xem [`docs/decision-drop-social-channels.md`](docs/decision-drop-social-channels.md). Mô tả dưới đây giữ làm lịch sử.

**Description:** Luồng điều khiển riêng cho kênh MXH: mở phiên bằng profile MXH (MVP-74) và IP cố định (MVP-75), gửi tin nhắn đặt bàn qua Fanpage, Zalo OA và Instagram DM, chờ nhà hàng trả lời rồi chốt. Khác luồng web ở chỗ không có form/selector cố định mà phụ thuộc hội thoại, và thời gian chờ 15–30 phút nên phiên phải ngủ đông qua Checkpointer (MVP-12) thay vì giữ trình duyệt mở.

**AC:** ~~Đặt được một bàn qua Fanpage, một qua Zalo OA và một qua Instagram DM; phiên ngủ đông trong lúc chờ rồi khôi phục đúng bước; đo được latency và tỷ lệ nhà hàng phản hồi.~~

#### MVP-38 — Success/Failure Detector & đường thoát khi 4 cấp fail

`Task` · `Owner: D · Browser control` · `Est: 1,5 pd` · `Dep: MVP-35, MVP-82`

**Description:** Bộ nhận diện tự động đặt bàn thành công hay thất bại từ artifact (ảnh, HAR, HTML) thay vì để người chấm tay, và định nghĩa đường thoát rõ ràng khi cả 4 cấp đều fail: trả lỗi có phân loại, đẩy sang Live View cho khách, không treo phiên.

**AC:** Phân loại đúng pass/fail trên bộ test; khi 4 cấp fail, phiên kết thúc có mã lỗi và không rò rỉ tài nguyên.

## EPIC-4 — Tầng 4 — Runtime Sandbox cô lập

*Bảo mật, chống SSRF, vòng đời phiên và đóng băng bộ nhớ.*

**EPIC-4** Tầng 4 — Runtime Sandbox cô lập — Owner: B · 5 task

#### MVP-40 — Sandbox cô lập trên Docker Rootless

`Story` · `Owner: B · Hạ tầng sandbox` · `Est: 2 pd` · `Dep: MVP-20`

**Description:** Mỗi phiên đặt bàn chạy trong container sạch. Ghi nhận rõ đánh đổi: Docker chia sẻ kernel với máy chủ (cô lập thấp nhất), nên bắt buộc bù bằng tường lửa và lifecycle.

**AC:** Phiên chạy độc lập; đo cold-start container.

#### MVP-41 — Chặn SSRF — Zero-Egress Internal Network

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1 pd` · `Dep: MVP-40`

**Description:** Tường lửa sandbox chặn tuyệt đối truy cập vào `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254` để trang web độc hại không tấn công mạng nội bộ.

**AC:** Test từ trong sandbox gọi các dải trên đều bị chặn.

#### MVP-42 — Ephemeral lifecycle

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1 pd` · `Dep: MVP-40`

**Description:** Container/MicroVM tự hủy ngay sau khi hoàn tất hoặc ngay sau khi chuyển sang ngủ đông, để không rò rỉ dữ liệu giữa khách A và khách B.

**AC:** Không còn tiến trình treo sau phiên; không tái sử dụng filesystem giữa hai phiên.

#### MVP-45 — Seccomp & hardening container

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1 pd` · `Dep: MVP-40`

**Description:** Siết bảo mật container sandbox: seccomp profile giới hạn syscall, bỏ capability thừa, chạy non-root, read-only root filesystem. Bù cho việc Docker chia sẻ kernel với máy chủ.

**AC:** Container chạy với seccomp profile và không có capability thừa; syscall ngoài danh sách bị chặn.

#### MVP-46 — Giới hạn tài nguyên per-container (cgroups)

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1 pd` · `Dep: MVP-40`

**Description:** Đặt trần RAM/CPU/PID cho từng container bằng cgroups để một phiên nặng không kéo sập cả máy 16GB, và để trần 3–5 sandbox là trần thật chứ không chỉ là quy ước.

**AC:** Container vượt trần RAM/CPU bị giới hạn chứ không OOM cả host; số PID bị chặn đúng mức.

## EPIC-5 — Dữ liệu & Test case

*Chốt site, ground truth, kịch bản mẫu — điều kiện để so sánh công bằng.*

**EPIC-5** Dữ liệu & Test case — Owner: E · 4 task

#### MVP-50 — Chốt 10–12 website mục tiêu + nhãn A/B

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1 pd` · `Dep: —`

**Description:** Chia 2 cấp độ nghiệp vụ web: chuỗi lớn (PasGo, TableCheck, Golden Gate...) và web nhà hàng độc lập. Loại A = đã biết DOM; Loại B = mới tinh. **Giữ riêng 2–3 site Loại B không chạy trong 15 ngày làm quỹ cold.** **v2.1:** bỏ kênh MXH — 3 site MXH cũ thay bằng 3 site web Loại B (Saigon Princess, Bình Quới, White Place).

**AC:** Danh sách khóa từ Ngày 1, không ai chạy thử trước trên máy benchmark.

#### MVP-51 — Ground truth pass/fail cho từng site

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-50`

**Description:** Xác định thế nào là "đặt bàn thành công" cho từng site, làm mốc chấm success rate và tỷ lệ điền sai dữ liệu.

**AC:** Mỗi site có tiêu chí pass/fail rõ, kiểm chứng được bằng tay.

#### MVP-52 — Kịch bản đặt bàn mẫu dạng JSON

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1 pd` · `Dep: MVP-01`

**Description:** Bộ input chuẩn (ngày, giờ, số người, SĐT) dùng chung cho mọi case, để so sánh giữa các công nghệ là so sánh trên cùng đầu vào.

**AC:** Ít nhất 3 kịch bản mẫu chạy pass liên tục.

#### MVP-53 — Tài khoản test + kênh nhận OTP

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1 pd` · `Dep: MVP-50`

**Description:** Chuẩn bị tài khoản cho site cần đăng nhập và số điện thoại/kênh nhận OTP cho luồng HITL.

**AC:** Đăng nhập được trên site cần auth; OTP nhận được trong lúc test.

## EPIC-6 — Benchmark, Anti-bot & Báo cáo

*Đo 4 trục, chấm điểm triển khai, tổng hợp báo cáo cho SA.*

**EPIC-6** Benchmark, Anti-bot & Báo cáo — Owner: E · 5 task

#### MVP-60 — Thang điểm độ phức tạp triển khai (9 tiêu chí / 45 điểm)

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 1,5 pd` · `Dep: MVP-02`

**Description:** Chấm mỗi case theo 9 tiêu chí thang 1–5: số capability phải workaround, số protocol phải dịch, dependency ngoài, thời gian dựng/test/debug (tách riêng để không đếm trùng), trình độ yêu cầu, LOC adapter, độ ổn định vận hành. **Chấm ngay khi viết adapter**, không chấm sau bằng cảm tính.

**AC:** Mỗi adapter có bảng điểm kèm bằng chứng; có ít nhất 1 case được người khác dựng lại từ zero chỉ dựa vào README.

#### MVP-61 — Benchmark 4 trục

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 3 pd` · `Dep: MVP-30 đến MVP-42`

**Description:** Chạy 10–12 site × case × 10 lần/ô + warm-up bị loại. Báo **p50 và p95**, không báo trung bình đơn thuần. Loại B đo **cold và warm thành hai cột riêng**.

**AC:** Không ô nào thiếu; $/task tính trên **task thành công**, không phải task chạy.

#### MVP-62 — Kiểm thử anti-bot

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-23`

**Description:** Chấm điểm vượt anti-bot trên `browserscan.net`, `creepjs.com`, Cloudflare Turnstile. Đây là thước đo của trục độ chính xác, không phải công nghệ cần cài.

**AC:** Có Trust Score cho từng engine; ghi rõ engine nào bị lộ headless.

#### MVP-63 — Test tải 3–5 phiên song song

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1,5 pd` · `Dep: MVP-26`

**Description:** Đo peak RAM và độ ổn định khi chạy đồng thời. Trần thực tế phụ thuộc RAM máy — phải đo thật, không giả định.

**AC:** Bảng peak RAM ở 1 / 3 / 5 phiên; ghi rõ trần thực tế của máy đo.

#### MVP-64 — Báo cáo benchmark + đề xuất tech stack

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-61, MVP-62, MVP-63`

**Description:** Làm sạch dữ liệu, tính p50/p95, $/task thành công, đối chiếu với ước tính lý thuyết trong tài liệu kiến trúc. Báo **4 cột riêng**, không gộp thành một điểm tổng trừ khi công bố rõ trọng số.

**AC:** Báo cáo có 4 bảng + khuyến nghị + danh sách điều chưa kiểm chứng.

## EPIC-7 — Cấp phát & Điều phối tài nguyên

*Ai tạo tài nguyên, ai cấp sandbox, ai giữ trần phiên — lớp này đứng dưới cả 4 tầng.*

**EPIC-7** Cấp phát & Điều phối tài nguyên — Owner: B (+ A) · 6 task

#### MVP-70 — Cấp phát hạ tầng nền & tài khoản cloud

`Task` · `Owner: B · Hạ tầng sandbox` · `Est: 1,5 pd` · `Dep: —`

**Description:** Ngày 1 của kế hoạch 7 ngày: khởi tạo VPS, cấu hình Docker Rootless, đăng ký tài khoản cloud nếu dùng nhánh SaaS (Browserbase, E2B, Modal). Gom toàn bộ khóa và endpoint vào một tệp `.env` duy nhất, không hard-code trong code.

**AC:** VPS truy cập được, Docker Rootless chạy; `.env` có đủ endpoint và khóa; không có khóa nào nằm trong repo.

#### MVP-71 — Sandbox Allocator đơn giản (trần 3–5 phiên)

`Story` · `Owner: B · Hạ tầng sandbox` · `Est: 3 pd` · `Dep: MVP-40, MVP-70`

**Description:** Bộ cấp phát nhận yêu cầu phiên và trả về một container sạch, tạo theo yêu cầu, trần cứng 3–5 phiên đồng thời. Không làm warm pool trong MVP nhanh — cold-start đo trực tiếp. Đây là thứ MVP-40 (sandbox cô lập) còn thiếu: MVP-40 dựng *một* sandbox, task này dựng *cơ chế cấp phát* sandbox.

**AC:** Cấp phát trả phiên sạch trong thời gian đo được; không cấp trùng một sandbox cho hai phiên; vượt trần 5 phiên thì từ chối rõ ràng thay vì OOM.

#### MVP-73 — Session Lifecycle Manager

`Story` · `Owner: B · Hạ tầng sandbox` · `Est: 2 pd` · `Dep: MVP-71`

**Description:** Quản lý vòng đời một phiên: tạo, chạy, ngủ đông, đánh thức, thu hồi. Gắn `trace_id` ngay khi tạo để mọi tầng ghi log về cùng một phiên. Thu hồi theo TTL để không rò rỉ tài nguyên.

**AC:** Không còn phiên treo sau khi chạy xong bộ test; mỗi phiên có đúng một `trace_id` xuyên suốt.

#### MVP-74 — ~~Profile Vault & cấp phát profile MXH~~ **ĐÃ HỦY 2026-11-18**

`Story` · `Owner: A · Hạ tầng browser` · `Est: ~~2~~ 0 pd` · `Dep: —`

> 🚫 **Task này đã bị hủy theo quyết định chính thức ngày 2026-11-18: bỏ kênh MXH, chỉ làm web đặt bàn.**
> Xem [`docs/decision-drop-social-channels.md`](docs/decision-drop-social-channels.md). Mô tả dưới đây giữ làm lịch sử.

**Description:** Kho lưu profile trình duyệt (Profile Vault) và bộ cấp phát gán profile cho phiên, kèm file lock để một profile chỉ có một trình duyệt mở tại một thời điểm. MVP-24 lo phần *lưu* phiên; task này lo phần *cấp* phiên.

**AC:** ~~Cấp profile không trùng; hai yêu cầu cùng profile thì một bị chặn và ghi log.~~

#### MVP-75 — ~~Cấp phát proxy & gán IP cố định~~ **ĐÃ HỦY 2026-11-18**

`Task` · `Owner: A · Hạ tầng browser` · `Est: ~~1,5~~ 0 pd` · `Dep: —`

> 🚫 **Task này đã bị hủy theo quyết định chính thức ngày 2026-11-18: bỏ kênh MXH, chỉ làm web đặt bàn.**
> Xem [`docs/decision-drop-social-channels.md`](docs/decision-drop-social-channels.md). Mô tả dưới đây giữ làm lịch sử.

**Description:** Bộ cấp phát IP từ pool proxy dân cư, gán cố định IP cho từng profile và ghi lại IP đã dùng cho từng task. MVP-25 lo phần *tích hợp* proxy; task này lo phần *phân bổ* IP.

**AC:** ~~Mỗi phiên MXH có IP riêng, không trùng giữa hai phiên song song; bảng ánh xạ profile ↔ IP ↔ task xuất được.~~

#### MVP-76 — Browser Allocator (trần 2–3 trình duyệt)

`Story` · `Owner: A · Hạ tầng browser` · `Est: 1,5 pd` · `Dep: MVP-20, MVP-22, MVP-23`

**Description:** Bộ cấp phát trình duyệt giữ trần cứng 2–3 trình duyệt đồng thời trên máy 16GB, chọn engine theo capability và trả phiên sạch; kèm health check engine giữa phiên để phát hiện engine treo hoặc bị chặn. MVP-71 cấp sandbox; task này cấp trình duyệt bên trong sandbox.

**AC:** Không vượt quá 3 trình duyệt cùng lúc; engine treo giữa phiên bị phát hiện và thay thế; không cấp trùng một trình duyệt cho hai phiên.

## EPIC-8 — Lưu trữ & Dữ liệu

*Đặt bàn, người dùng, artifact, Registry — không có lớp này thì mọi thứ chỉ nằm trong RAM.*

**EPIC-8** Lưu trữ & Dữ liệu — Owner: E · 4 task

#### MVP-80 — Schema SQLite + migration

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-20`

**Description:** Thiết kế bảng cho `booking` (yêu cầu đặt bàn, trạng thái, kết quả), `session` (phiên, trace_id, cấp đã dùng), `registry` (API Template, Playwright Workflow) và `artifact_index`. **v2.0:** database là SQLite (`data/app.db`, WAL mode) — ranh giới module bằng **tiền tố bảng** (`booking_*`, `agent_*`, `bc_*`, `sandbox_*`, `profile_*`, `artifact_*`, `telemetry_*`), không có schema. Migration bằng Alembic + SQLite dialect, dùng **table-rebuild pattern** cho thay đổi cột. Có migration chạy lại được từ máy trắng.

**AC:** Migration chạy sạch trên database trống; có index cho truy vấn theo `trace_id` và theo site; PRAGMA `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` được set khi mở connection.

#### MVP-82 — Artifact Store bằng thư mục local: ảnh, HAR, HTML snapshot

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-80`

**Description:** Lưu mọi bằng chứng của một phiên vào thư mục `artifacts/<trace_id>/` trên đĩa: ảnh chụp màn hình từng bước, HAR/network log, HTML snapshot. Không dựng MinIO trong MVP nhanh — đĩa local đủ cho vài trăm phiên. Mỗi artifact có `artifact_id` và trỏ về `trace_id` — đây chính là trường `artifact_id` đã chừa trong telemetry schema từ MVP-01.

**AC:** Mọi artifact truy được về đúng phiên; đo được dung lượng trung bình mỗi phiên để tính chi phí lưu trữ.

#### MVP-83 — Dữ liệu người dùng & PII

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-80`

**Description:** Lưu thông tin khách (tên, SĐT, số người) ở dạng mã hóa khi nghỉ, che bớt khi hiển thị và trong log, đặt thời hạn xóa. Không ghi SĐT thô vào log telemetry hay tên tệp artifact.

**AC:** Truy vấn thẳng database không đọc được SĐT thô; log không chứa PII; job xóa theo TTL chạy được.

#### MVP-84 — Registry API Template & Playwright Workflow

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-80, MVP-04`

**Description:** Hai bảng Registry đã chừa seam ở MVP-04 nay có API đọc/ghi thật: lưu template, đánh version, đánh dấu template hỏng khi site đổi giao diện, và rollback về bản trước.

**AC:** Master Router đọc được Registry; một template hỏng bị đánh dấu và tự rơi xuống cấp dưới thay vì chạy sai.

## EPIC-9 — Monitor & Thu thập dữ liệu benchmark theo tầng

*Chỉ còn hai task: chuẩn trace_id và gắn điểm đo. Số liệu ghi ra tệp CSV/JSONL, không dựng store chuỗi thời gian.*

**EPIC-9** Monitor & Thu thập dữ liệu benchmark theo tầng — Owner: E · 2 task

> ℹ️ **Quan hệ với MVP-01 và MVP-03**
>
> MVP-01 đã định nghĩa *schema* telemetry và MVP-03 đã dựng *runner ghi log*. EPIC-9 là phần còn thiếu:
> **gắn điểm đo vào từng tầng** (sandbox, hạ tầng browser, điều khiển, agent), ghi ra cùng một tệp CSV/JSONL.
> Không có nó, mỗi tầng ghi một kiểu và không ghép được thành một dòng thời gian của cùng một phiên.

#### MVP-90 — Chuẩn trace_id xuyên tầng

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1 pd` · `Dep: MVP-01`

**Description:** Một `trace_id` sinh ra ở tầng agent, truyền xuống sandbox, hạ tầng browser và điều khiển qua header/context. Mọi log và artifact đều mang nó.

**AC:** Từ một `trace_id` lấy ra được toàn bộ log của cả 4 tầng theo đúng thứ tự thời gian.

#### MVP-91 — Instrumentation từng tầng

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2,5 pd` · `Dep: MVP-90`

**Description:** Gắn điểm đo tại 4 chỗ: sandbox (cold-start, RAM), hạ tầng browser (RAM/phiên, RTT), điều khiển (latency/bước, token/bước, cấp đã dùng) và agent (thời gian toàn trình, số lần chuyển cấp). Dùng đồng hồ monotonic như MVP-03.

**AC:** Mỗi tầng phát metric đúng schema MVP-01; không tầng nào ghi trường tự phát ngoài schema.

## EPIC-10 — Benchmark Harness & Báo cáo cuối

*Lớp cuối cùng: chạy ma trận, đóng băng dữ liệu, tính số, xuất báo cáo tái lập được.*

**EPIC-10** Benchmark Harness & Báo cáo cuối — Owner: E · 5 task

#### MVP-100 — Matrix runner

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 3 pd` · `Dep: MVP-61, MVP-71`

**Description:** Chạy tự động ma trận site × công nghệ × case × số lần lặp, có warm-up bị loại khỏi kết quả, có resume khi đứt giữa chừng và không chạy trùng một ô đã xong. MVP-61 là nội dung đo; task này là cỗ máy chạy.

**AC:** Chạy lại từ chỗ đứt mà không nhân đôi dữ liệu; mỗi ô ghi rõ số lần lặp thực tế.

#### MVP-101 — Đóng băng dataset & ground truth

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1,5 pd` · `Dep: MVP-50, MVP-51`

**Description:** Đóng băng danh sách site, kịch bản JSON và tiêu chí pass/fail thành một phiên bản có mã hash. Không ai được sửa giữa đợt đo; muốn đổi thì tạo phiên bản mới và ghi rõ.

**AC:** Dataset có hash và ngày đóng băng; báo cáo trích đúng hash đã dùng.

#### MVP-102 — Statistics engine

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-100`

**Description:** Tính từ log thô, không nhập tay: p50/p95, success rate, pass@1, số lần retry, tỷ lệ điền sai dữ liệu và $/task thành công. Loại B tách cold và warm thành hai cột.

**AC:** Mọi con số trong báo cáo sinh ra từ script, chạy lại cho ra đúng kết quả cũ.

#### MVP-103 — Cost model

`Task` · `Owner: E · Benchmark & dữ liệu` · `Est: 1,5 pd` · `Dep: MVP-102`

**Description:** Cộng đủ bốn loại chi phí: compute (VPS/cloud), token LLM, proxy dân cư và lưu trữ artifact. Quy ra $/đơn đặt bàn thành công cho từng tổ hợp công nghệ.

**AC:** Bảng chi phí tách rõ từng khoản; nêu rõ khoản nào là ước tính và khoản nào là số đo thật.

#### MVP-104 — Report generator + phụ lục tái lập

`Story` · `Owner: E · Benchmark & dữ liệu` · `Est: 2 pd` · `Dep: MVP-102, MVP-103`

**Description:** Sinh báo cáo cho SA từ dữ liệu đã tính, kèm phụ lục tái lập: hash dataset, phiên bản code, cấu hình máy đo, script chạy lại và danh sách điều chưa kiểm chứng. MVP-64 là nội dung báo cáo; task này là bộ sinh tự động.

**AC:** Người khác chạy lại script trên cùng dataset ra cùng bảng số; báo cáo có mục "điều chưa kiểm chứng".

## EPIC-11 — API Layer (v2.0)

*Cổng giao tiếp FE ↔ BE theo mục 7 của system design v2.1: REST, SSE, WebSocket, auth, rate limit, trace.*

**EPIC-11** API Layer — Owner: F · 4 task

> ℹ️ **Vì sao epic này tồn tại**
>
> Backlog v1.9 phủ đủ 4 tầng kỹ thuật nhưng **không có task nào** cho lớp API mà system design v2.1 mô tả ở mục 7 — 8 endpoint REST, SSE tiến trình, WebSocket Live View, auth, rate limit và trace middleware. Không có lớp này thì FE không có gì để gọi và demo chỉ chạy được bằng CLI.

#### MVP-110 — FastAPI skeleton + REST endpoints + error taxonomy

`Story` · `Owner: F · API & FE` · `Est: 3 pd` · `Dep: MVP-01, MVP-80`

**Description:** Dựng FastAPI app theo cấu trúc module của system design v2.1: `POST /v1/bookings`, `GET /v1/bookings/{id}`, `GET /v1/bookings`, `GET /v1/sites`, `GET /v1/health`, `GET /v1/benchmark/runs`. Mọi response có `trace_id`. Lỗi trả theo taxonomy thống nhất: `INPUT_INVALID`, `TIER_EXHAUSTED`, `HITL_REQUIRED`, `SANDBOX_UNAVAILABLE`, `PROFILE_LOCKED`, `SITE_BLOCKED`. FE không nhận thông tin kỹ thuật nội bộ (tên profile, fingerprint seed, proxy IP, đường dẫn artifact).

**AC:** 6 endpoint trả đúng schema; mọi response có `trace_id` đối chiếu được với telemetry; lỗi trả đúng mã taxonomy, không lộ stack trace hay thông tin nội bộ.

#### MVP-111 — SSE tiến trình + WebSocket Live View

`Story` · `Owner: F · API & FE` · `Est: 2 pd` · `Dep: MVP-110, MVP-07`

**Description:** Hai kênh streaming tách riêng: **SSE** `GET /v1/bookings/{id}/events` cho tiến trình từng bước, chuyển cấp, log trạng thái (một chiều, tự reconnect); **WebSocket** `/v1/bookings/{id}/liveview` cho luồng màn hình Live View khi khách tự nhập OTP (hai chiều). Tách hai kênh để lỗi Live View không làm đứt log tiến trình.

**AC:** SSE đẩy được sự kiện chuyển cấp và `HITL_REQUIRED`; WS truyền được khung hình Live View và nhận input OTP; ngắt WS không làm đứt SSE.

#### MVP-112 — Auth + rate limit + trace_id middleware

`Task` · `Owner: F · API & FE` · `Est: 2 pd` · `Dep: MVP-110, MVP-90`

**Description:** Ba middleware xuyên suốt: xác thực FE ↔ BE (JWT, session cookie hoặc API key nội bộ — chốt theo mục 12.7 của system design), rate limit theo client, và gắn `trace_id` vào mọi request/response để đối chiếu với telemetry.

**AC:** Request thiếu auth bị từ chối; vượt rate limit trả 429; `trace_id` sinh ở API truyền xuống được tới sandbox/browser qua context.

#### MVP-113 — Booking API: tạo/tra cứu/hủy/HITL + Idempotency-Key

`Story` · `Owner: F · API & FE` · `Est: 2 pd` · `Dep: MVP-110, MVP-39`

**Description:** Hoàn thiện vòng đời booking qua API: `POST /v1/bookings` nhận `Idempotency-Key`, gọi lại cùng key trả cùng kết quả và không tạo phiên mới; `POST /v1/bookings/{id}/cancel` idempotent; `POST /v1/bookings/{id}/hitl` nhận phản hồi HITL (OTP, xác nhận cọc) và đánh thức agent đúng `thread_id`.

**AC:** Gọi lại `POST /v1/bookings` cùng `Idempotency-Key` không tạo bản ghi thứ hai; hủy hai lần trả cùng kết quả; HITL đánh thức đúng phiên đang dừng.

## EPIC-12 — FE Web App (v2.0)

*Giao diện khách: đặt bàn, theo dõi tiến trình, Live View nhập OTP, lịch sử.*

**EPIC-12** FE Web App — Owner: F · 4 task

> ℹ️ **Vì sao epic này tồn tại**
>
> System design v2.1 mô tả FE web app ở mục 2 (đặt bàn · theo dõi tiến trình · Live View nhập OTP · lịch sử), nhưng backlog v1.9 chỉ có MVP-28 (Live View UI) — không có form đặt bàn, không có màn hình theo dõi, không có lịch sử. MVP-28 vẫn giữ nguyên và được MVP-122 tái sử dụng.

#### MVP-120 — FE khung web app + form đặt bàn

`Story` · `Owner: F · API & FE` · `Est: 3 pd` · `Dep: MVP-110`

**Description:** Khung web app (SPA) + form đặt bàn gọi `POST /v1/bookings`: ngày, giờ, số người, SĐT, chọn site. Hiển thị `booking_id` và `trace_id` sau khi tạo. Validate phía client khớp với Input Guardrails (MVP-11).

**AC:** Tạo được booking từ trình duyệt; lỗi validate hiển thị rõ theo taxonomy; không lộ thông tin kỹ thuật nội bộ.

#### MVP-121 — FE theo dõi tiến trình (SSE) + lịch sử

`Story` · `Owner: F · API & FE` · `Est: 2 pd` · `Dep: MVP-120, MVP-111`

**Description:** Màn hình theo dõi tiến trình một booking qua SSE: từng bước, cấp đang chạy, chuyển cấp, trạng thái HITL. Màn hình lịch sử gọi `GET /v1/bookings` với lọc theo trạng thái/ngày/site.

**AC:** Tiến trình cập nhật realtime không cần refresh; SSE tự reconnect khi mất kết nối; lịch sử lọc đúng.

#### MVP-122 — FE Live View nhập OTP (WS)

`Story` · `Owner: F · API & FE` · `Est: 1,5 pd` · `Dep: MVP-120, MVP-111, MVP-28`

**Description:** Nhúng Live View (MVP-28) vào web app qua WebSocket để khách tự nhập OTP/quét QR cọc khi nhận `HITL_REQUIRED`. Kèm nút dừng/tiếp tục.

**AC:** Khách nhập OTP xong phiên chạy tiếp; độ trễ hiển thị dưới 200 ms; không lộ thông tin kỹ thuật hay profile.

#### MVP-123 — FE polish: trạng thái lỗi, responsive, a11y

`Task` · `Owner: F · API & FE` · `Est: 0,5 pd` · `Dep: MVP-121, MVP-122`

**Description:** Hoàn thiện trải nghiệm: hiển thị đủ 6 mã lỗi taxonomy bằng tiếng Việt dễ hiểu, responsive trên mobile, kiểm tra a11y cơ bản.

**AC:** Cả 6 mã lỗi có thông điệp tiếng Việt; dùng được trên màn hình 375 px; không lỗi a11y mức nghiêm trọng.

## GATE — Bốn cổng kiểm tra

*Dùng làm Definition of Done theo mốc — không qua cổng thì không đi tiếp.*

| Cổng | Mốc | Điều kiện qua |
|---|---|---|
| **Cổng 1** | Hết Ngày 2 | Spec Gateway đóng băng, đã kiểm chứng bằng 2 công nghệ khác nhân |
| **Cổng 2** | Hết Ngày 6 | 2 endpoint hạ tầng + 2 driver + sandbox chạy độc lập, có số đo thô |
| **Cổng 3** | Hết Ngày 10 | 4 cấp sẵn sàng; Snapshot/Restore và Live View chạy được (hoặc đã kích hoạt dự phòng) |
| **Cổng 4** | Hết Ngày 12 | End-to-end ổn định, không còn lỗi tích hợp mở; API + FE tối thiểu chạy được luồng đặt bàn từ trình duyệt (v2.0) |

## OPEN — Điểm cần xác nhận trước khi đưa vào Jira

*Hai câu hỏi chặn, nên chốt trước buổi kickoff.*

> ⚠️ **1. Cấp 4 dùng GPU hay API vision?**
>
> Backlog này viết theo **tech stack v1.2** (API vision, không cần GPU). Tài liệu quyết định
> **v1.1** vẫn ghi OmniParser V2 + GPU — nếu chọn hướng GPU thì **MVP-33** phải đổi thành
> task xin cấp GPU, và rủi ro "tách Cấp 4 khỏi MVP" quay lại.

> ℹ️ **2. Estimate có cần chốt cứng không?**
>
> Các con số person-days trong tài liệu này là **ước lượng đề xuất**, không phải số đã có trong
> tài liệu gốc. Cần team rà lại trước khi gán vào sprint.

> ⚠️ **3. Hổng còn lại sau v1.5 — chưa task nào phủ**
>
> Rà 9 task mới với bốn tài liệu tầng, còn bốn điểm chưa có task:
> **(1)** phát hiện IP bị ban và ~~nick MXH~~ **profile web** bị checkpoint giữa phiên — MVP-76 mới có health check engine, chưa có tín hiệu này;
> **(2)** đường đưa artifact từ trong container sandbox ra host — MVP-82 mới lo kho artifact phía host;
> **(3)** chuẩn hóa ngôn ngữ tiếng Việt cho đầu vào tự nhiên (dấu, viết tắt, tên quán) — hiện MVP chỉ nhận JSON cố định;
> **(4)** CAPTCHA — đã quyết gộp vào MVP-07 nhưng mô tả MVP-07 chưa ghi, cần bổ sung khi chốt. **v1.8:** hổng (1) đã có task phủ là **MVP-29** (health_score, cờ checkpoint, degraded); ba hổng còn lại vẫn chưa có task. **v2.0:** vẫn còn ba hổng (2), (3), (4) — chưa thành task, cần bổ sung nếu muốn đóng trước Cổng 4.

> ⚠️ **4. v1.8 — Bốn điểm phải chốt với thành viên phụ trách agent**
>
> **(1) Cơ chế LongTaskRunner của MVP-16:** ~~thuần PostgreSQL `SKIP LOCKED` + bảng `scheduled_wakeups` (0 service mới), hay bật thêm Inngest Dev Server~~ → **v2.0 đã chốt:** SQLite claim pattern trong `BEGIN IMMEDIATE` + bảng `scheduled_wakeups`. Không thêm service nào.
>
> **(2) Ranh giới suy luận web mới giữa C và D:** khi Cấp 3 gặp form mới, D trả `a11y_tree_snapshot` về cho C (MVP-15 BAML) suy luận và kiểm Safety Gate, hay D tự xử lý một phần bên trong Tầng 3. Đề xuất: D trả snapshot, C quyết định — giữ nguyên nguyên tắc D không tự quyết định trượt cấp.
>
> **(3) Cách truyền Heavy Profile với A và E:** mount trực tiếp thư mục `profile_id` theo đường dẫn trong ContextLease, hay tải/giải nén `.tar.zst` qua HTTP nội bộ. Đề xuất mount trực tiếp vì toàn bộ hệ thống chạy trên một máy WSL2.
>
> **(4) Bộ tham số IP-Session:** `max_sessions_per_ip`, `cooldown`, `rotation_threshold` để trống dưới dạng cấu hình động và điền số thật sau MVP-62 — đồng ý, nhưng phải ghi rõ trong báo cáo là chưa có ngưỡng thực nghiệm.

> 🚫 **5. v1.8 — Những đề xuất KHÔNG nhận, và vì sao**
>
> **Thay fcntl.flock bằng PostgreSQL Lease Lock (MVP-24L):** không nhận. Quyết định bỏ Redis và dùng file lock đã chốt từ v1.2; file lock đúng khi toàn bộ hệ thống chạy trên một máy, và đánh đổi này đã ghi rõ trong tài liệu. Nếu sau này tách nhiều máy thì mới quay lại lock phân tán. Phần *IP-Session Quota Enforcer* của MVP-24L thì nhận, đã gộp vào MVP-25.
>
> **Tách MVP-24 thành 24C/24L:** không nhận. MVP-24 đã thuộc A; tách ra là đổi owner và đổi số hiệu. Nội dung vault, write-back và Tiered Hydration đã gộp vào MVP-24; quota vào MVP-25.
>
> **Inngest Dev Server / Temporal:** không đưa vào MVP. Tài liệu Tầng 1 ghi Temporal/Inngest là lựa chọn durable execution, nhưng thêm service là thêm thứ phải cài trên máy công ty; MVP dùng SQLite, giữ interface để nâng cấp sau.
>
> **Hạ estimate của task cũ:** không nhận. MVP-01 1,0 → 1,5; MVP-03 1,5 → 1,5; MVP-06 1,5 → 1,5; MVP-11 1 → 1; MVP-12 2 → 2; MVP-13 1 → 1; MVP-39 1 → 1. Giảm estimate để vừa trần 15 ngày là làm sai bản chất vấn đề — C đang quá tải thật, phải xử lý bằng cách tách người hoặc cắt phạm vi.
>
> **Chuyển MVP-05 và MVP-08 sang người khác:** không nhận. MVP-05 (khung báo cáo SA) và MVP-08 (đóng gói một lệnh) vẫn thuộc C theo phân công hiện tại; đổi owner phải do bạn quyết định, không phải tự đổi trong backlog.

> ✅ **6. v2.0 — Đồng bộ với system design v2.1 (SQLite)**
>
> **Đã sửa trong v2.0:** MVP-12 (`PostgresSaver` → `AsyncSqliteSaver`), MVP-16 (`SKIP LOCKED` → claim pattern `BEGIN IMMEDIATE`), MVP-20 (bỏ PostgreSQL khỏi WSL2), MVP-24 (storageState mã hóa trong SQLite), MVP-80 (Schema SQLite + Alembic SQLite dialect + tiền tố bảng), MVP-08 (bỏ service DB khỏi compose), bảng 00c (backup bằng `VACUUM INTO`).
>
> **Đã thêm:** EPIC-11 API Layer (MVP-110 → MVP-113, owner F) và EPIC-12 FE Web App (MVP-120 → MVP-123, owner F) — hai mảng system design v2.1 mô tả nhưng backlog v1.9 không có task nào.
>
> **Đã sửa lỗi đếm:** EPIC-1 header 8 → 9 task; bảng ưu tiên 32/34 → 35/39.
>
> **Còn treo (không chặn build):** supervisor (mục 12.2), Live View Steel vs screenshot (12.4), auth mode (12.7), chu kỳ backup (12.8) — chưa thành task, có thể bổ sung sau khi chốt.

> ✅ **Bước tiếp theo**
>
> Nếu cần import trực tiếp vào Jira, xuất thêm bản CSV với các cột:
> `Issue Type`, `Summary`, `Description`, `Assignee`,
> `Story Points`, `Labels`, `Epic Link`.

Backlog triển khai MVP Browser Agent Đặt bàn · v2.0 · 18/11/2026 · Người lập: Vũ Ngọc Hùng · 13 epic · 74 task · 4 cổng kiểm tra.
