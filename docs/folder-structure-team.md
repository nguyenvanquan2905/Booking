# Cấu trúc thư mục & phân vùng sở hữu — vb-browser-use

> **Bản chốt dùng chung cho cả team.** Mục tiêu: mỗi người chỉ làm trong vùng của mình → không conflict code.
> Nguồn chốt: `README.md` · `docs/system-design-booking-agent-v2.1.md` (mục 3–4) · `backlog-jira-mvp-browser-agent.md` (mục 00d).
> Cây dưới đây phản ánh **hiện trạng repo** (đã có code thực tế từ MVP-01/52/60/80/82/83/84/90/100–104). File chưa có code vẫn là stub rỗng — **không xóa, không đổi tên**; chúng chốt ranh giới module.

## 1. Cây thư mục chính xác

```text
vb-browser-use/
├── .env.example                          # mẫu biến môi trường (commit) — KHÓA CHUNG
├── .gitignore                            # KHÓA CHUNG
├── AGENTS.md                             # quy tắc cho AI agent — KHÓA CHUNG
├── README.md                             # mô tả cấu trúc — KHÓA CHUNG
├── alembic.ini                           # cấu hình migration — KHÓA CHUNG
├── pyproject.toml                        # deps + pytest/ruff — KHÓA CHUNG
├── requirements.txt                      # deps MVP — KHÓA CHUNG
├── backlog-jira-mvp-browser-agent.md     # backlog 74 task — KHÓA CHUNG
│
├── docs/
│   ├── system-design-booking-agent-v2.1.md   # system design — KHÓA CHUNG
│   └── folder-structure-team.md              # tài liệu này
│
├── data/                                 # SQLite runtime + dữ liệu benchmark — E
│   ├── .gitkeep
│   ├── app.db                            # SQLite runtime — KHÔNG COMMIT
│   ├── prices.json                       # cost model input (MVP-103) — commit
│   ├── scenarios/
│   │   └── baseline.json                 # kịch bản đặt bàn (MVP-52) — commit
│   └── scorecards/
│       └── playwright__pasgo.json        # điểm độ phức tạp (MVP-60) — commit
├── profiles/                             # Profile Vault runtime — KHÔNG COMMIT · A
│   └── .gitkeep
├── artifacts/                            # ảnh/HAR/HTML theo booking — KHÔNG COMMIT · E
│   └── .gitkeep
├── frontend/                             # FE web app — F
│   └── .gitkeep
│
├── migrations/                           # Alembic — E (MVP-80)
│   ├── env.py                            #   env SQLite dialect
│   ├── script.py.mako                    #   template revision
│   └── versions/
│       ├── .gitkeep
│       └── 0001_initial.py               #   revision đầu — DDL import từ shared/schema.py
│
├── src/booking_agent/
│   ├── __init__.py
│   ├── main.py                           # entrypoint backend — C
│   │
│   ├── shared/                           # shared kernel — C (MVP-01)
│   │   ├── __init__.py
│   │   ├── config.py                     #   pydantic-settings                    [có code]
│   │   ├── logging.py                    #   JSONL log + trace_id + PII redaction [có code]
│   │   ├── clock.py                      #   clock monotonic                      [có code]
│   │   ├── errors.py                     #   error taxonomy                       [có code]
│   │   ├── db.py                         #   aiosqlite pool + PRAGMA (WAL)        [có code]
│   │   ├── schema.py                     #   DDL duy nhất cho toàn bộ SQLite      [có code]
│   │   ├── trace.py                      #   chuẩn trace_id xuyên tầng (MVP-90)   [có code]
│   │   └── pii.py                        #   mã hóa/mask PII (MVP-83)             [có code]
│   │
│   ├── api/                              # F (EPIC-11) — stub
│   │   ├── __init__.py
│   │   ├── app.py                        #   FastAPI app factory
│   │   ├── deps.py                       #   dependency injection
│   │   ├── schemas.py                    #   request/response models
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── bookings.py               #   /v1/bookings (+ cancel, hitl)
│   │   │   ├── sites.py                  #   /v1/sites
│   │   │   ├── health.py                 #   /v1/health
│   │   │   └── benchmark.py              #   /v1/benchmark/runs
│   │   ├── streaming/
│   │   │   ├── __init__.py
│   │   │   ├── sse.py                    #   /v1/bookings/{id}/events
│   │   │   └── liveview.py               #   /v1/bookings/{id}/liveview (WS)
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── rate_limit.py
│   │       └── trace.py                  #   gắn trace_id mọi response
│   │
│   ├── booking/                          # C (MVP-39, 83) — bảng booking_*
│   │   ├── __init__.py
│   │   ├── models.py                     #   stub
│   │   ├── repository.py                 #   stub
│   │   ├── service.py                    #   stub
│   │   ├── state_machine.py              #   stub
│   │   ├── idempotency.py                #   stub — Idempotency-Key
│   │   └── pii.py                        #   CustomerRepository, TTL xóa (MVP-83) [có code]
│   │
│   ├── agent/                            # C (EPIC-1)
│   │   ├── __init__.py
│   │   ├── graph.py                      #   stub — LangGraph definition
│   │   ├── checkpointer.py               #   stub — AsyncSqliteSaver
│   │   ├── router.py                     #   stub — Master Router
│   │   ├── registry.py                   #   MasterRouter + Tier (MVP-84)         [có code]
│   │   ├── queue.py                      #   stub — Durable Queue
│   │   └── guardrails/
│   │       ├── __init__.py
│   │       ├── layer1_normalize.py       #   stub
│   │       ├── layer2_policy.py          #   stub
│   │       └── layer3_hitl.py            #   stub
│   │
│   ├── browser_control/                  # D (EPIC-3) — bảng bc_*
│   │   ├── __init__.py
│   │   ├── port.py                       #   stub — BrowserControlPort (Protocol)
│   │   ├── registry.py                   #   Registry API Template/Workflow (MVP-84) [có code]
│   │   ├── tiers/
│   │   │   ├── __init__.py
│   │   │   ├── tier1_api_replay.py       #   stub — Cấp 1
│   │   │   ├── tier2_playwright.py       #   stub — Cấp 2
│   │   │   ├── tier3_stagehand.py        #   stub — Cấp 3
│   │   │   └── tier4_vision.py           #   stub — Cấp 4
│   │   └── learning/
│   │       ├── __init__.py
│   │       ├── network_sniffer.py        #   stub
│   │       └── action_recorder.py        #   stub
│   │
│   ├── browser_infra/                    # A (EPIC-2) — trừ 2 file của D
│   │   ├── __init__.py
│   │   ├── cdp_gateway.py                #   D — MVP-02 Unified CDP/WS Gateway (stub)
│   │   ├── steel.py                      #   A — stub
│   │   ├── xvfb.py                       #   A — stub
│   │   ├── camoufox.py                   #   A — stub
│   │   └── liveview.py                   #   D — MVP-27 Live View HITL (stub)
│   │
│   ├── sandbox/                          # B (EPIC-4) — bảng sandbox_* — stub
│   │   ├── __init__.py
│   │   ├── port.py                       #   SandboxPort (Protocol)
│   │   ├── allocator.py                  #   asyncio.Semaphore trần 3–5 phiên
│   │   ├── lifecycle.py
│   │   ├── health.py
│   │   └── zero_egress.py                #   chặn SSRF
│   │
│   ├── profile/                          # A (MVP-24, 74, 75) — bảng profile_* — stub
│   │   ├── __init__.py
│   │   ├── port.py                       #   ProfilePort (Protocol)
│   │   ├── vault.py                      #   Profile Vault
│   │   ├── lease.py                      #   profile_lease + fcntl.flock
│   │   ├── fingerprint.py                #   fingerprint seed
│   │   └── proxy.py                      #   proxy dân cư, IP cố định
│   │
│   ├── artifact/                         # E (MVP-82) — bảng artifact_*
│   │   ├── __init__.py
│   │   ├── store.py                      #   lưu file local (ảnh, HAR, HTML)     [có code]
│   │   └── index.py                      #   artifact_index + FTS5               [có code]
│   │
│   └── telemetry/                        # C (schema) + E (metrics, benchmark)
│       ├── __init__.py
│       ├── schema.py                     #   C — log contract 4 tầng (MVP-01/91) [có code]
│       ├── metrics.py                    #   E — statistics engine (MVP-102)     [có code]
│       ├── benchmark.py                  #   E — matrix runner (MVP-100)         [có code]
│       ├── scenarios.py                  #   E — kịch bản JSON (MVP-52)          [có code]
│       ├── complexity.py                 #   E — scorecard 9 tiêu chí (MVP-60)   [có code]
│       ├── cost.py                       #   E — cost model (MVP-103)            [có code]
│       ├── report.py                     #   E — report generator (MVP-104)      [có code]
│       ├── sites.py                      #   E — site registry 12 site (MVP-50)  [có code]
│       ├── ground_truth.py               #   E — pass/fail từng site (MVP-51)    [có code]
│       ├── accounts.py                   #   E — tài khoản test + OTP (MVP-53)   [có code]
│       ├── dataset.py                    #   E — đóng băng dataset (MVP-101)     [có code]
│       ├── emitter.py                    #   E — instrumentation 4 tầng (MVP-91) [có code]
│       └── pipeline.py                   #   E — script tái lập báo cáo (MVP-104)[có code]
│
└── tests/
    ├── __init__.py
    ├── conftest.py                       # fixture DB SQLite mới mỗi test — KHÓA CHUNG
    ├── unit/                             # mỗi người thêm test_<module>_*.py của mình
    │   ├── __init__.py
    │   ├── test_artifact.py              #   MVP-82
    │   ├── test_benchmark.py             #   MVP-100
    │   ├── test_complexity.py            #   MVP-60
    │   ├── test_cost.py                  #   MVP-103
    │   ├── test_metrics.py               #   MVP-102
    │   ├── test_pii.py                   #   MVP-83
    │   ├── test_registry.py              #   MVP-84
    │   ├── test_report.py                #   MVP-104
    │   ├── test_scenarios.py             #   MVP-52
    │   ├── test_schema.py                #   MVP-80
    │   └── test_trace.py                 #   MVP-90
    ├── integration/                      # mỗi người thêm test của mình
    │   ├── __init__.py
    │   └── test_pipeline_e2e.py          #   E — freeze → run → stats → report
    └── architecture/                     # KHÓA CHUNG — C chủ trì
        ├── __init__.py
        ├── test_module_boundaries.py     # chặn import chéo giữa module
        └── test_no_cross_table_queries.py  # quét SQL, chặn truy vấn chéo bảng
```

## 2. Ai sở hữu vùng nào

| Người | Phạm vi | Thư mục / file sở hữu | Bảng SQLite | Task chính |
|---|---|---|---|---|
| **A** | Hạ tầng browser | `browser_infra/` (trừ `cdp_gateway.py`, `liveview.py`), `profile/`, `profiles/` | `profile_*`, `profile_lease` | MVP-22–26, 76 |
| **B** | Hạ tầng sandbox | `sandbox/` | `sandbox_*` | MVP-20, 40–42, 45, 46, 70, 71, 73 |
| **C** | Agent | `agent/`, `booking/`, `shared/`, `main.py`, `telemetry/schema.py` | `agent_*`, `booking_*` | MVP-01, 03–08, 10–18, 29, 39 |
| **D** | Browser control | `browser_control/`, `browser_infra/cdp_gateway.py`, `browser_infra/liveview.py` | `bc_*` | MVP-02, 27, 28, 30–36, 38 |
| **E** | Benchmark & dữ liệu | `artifact/`, `telemetry/` (trừ `schema.py`), `migrations/`, `data/`, `artifacts/` | `artifact_*`, `telemetry_*` | MVP-50–53, 60–64, 80, 82–84, 90, 91, 100–104 |
| **F** | API + FE | `api/`, `frontend/` | — | MVP-110–113, 120–123 |

> Hai file `browser_infra/cdp_gateway.py` và `browser_infra/liveview.py` nằm trong thư mục của A nhưng là việc của **D** (MVP-02, MVP-27) — theo backlog mục 00d. A không sửa 2 file này; D không sửa các file còn lại của `browser_infra/`.

## 3. Quy tắc chống conflict (bắt buộc)

### 3.1 Ba nguyên tắc vàng

1. **Một thư mục — một owner.** Không sửa file ngoài vùng của mình, kể cả 1 dòng.
2. **Giao tiếp qua hợp đồng, không qua file.** Liên module chỉ qua `Protocol` trong `port.py` (`BrowserControlPort`, `SandboxPort`, `ProfilePort`) hoặc Interface Spec MVP-01. Không import thẳng internals của module khác — `tests/architecture/test_module_boundaries.py` sẽ fail.
3. **File khóa chung: đổi phải thống nhất nhóm trước** (danh sách ở 3.2).

### 3.2 File khóa chung — không tự sửa

- Cấu hình & tài liệu gốc: `pyproject.toml`, `requirements.txt`, `alembic.ini`, `.env.example`, `.gitignore`, `AGENTS.md`, `README.md`, `docs/`, `backlog-jira-mvp-browser-agent.md`
- Test kiến trúc: `tests/architecture/*`, `tests/conftest.py`
- Hợp đồng liên module: `src/booking_agent/*/port.py` (sửa phải thống nhất cả bên gọi và bên cung cấp)
- Shared kernel: `src/booking_agent/shared/*` (C chủ trì — sửa phải báo C)
- `src/booking_agent/shared/schema.py` — **nguồn DDL duy nhất**; mọi thay đổi bảng phải qua đây + 1 revision mới
- Migration đã có trong `migrations/versions/` (không sửa/rewrite của người khác)

### 3.3 Git

- Base branch: `main`. Bắt đầu task:

  ```bash
  git switch main && git pull --rebase
  git switch -c feature/MVP-XX-mo-ta-ngan
  ```

- **1 task = 1 branch = 1 PR nhỏ, chỉ trong 1 module.** PR chạm nhiều module phải tách.
- Commit message có mã task: `feat(MVP-30): tier1 api replay`, `fix(MVP-41): zero-egress rule`.
- Không push thẳng `main` — mọi thay đổi qua PR.
- Không commit: `.env`, `data/*.db*`, `data/backup/`, `profiles/*` (trừ `.gitkeep`), `artifacts/*` (trừ `.gitkeep`), `__pycache__/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`.
- Migration: mỗi thay đổi schema = 1 revision mới (`alembic revision -m "..."`); trước khi PR chạy `alembic heads` — phải đúng **1 head**.
- Nếu dùng AI assistant trong repo: đọc `AGENTS.md` trước — agent bị **cấm mọi thao tác git lên remote** (push, tag, PR…), chỉ được clone/pull/fetch.

### 3.4 Ranh giới bảng SQLite

SQLite không có schema → ranh giới bằng **tiền tố bảng** (khai báo trong `shared/schema.py`):

| Module | Bảng sở hữu |
|---|---|
| `booking` | `booking_*` |
| `agent` | `agent_*` |
| `browser_control` | `bc_*` |
| `sandbox` | `sandbox_*` |
| `profile` | `profile_*` |
| `artifact` | `artifact_*` |
| `telemetry` | `telemetry_*` |

- Chỉ ghi vào bảng có tiền tố của module mình.
- Đọc chéo phải qua repository/service của module sở hữu.
- `tests/architecture/test_no_cross_table_queries.py` quét toàn bộ SQL và fail nếu vi phạm.

### 3.5 Khi cần thêm file / thư mục mới

- File mới đặt trong module đã có, tên `snake_case`.
- Module/thư mục mới trong `src/booking_agent/` → thống nhất cả nhóm + cập nhật `README.md` + test kiến trúc.
- Package mới bắt buộc có `__init__.py` (`test_every_module_has_init` kiểm tra).
- Không tạo file mới ở thư mục gốc repo.

## 4. Setup môi trường (WSL2 Ubuntu 24.04 · Python 3.12.3)

```bash
cd ~/vb-browser-use
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # hoặc: pip install -e ".[dev]"
cp .env.example .env                 # rồi sửa API_KEY, DB_PATH nếu cần
pytest                               # phải xanh, gồm cả tests/architecture
uvicorn booking_agent.main:app --reload
```

> README có thêm bản PowerShell cho Windows; `requirements.txt` chốt target WSL2 + Python 3.12.3.

## 5. Checklist trước khi mở PR

- [ ] Chỉ sửa file trong vùng của mình (mục 2)
- [ ] Không đụng file khóa chung (mục 3.2)
- [ ] `pytest` xanh — đặc biệt `tests/architecture/`
- [ ] `ruff check src tests` sạch
- [ ] Không commit `.env`, DB, profile, artifact runtime
- [ ] PR nhỏ, 1 module, tiêu đề có mã `MVP-XX`
- [ ] Đã `git pull --rebase` từ `main` trước khi mở PR
