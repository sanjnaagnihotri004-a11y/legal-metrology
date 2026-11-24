# Legal Metrology Compliance Checker — Frontend

Frontend-only Streamlit application based on the supplied Frontend Developer Handover, API contract v1.0.

## Requirements
- Python 3.10+
- FastAPI backend (optional while using mock mode)

## Setup (Windows / VS Code)

Open this `frontend` folder in VS Code. In the VS Code terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

If PowerShell blocks activation, use:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open http://localhost:8501.

## Mock mode
The included mock mode lets you explore the screens without the backend:
`USE_MOCK=true` in `.env`.

For backend integration, set:
`USE_MOCK=false`
`BACKEND_URL=http://localhost:8000`

Restart Streamlit after changing `.env`.

## Backend contract
The frontend calls the endpoints and field names described in the handover:
`/health`, `/auth/login`, `/auth/me`, `/scans`, `/scans/{id}`, `/scans/{id}/recheck`,
`/scans/{id}/image`, `/scans/{id}/annotated-image`, `/scans/{id}/evidence`,
`/scans/{id}/report`, `/stats`, `/rules`, `/users`.

All authenticated requests are made in `utils/api_client.py`. Pages must not call the backend directly.

## Important
- Mock data is illustrative only; it is not legal advice or real inspection data.
- Compliance decisions, OCR, clause text and rule thresholds come from FastAPI.
- Backend must enforce role permissions and data ownership.
- This is a screening aid. Findings must be verified by an authorised officer.
- The handover mentions the `recheck` endpoint as an addition that the backend developer must confirm.
