# vb-browser-use — Booking Agent MVP

Dự án Booking Agent với kiến trúc modular monolith (`src/booking_agent/`), phân tách ranh giới module rõ ràng cho 6 thành viên (A–F) và đồng bộ qua SQLite WAL + `Protocol` ports.

## Cấu trúc chính

Xem chi tiết tại [docs/folder-structure-team.md](docs/folder-structure-team.md).

## Setup nhanh (Windows PowerShell — ổ D:)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
pytest
uvicorn booking_agent.main:app --reload
```

## Setup chuẩn WSL2 Ubuntu 24.04

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest
uvicorn booking_agent.main:app --reload
```
