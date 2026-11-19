# AGENTS.md — Quy tắc làm việc cho AI Agent trong vb-browser-use

1. **Phạm vi sở hữu**: Chỉ sửa các file thuộc phân vùng được giao (xem `docs/folder-structure-team.md`). Không xóa hoặc đổi tên các file stub rỗng của module khác.
2. **Không tự ý sửa file khóa chung**: `pyproject.toml`, `requirements.txt`, `alembic.ini`, `.env.example`, `.gitignore`, `AGENTS.md`, `README.md`, `docs/`, `tests/conftest.py`, `tests/architecture/*`, `src/booking_agent/*/port.py`, `src/booking_agent/shared/*`, `migrations/versions/0001_initial.py`.
3. **Ranh giới module & SQLite**:
   - Giao tiếp liên module chỉ qua `Protocol` trong `port.py` hoặc service công khai, không import internals của module khác.
   - Chỉ ghi vào bảng có tiền tố của module mình (`booking_*`, `agent_*`, `bc_*`, `sandbox_*`, `profile_*`, `artifact_*`, `telemetry_*`).
4. **Git safety**: AI agent bị **cấm mọi thao tác git lên remote** (`push`, `tag`, `PR`...); chỉ được `clone`, `pull`, `fetch` hoặc kiểm tra local.
5. **Kiểm chứng bắt buộc**: Sau khi chỉnh sửa, chạy `pytest` (bao gồm `tests/architecture/`) và `ruff check src tests`.
