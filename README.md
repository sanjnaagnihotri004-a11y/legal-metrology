
# Legal Metrology Compliance Checker

A screening tool for the **Legal Metrology (Packaged Commodities) Rules, 2011**. An inspector uploads a
photo of a product label. The system reads it with OCR, extracts the mandatory declarations, checks six
rules, measures the height of the net quantity numerals, draws the findings on the photo, and produces a
PDF, Word or CSV report. Scans, photos and inspection history are stored and shown on a dashboard.

> **This is a screening aid.** Findings must be verified by an authorised officer.

## Contents

1. [What it checks](#what-it-checks)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Project layout](#project-layout)
5. [Setup and run (Windows)](#setup-and-run-windows)
6. [Using the app](#using-the-app)
7. [Demo data](#demo-data)
8. [Tests and accuracy evaluation](#tests-and-accuracy-evaluation)
9. [API overview](#api-overview)
10. [Known limitations](#known-limitations)
11. [Troubleshooting](#troubleshooting)

## What it checks

| Rule | Check | Severity |
|---|---|---|
| LM-R1 | Manufacturer / packer / importer name and address, with a 6-digit PIN code | critical |
| LM-R2 | Net quantity declared with a standard metric unit | critical |
| LM-R3 | MRP declared, inclusive of all taxes | critical |
| LM-R4 | Month and year of manufacture / packing / import | major |
| LM-R5 | Consumer care details (phone or email) | major |
| LM-R6 | Net quantity numeral height against the minimum for the display-panel area | major |

Each rule returns `pass`, `fail` or `not_checked`. The scan status is:

- **non_compliant**: at least one rule failed;
- **needs_review**: nothing failed, but a rule could not be checked (for example no label width was given,
  or the numeral height is within 10% of the limit) or the OCR confidence is low;
- **compliant**: every rule passed.

The score is the weighted share of rules passed (critical 3, major 2, minor 1).
Clause numbers and the numeral-height table live in `backend/rules/rules.yaml`. **They come from
secondary sources and must be verified against the official gazette before formal use.**

## Features

- Photo upload or camera capture, with product details and an optional label width
- OCR with automatic correction of sideways photos (90-degree steps)
- Extraction of the five declarations, including table layouts (heading above value)
- Rule engine with clause references and a message per rule
- Numeral-height check scaled from the label width (optional)
- Annotated image: green, red and orange boxes, and a banner listing what was not found
- Manual correction of OCR text followed by a fresh compliance check
- Evidence photos and notes attached to a scan
- Repository with search and filters, and a dashboard with charts
- Reports in PDF, Word (.docx) and CSV
- Roles: `admin` sees everything and manages users; `inspector` sees only their own scans
- Login with JWT tokens

## Architecture

```
Streamlit frontend  --HTTP/JSON-->  FastAPI backend
                                      |-- auth and roles (JWT)
                                      |-- scan pipeline:
                                      |     image preparation -> OCR (RapidOCR) -> field extraction
                                      |     -> rule engine -> numeral-height check -> annotated image
                                      |-- report builder (PDF / DOCX / CSV)
                                      `-- SQLite database + file storage (photos, evidence)
```

Technologies: Python 3.11, FastAPI, SQLAlchemy, SQLite, RapidOCR (ONNX), OpenCV, Pillow, ReportLab,
python-docx, Streamlit, Plotly, pytest.

## Project layout

```
legal-metrology/
  backend/
    app/
      main.py  config.py  db.py  errors.py  security.py  deps.py
      models/        database tables (users, products, scans, violations, evidence, rules)
      schemas/       request and response shapes (the API contract)
      routers/       auth, scans, evidence, reports, stats, rules, users
      services/      ocr, extraction, engine, fontsize, annotate, pipeline,
                     scan_service, storage, reports, calibration
      mock_data/     sample label images used by tests
    rules/rules.yaml rules, clause numbers and the numeral-height table
    scripts/         seed, bulk_scan, evaluate, diagnose, probes
    tests/           automated tests
    storage/         uploaded photos and generated files (not in Git)
  frontend/
    app.py  utils/  views/  .streamlit/config.toml
  docs/              evidence and documentation
  README.md
```

## Setup and run (Windows)

Needs **Python 3.11** (3.12 also works; very new versions may lack packages) and Git.
Run the backend and the frontend in **two separate terminals, both left open**.

### Backend

```powershell
cd backend
py -3.11 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `backend\.env` and set `JWT_SECRET` to a long random text. One way to make one:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Then create the database and start the server:

```powershell
python -m scripts.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Health check: http://localhost:8000/health
- Interactive API console: http://localhost:8000/docs
- The first scan after a start takes longer (the OCR engine loads, and may download its models once).

### Frontend

```powershell
cd frontend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

In `frontend\.env`:

```
BACKEND_URL=http://localhost:8000
USE_MOCK=false
REQUEST_TIMEOUT_SECONDS=120
```

Restart Streamlit after changing `.env`. Open http://localhost:8501.
`USE_MOCK=true` shows the screens with illustrative data and no backend.

### Development accounts

| Role | Email | Password |
|---|---|---|
| admin | `admin@lm.test` | `Admin@123` |
| inspector | `inspector@lm.test` | `Inspector@123` |

These are for development only. Change them, and use a new `JWT_SECRET`, before any real use.

### Reset the database

Stop the backend first, then from `backend`:

```powershell
Remove-Item lm.db
Remove-Item storage\originals\*, storage\annotated\*, storage\evidence\* -ErrorAction SilentlyContinue
python -m scripts.seed
```

## Using the app

1. Log in, then open **New Scan**.
2. Upload or take a photo, and enter the product name, brand and category.
3. Optionally enter the **real width in mm of the area covered by the whole photo**, measured left to
   right. Crop the photo tightly around the label so this is simply the label width. If it is left at 0,
   LM-R6 is reported as "needs review" and the other five rules still run.
4. Click **Analyse label**. The result page shows the rule results, both images and the extracted text.
5. If the OCR got something wrong, correct the field under **Manual correction** and re-run the check.
6. Attach evidence if needed, and download the report as PDF, Word or CSV.
7. **Repository** lists past scans with search and filters. **Dashboard** shows totals, rates and charts.

**Photo tips:** lay the pack flat, photograph the face carrying the declarations from straight above,
keep the text upright, avoid glare, use good light and use the original phone photo (messaging apps
shrink and compress images). Do not include ID cards or other personal details in photos: photos are
stored and embedded in reports.

## Demo data

To fill the repository and dashboard, put photos and a `labels.csv` in one folder:

```
filename,product_name,brand,category,label_width_mm
lakme_facewash.jpeg,Blush & Glow Jelly Facewash,Lakme,cosmetics,89
masalabox.jpeg,Masala Box,Unknown,food,
```

Allowed categories: `food`, `edible_oil`, `beverages`, `cosmetics`, `personal_care`,
`detergent_household`, `other`. Leave `label_width_mm` blank if unknown. Then, from `backend`:

```powershell
python -m scripts.bulk_scan "D:\label_photos" --spread-days 5
```

`--spread-days` spreads the scan dates over the last N days, which makes the charts richer.
`--mm-per-px 0.06` can be added for a fixed camera setup (it replaces blank widths).

## Tests and accuracy evaluation

```powershell
cd backend
python -m pytest tests -v
```

About 150 automated tests cover the extractors, the rule engine, the numeral-height measurement, the
annotated image, sideways photos and the whole API (login, scans, corrections, evidence, reports,
statistics, users). Some run real OCR, so the full run takes a few minutes.

**Accuracy evaluation** compares the system with a human reading of each photo (LM-R1 to LM-R5):

```powershell
python -m scripts.evaluate "D:\label_photos" --template   # creates ground_truth.csv, fill it in by hand
python -m scripts.evaluate "D:\label_photos"              # prints accuracy, precision and recall
python -m scripts.diagnose "D:\label_photos"              # shows what the OCR read for each disagreement
```

**First result:** 16 photographed packs, 80 rule judgements, 68% agreement with the manual reading.
Recall was 100% (no real violation was missed). Every disagreement was a false alarm, giving precision
of 36% to 56% per rule. Causes are OCR failures on small, faint or curved print and declarations whose
value is printed apart from its label. This is a **baseline** from a small set judged by one person, and
the code was tuned on the same photos, so it should not be read as a general accuracy figure.

## API overview

All endpoints except `/auth/login` and `/health` need the header `Authorization: Bearer <token>`.
Full interactive documentation is at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Server status |
| `POST /auth/login`, `GET /auth/me` | Log in, current user |
| `POST /scans` | Upload a photo and analyse it (width is optional) |
| `GET /scans` | List with search, filters and paging |
| `GET /scans/{id}` | Full result |
| `GET /scans/{id}/image`, `/annotated-image` | The stored photo, and the annotated copy |
| `POST /scans/{id}/recheck` | Apply corrections and re-run the rules |
| `POST /scans/{id}/evidence`, `GET /evidence/{id}/file` | Attach and read evidence |
| `GET /scans/{id}/report?format=pdf\|docx\|csv` | Download a report |
| `GET /stats` | Dashboard numbers |
| `GET /rules` | The rules and their clauses |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | User management (admin only) |

Errors always have the same shape:
`{"error": {"code": "VALIDATION_ERROR", "message": "...", "fields": {"field": "reason"}}}`.

## Known limitations

- **One photo per scan.** A product with several printed panels needs one scan per panel, and a
  single panel rarely shows every declaration.
- **Curved packs** (tubes, bottles, bags) distort and hide text, so the OCR misses more there.
- **Layouts:** a value must be near its label. Same-line, next-line and two table layouts are handled
  (heading above value, symbol-marked dates). Other layouts are often missed.
- **Net quantity** is recognised only next to wording such as "Net Wt." or "Net Vol." A weight inside a
  product name (for example "Groundnut 1KG") is not counted. An inspector can record it with a manual
  correction.
- **LM-R1 requires a PIN code.** Check whether the Rules actually make this mandatory, and relax the
  check in `backend/app/services/engine.py` if not.
- **Numeral height** needs a physical scale, so it depends on the width entered. The display-panel area is
  estimated from the extent of the detected text, and the formula for curved packs is not implemented.
  Only net quantity numerals are measured, and only the "normal printing" column of the table is used.
  Results within 10% of the limit are referred for manual verification.
- Photos are rotated in 90-degree steps only; text tilted by other angles may be misread.
- English labels only. Dates on charts are grouped by UTC day.
- The clause numbers and the numeral-height table come from secondary sources and need verification.
- The accuracy test set is small and was judged by one person.

**Future work:** flattening of curved labels, layout-aware reading, several photos per product, an
automatic scale from a reference object, regional-language OCR, e-commerce listing checks.

## Troubleshooting

| Problem | What to do |
|---|---|
| Frontend says the backend is not reachable | Start the backend in its own terminal; check http://localhost:8000/health; check `BACKEND_URL` in `frontend/.env` and restart Streamlit |
| `INVALID_CREDENTIALS` for a development account | The database has no users. Stop the backend, then run `python -m scripts.seed` |
| `No space left on device` while installing or uploading | Free space on drive C: and, in that terminal, run `mkdir D:\tmp -Force` then `$env:TEMP = "D:\tmp"` and `$env:TMP = "D:\tmp"` |
| `no such column` after pulling new code | The database is from an older version. Reset it (see above) |
| PowerShell blocks `Activate.ps1` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| OCR_NO_TEXT | The photo is blank, blurred or too small. Retake it flat, sharp, well lit and filling the frame |

## License and disclaimer

College project. Not legal advice. Results are automated screening output and must be verified by an
authorised officer.