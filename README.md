# Task 5: Weyland-Yutani mining data

Synthetic daily output of Weyland-Yutani mines and a dashboard that analyses it.

**Generator.** A Google Sheet built only from cell formulas generates daily output per mine. Adjustable: mines,
date range, distribution (normal, uniform, lognormal), smoothing, weekday factors, trend and spike/drop events.
`src/mining/simulator.py` repeats the same formulas in Python for demo data and tests.

**Dashboard.** A Streamlit app reads the sheet (or demo data, or a CSV) and shows for each mine and the total:
mean, standard deviation, median, IQR, anomalies (IQR rule, z-score, distance from moving average, Grubbs),
line, bar or stacked charts with trendlines and optional smoothing, and a PDF report.

## Run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Paste the sheet link in the sidebar or set `SHEET_URL` in `.streamlit/secrets.toml`. The sheet must be shared as
"Anyone with the link".

## Tests

```powershell
python -m pytest tests
```

## Deploy

Streamlit Community Cloud: main file `streamlit_app.py`, Python 3.13, secret `SHEET_URL`.
