# TÀI LIỆU SYSTEM DESIGN — v2.1
## Kiến trúc Modular Monolith cho Booking Agent · Database: SQLite

---

## 0. Thay đổi so với v2.0

| Hạng mục | v2.0 | v2.1 |
|---|---|---|
| Database | PostgreSQL (1 instance, nhiều schema) | **SQLite** (file nhúng, WAL mode) |
| Checkpointer LangGraph | `PostgresSaver` | **`AsyncSqliteSaver`** (`langgraph-checkpoint-sqlite`) |
| Durable Queue | PostgreSQL `SKIP LOCKED` | **Claim pattern trong `BEGIN IMMEDIATE`** (SQLite không có SKIP LOCKED) |
| Lease Lock TTL | Bảng lease trên PostgreSQL | Bảng lease trên SQLite + `fcntl.flock` cho khóa cứng |
| Ranh giới module | Schema riêng mỗi module | **Tiền tố bảng** mỗi module (SQLite không có schema) |
| Backup | `pg_dump` | **`VACUUM INTO`** — snapshot nguyên tử, không cần dừng hệ thống |
| Migration | Alembic + PostgreSQL dialect | Alembic + SQLite dialect, **table-rebuild pattern** |

**Lý do đổi:** SQLite là thư viện nhúng — không có tiến trình server riêng, không có cổng mạng, không có service phải cài, không có user/password phải quản. Trên một máy Windows 11 không được tự cài phần mềm, đây là lợi thế trực tiếp: bỏ được một service khỏi danh sách phải giám sát và một cổng khỏi danh sách phải mở.

---

## 1. Nguyên tắc thiết kế

1. Một tiến trình deploy, nhiều module có ranh giới cứng.
2. Giao tiếp giữa module là gọi hàm in-process qua interface (`Protocol`/ABC). Không HTTP nội bộ, không broker.
3. Mỗi module sở hữu tập bảng riêng; không module nào đọc thẳng bảng của module khác.
4. Ranh giới phải cắt được — tách service sau này chỉ thay adapter.
5. FE không biết gì về module nội bộ.
6. Không có state chia sẻ ngầm.
7. **Mới:** mọi ghi DB phải ngắn và có `busy_timeout`. SQLite chỉ cho **một writer tại một thời điểm** — đây là ràng buộc thiết kế, không phải chi tiết cài đặt.

---

## 2. Sơ đồ tổng thể

```text
┌──────────────────────────────────────────────────────────────┐
│  FE — Web app (trình duyệt)                                  │
│  Đặt bàn · theo dõi tiến trình · Live View nhập OTP · lịch sử │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS/JSON (REST) + SSE + WebSocket
                            ▼
╔══════════════════════════════════════════════════════════════╗
║  BACKEND SERVICE — 1 tiến trình, modular monolith            ║
║                                                              ║
║  ┌────────────────────────────────────────────────────────┐  ║
║  │  api  — FastAPI: REST, SSE, WS, auth, validate, limit  │  ║
║  └────────────────────────────────────────────────────────┘  ║
║                                                              ║
║  ┌───────────┬───────────┬────────────┬──────────────────┐   ║
║  │  booking  │   agent   │  browser_  │  browser_infra   │   ║
║  │           │ (LangGraph│  control   │  (CDP gateway,   │   ║
║  │           │  + 3 lớp  │  (4 cấp    │   Steel, Xvfb,   │   ║
║  │           │  guard)   │  thác đổ)  │   Camoufox)      │   ║
║  └───────────┴───────────┴────────────┴──────────────────┘   ║
║                                                              ║
║  ┌───────────┬───────────┬────────────┬──────────────────┐   ║
║  │  sandbox  │  profile  │  artifact  │   telemetry      │   ║
║  └───────────┴───────────┴────────────┴──────────────────┘   ║
║                                                              ║
║  ┌────────────────────────────────────────────────────────┐  ║
║  │  shared kernel — config, logging, clock, error taxonomy│  ║
║  └────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════╝
        │                    │                      │
        ▼                    ▼                      ▼
  ┌───────────────┐  ┌────────────────────┐  ┌──────────────────┐
  │ SQLite        │  │ Thư mục local      │  │ Tiến trình con   │
  │ data/app.db   │  │ profiles/ artifacts│  │ Xvfb + Chromium  │
  │ (+ WAL, -shm) │  │                    │  │ + Camoufox       │
  └───────────────┘  └────────────────────┘  └──────────────────┘
```

Trình duyệt và sandbox **vẫn là tiến trình/container riêng** — cần cô lập và an ninh. Cái gom là lớp điều khiển chúng. SQLite nằm trong tiến trình backend, không có cổng mạng nào.

---

## 3. Module & dữ liệu sở hữu

| Module | Trách nhiệm | Bảng sở hữu (tiền tố) |
|---|---|---|
| `api` | REST/SSE/WS, xác thực, validate, rate limit | — |
| `booking` | Vòng đời yêu cầu, máy trạng thái nghiệp vụ, idempotency, hủy | `booking_*` |
| `agent` | LangGraph, guardrails 3 lớp, Master Router, checkpointer | `agent_checkpoint*`, `agent_registry*` |
| `browser_control` | 4 cấp: API Replay, Playwright, Stagehand, vision | `bc_api_template`, `bc_playwright_workflow` |
| `browser_infra` | Gateway CDP, Steel, Xvfb, Camoufox, Live View | — |
| `sandbox` | Vòng đời container, allocator, health check, zero-egress | `sandbox_*` |
| `profile` | Profile Vault, lease, fingerprint seed, proxy | `profile_*`, `profile_lease` |
| `artifact` | Lưu file local, index tra cứu (FTS5) | `artifact_index`, `artifact_fts` |
| `telemetry` | Schema log, 4 trục metric, runner benchmark | `telemetry_*` |
| `shared` | Config, logging, clock monotonic, error taxonomy | — |

---

## 4. Ranh giới module trên SQLite

SQLite **không có schema**. Ba cách giữ ranh giới, tôi chọn cách 1:

**Cách 1 — Tiền tố bảng + test tự động (khuyến nghị).** Mỗi module chỉ được ghi vào bảng có tiền tố của mình. Một test quét toàn bộ câu SQL trong codebase, đối chiếu với bảng khai báo của từng module, fail nếu có truy vấn chéo. Đơn giản, một file, một transaction xuyên module khi cần.

**Cách 2 — `ATTACH DATABASE`, mỗi module một file `.db`.** Ranh giới vật lý rõ ràng, nhưng transaction xuyên module phức tạp hơn và backup phải làm nhiều file. Dùng nếu sau này cần tách module ra file riêng.

**Cách 3 — Bỏ ranh giới, một đống bảng chung.** Không chấp nhận — mất khả năng tách service sau này.

Hợp đồng liên module vẫn là `Protocol` in-process, không đổi so với v2.0:

```python
class BrowserControlPort(Protocol):
    async def execute(self, tier: Tier, task: BookingTask,
                      ctx: SessionContext) -> StepResult: ...

class SandboxPort(Protocol):
    async def acquire(self, spec: SandboxSpec) -> SandboxHandle: ...
    async def release(self, handle: SandboxHandle) -> None: ...

class ProfilePort(Protocol):
    async def lease(self, profile_id: str, owner: str) -> ContextLease: ...
    async def release(self, lease: ContextLease) -> None: ...
```

---

## 5. Cấu hình SQLite cụ thể

```sql
PRAGMA journal_mode = WAL;        -- 1 writer + N reader đồng thời
PRAGMA synchronous  = NORMAL;     -- FULL cho bảng giao dịch quan trọng
PRAGMA busy_timeout = 5000;       -- chờ 5s thay vì fail ngay khi gặp khóa
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 1000;
```

**Bố cục file:**

```text
data/
├── app.db          # dữ liệu chính (booking, agent, profile, artifact)
├── app.db-wal      # write-ahead log
└── app.db-shm      # shared memory index
```

**Quy tắc truy cập:**

- Một `aiosqlite` connection pool nhỏ (2–4 connection) cho toàn tiến trình. Không mở connection mới mỗi request.
- Mọi ghi bọc trong transaction ngắn. Không giữ transaction mở trong lúc chờ mạng hay chờ LLM.
- Đọc dùng connection riêng, tận dụng WAL để không chặn writer.
- Ghi hàng loạt (telemetry, benchmark) gom theo lô, flush định kỳ — không ghi từng dòng.

---

## 6. Ánh xạ thành phần PostgreSQL → SQLite

| Thành phần | PostgreSQL (v2.0) | SQLite (v2.1) |
|---|---|---|
| Checkpointer LangGraph | `PostgresSaver` | `AsyncSqliteSaver` |
| Durable Queue | `SELECT ... FOR UPDATE SKIP LOCKED` | `BEGIN IMMEDIATE` + cột `claimed_at`, `claimed_by` |
| Lease Lock TTL | Bảng lease + `pg_advisory_lock` | Bảng `profile_lease` + `fcntl.flock` |
| JSON | `JSONB` | `TEXT` + `json_extract()` (hoặc `JSONB` nếu build hỗ trợ) |
| Full-text search | `tsvector` + GIN | **FTS5** virtual table |
| Auto-increment | `BIGSERIAL` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| Timestamp | `TIMESTAMPTZ` | `TEXT` ISO-8601 UTC (hoặc `INTEGER` epoch ms) |
| Migration | Alembic + PG dialect | Alembic + SQLite dialect, table-rebuild |
| Backup | `pg_dump` | `VACUUM INTO 'backup.db'` |
| Đo hiệu năng | `pg_stat_statements` | `EXPLAIN QUERY PLAN` |

**Durable Queue — chi tiết vì đây là chỗ dễ sai nhất:**

```sql
-- Lấy việc: claim nguyên tử trong một transaction ghi
BEGIN IMMEDIATE;
  UPDATE agent_task
     SET claimed_by = :worker_id,
         claimed_at = :now
   WHERE task_id = (
     SELECT task_id FROM agent_task
      WHERE status = 'pending'
        AND (claimed_at IS NULL OR claimed_at < :stale_before)
      ORDER BY priority DESC, created_at ASC
      LIMIT 1
   )
   RETURNING task_id, payload;
COMMIT;
```

`BEGIN IMMEDIATE` lấy write lock ngay từ đầu, nên hai worker không thể claim cùng một dòng. Không có `SKIP LOCKED` nhưng hiệu quả tương đương ở quy mô một máy.

---

## 7. API contract FE ↔ BE

### 7.1 REST

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/v1/bookings` | Tạo yêu cầu đặt bàn, trả `booking_id` + `trace_id` |
| `GET` | `/v1/bookings/{id}` | Trạng thái hiện tại, cấp đang chạy, kết quả |
| `GET` | `/v1/bookings` | Danh sách, lọc theo trạng thái/ngày/site |
| `POST` | `/v1/bookings/{id}/cancel` | Hủy, idempotent |
| `POST` | `/v1/bookings/{id}/hitl` | Gửi phản hồi HITL (OTP, xác nhận cọc) |
| `GET` | `/v1/sites` | Registry: site đã học, cấp khả dụng |
| `GET` | `/v1/health` | Trạng thái backend, SQLite, sandbox pool |
| `GET` | `/v1/benchmark/runs` | Kết quả benchmark, p50/p95 |

### 7.2 Streaming

| Giao thức | Endpoint | Dùng cho |
|---|---|---|
| SSE | `/v1/bookings/{id}/events` | Tiến trình từng bước, chuyển cấp, log trạng thái |
| WebSocket | `/v1/bookings/{id}/liveview` | Luồng màn hình Live View khi cần khách tự nhập OTP |

**Vì sao SSE cho tiến trình, WS cho Live View:** SSE một chiều, tự reconnect, đủ cho log tiến trình. Live View cần hai chiều (khách bấm, gõ) nên phải WebSocket. Tách hai kênh để lỗi Live View không làm đứt log tiến trình.

### 7.3 Nguyên tắc API

- Mọi response có `trace_id` để đối chiếu với `telemetry`.
- `POST /v1/bookings` nhận `Idempotency-Key`; gọi lại cùng key trả cùng kết quả, không tạo phiên mới.
- Lỗi trả theo taxonomy thống nhất: `INPUT_INVALID`, `TIER_EXHAUSTED`, `HITL_REQUIRED`, `SANDBOX_UNAVAILABLE`, `PROFILE_LOCKED`, `SITE_BLOCKED`.
- FE **không** được nhận thông tin kỹ thuật nội bộ (tên profile, fingerprint seed, proxy IP, đường dẫn artifact).

---

## 8. Luồng end-to-end

```text
1. FE  ──POST /v1/bookings──►  api
2. api ──► booking: tạo bản ghi, sinh trace_id, trả 202 + booking_id
3. booking ──► agent: khởi động LangGraph
4. agent ──► guardrails Lớp 1: chuẩn hóa ngày/giờ/số người/SĐT
5. agent ──► Master Router: tra registry, chọn cấp
6. agent ──► sandbox.acquire()  → container sạch
7. agent ──► profile.lease()    → file lock + fingerprint seed + proxy
8. agent ──► browser_control.execute(tier)
        ├─ Cấp 1: API Replay
        ├─ Cấp 2: Playwright Workflow
        ├─ Cấp 3: Stagehand (A11y Tree) — qua BAML parse_and_guard
        └─ Cấp 4: API vision multimodal (không GPU)
     ↕ lỗi thì trượt cấp trên cùng phiên, không tắt trình duyệt
9. Gặp bước nhạy cảm ──► guardrails Lớp 3: interrupt()
        └─► SSE báo HITL_REQUIRED ──► FE mở Live View (WS)
        └─► khách nhập OTP ──► POST /v1/bookings/{id}/hitl
10. Thành công ──► artifact lưu ảnh/log ──► telemetry ghi metric
11. profile.release() ──► sandbox.release() ──► container tự hủy
12. (chạy ngầm) tự học ngược: CDP Network Sniffer → API Template
                  Stagehand Action Recorder → Playwright Workflow
```

Bước 12 chạy sau khi đã trả kết quả cho FE — không làm chậm lượt đặt bàn.

---

## 9. Ánh xạ từ kiến trúc 3 tầng cũ

| Khối trong `Kiến trúc.txt` | Module trong v2.1 |
|---|---|
| KHỐI 1 — Tầng Điều phối Agent & Guardrails | `agent` |
| KHỐI 2 — Tầng Điều khiển Trình duyệt 4 cấp | `browser_control` |
| KHỐI 3 — Tầng Hạ tầng Browser & Sandbox | `browser_infra` + `sandbox` |
| Cổng giao tiếp chuẩn hóa `wss://browser-endpoint` | Gọi hàm in-process qua `BrowserControlPort` |
| Checkpointer PostgreSQL/Redis | `agent` + SQLite (`AsyncSqliteSaver`) |
| Redis Lock cho profile | `profile` + `fcntl.flock` + bảng lease SQLite |
| Live View noVNC/KasmVNC tự dựng | `browser_infra` + Steel self-host hoặc chụp màn hình định kỳ |

---

## 10. Những gì bị loại bỏ

| Bị loại | Lý do |
|---|---|
| PostgreSQL | Thay bằng SQLite — bỏ service, bỏ cổng mạng, bỏ user/password |
| Phương án A — Browserbase + E2B/Modal | Không dùng cloud; chi phí theo phiên; phụ thuộc nhà cung cấp |
| Redis (lock, cache, checkpoint) | Thêm service phải cài; thay bằng `fcntl.flock` + SQLite |
| Lightpanda | Đã bỏ ở backlog v1.9; không chụp được ảnh cho Cấp 4, không có Live View |
| Inngest / Temporal | Thêm service; thay bằng Durable Queue trên SQLite |
| K8s + gVisor | Quá nặng cho một máy 16GB; dùng Docker Rootless |
| OmniParser V2 + GPU | Cấp 4 chuyển sang API vision multimodal, không cần GPU rời |
| noVNC/KasmVNC tự dựng | Dùng Live View có sẵn của Steel hoặc chụp màn hình định kỳ |

---

## 11. Rủi ro & đánh đổi

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Một tiến trình chết → toàn hệ thống chết | Cao | Supervisor tự khởi động lại; checkpoint SQLite cho phép khôi phục đúng bước |
| SQLite chỉ 1 writer → nghẽn ghi | **Cao (mới)** | Ghi ngắn, gom lô, `busy_timeout`, tách đọc/ghi, cân nhắc `ATTACH` nhiều file nếu nghẽn thật |
| File DB hỏng do tắt máy đột ngột | Trung bình | WAL + `synchronous=NORMAL`; backup `VACUUM INTO` định kỳ; kiểm tra `PRAGMA integrity_check` |
| GIL hạn chế tính toán song song | Trung bình | Phần nặng (trình duyệt) chạy ở tiến trình con, không phải thread Python |
| Áp lực RAM khi nhiều phiên | Cao | `asyncio.Semaphore` giới hạn 3–5 sandbox, 2–3 trình duyệt; health check tự diệt khi vượt ngưỡng |
| Ranh giới module bị phá dần | Cao | Test tự động chặn import chéo và truy vấn chéo bảng |
| Deploy = restart tất cả | Trung bình | Chấp nhận ở quy mô này; checkpoint cho phép khôi phục sau restart |
| Khó scale ngang | Trung bình | Chấp nhận — mục tiêu là một máy; ranh giới module giữ đường tách sau này |

**Đánh đổi cốt lõi:** đổi khả năng scale ngang, cô lập lỗi theo service và khả năng ghi song song cao, lấy đơn giản vận hành trên một máy. Với ràng buộc hiện tại, đây là đánh đổi đúng.

---

## 12. Việc cần chốt

1. **Ngưỡng nghẽn ghi SQLite:** cần đo thật với tải telemetry + benchmark trên máy Core 7 150U. Nếu nghẽn, chuyển sang `ATTACH DATABASE` tách file telemetry.
2. **Cơ chế supervisor:** systemd trong WSL2, Docker restart policy, hay script giám sát riêng?
3. **Ranh giới `browser_infra` ↔ `sandbox`:** gộp làm một module hay giữ hai?
4. **Live View:** dùng Steel self-host hay chụp màn hình định kỳ? Ảnh hưởng trực tiếp đến độ trễ HITL.
5. **Event bus in-process:** callback đồng bộ hay `asyncio.Queue`?
6. **Ngưỡng tài nguyên:** số sandbox và trình duyệt đồng thời thực tế — cần đo lại, không lấy số cũ.
7. **Xác thực FE ↔ BE:** JWT, session cookie, hay API key nội bộ?
8. **Chu kỳ backup:** `VACUUM INTO` mỗi bao lâu, giữ bao nhiêu bản, lưu ở đâu?
