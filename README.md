# TASK 5

Weyland-Yutani mining output: a data generator built from Google Sheets formulas (part I) and a web dashboard
that analyses it and exports a PDF report (part II).

## Part I: generator (Google Sheet)

The sheet has three tabs: `Generator` (the parameter table and two live charts), `Impact` (which mines each event
hits) and `Data` (the generated table). All values come from formulas in cells; nothing runs as a script when
parameters change. Layout, named ranges, every formula and the maths behind them are in
[sheet/formulas.md](sheet/formulas.md).

Build it once:

1. Open a blank spreadsheet (sheets.new).
2. Extensions > Apps Script, replace the code with [sheet/build_sheet.gs](sheet/build_sheet.gs), save, select
   `buildMiningSimulator`, Run, and allow it to edit the spreadsheet. It writes the table, named ranges, formulas,
   validation and charts; it can be deleted afterwards.
3. Share > General access > Anyone with the link > Editor.

What the user can change on `Generator`:

| Parameter | Where | Effect |
|-----------|-------|--------|
| Mines (number and names) | B5 to the right, up to Z5 | One `Data` column per name; Capacity (row 6) scales each mine |
| Date range | Start date B4, Days count C4 | Up to 1000 days |
| Distribution | B8 dropdown | Normal, Uniform, Lognormal; the parameter labels in C7:D7 switch (Mean/Deviation or Min/Max) |
| Smoothing | E8 | Day-to-day correlation (AR(1) coefficient) |
| Mine link | F8 | Share of the daily shock common to all mines |
| Seed | G8 | New random scenario; the same seed reproduces the data |
| Weekday factors | B10:H10 | e.g. Sunday 0.6 = output reduced by 40% |
| Trend | B11 | Compound daily growth (negative for decline) |
| Events (6 rows) | B13:F18 | Day, Duration, Factor, Probability, or Mines = exact number of mines hit; bell-shaped |

Row 19 checks the parameters (for example a Uniform Max below Min) and says what to fix.

## Part II: dashboard (Streamlit)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Paste the spreadsheet link in the sidebar, or save it once in `.streamlit/secrets.toml`:

```toml
SHEET_URL = "https://docs.google.com/spreadsheets/d/<id>/edit"
```

Sources: **Google Sheet** (reads the `Data` tab as CSV, cached for two minutes, "Reload from sheet" refreshes),
**Demo** (a Python twin of the sheet formulas with the default parameters, `src/mining/simulator.py`), or **CSV**
(a `Date` column plus one numeric column per mine).

The dashboard shows, for each mine and for the total:

- mean, standard deviation, median, quartiles and IQR, min, max, coefficient of variation;
- anomalies from four tests with adjustable parameters: IQR rule (k), z-score (threshold), distance from a moving
  average (window, percent, centred or trailing) and iterative Grubbs' test (alpha). A day is an anomaly when at least
  N enabled tests agree (N is adjustable). The weekday pattern can be removed before testing so planned weekend
  slowdowns are not flagged;
- line, bar or stacked charts with outliers marked (▲ spike, ▼ drop) and polynomial trendlines of degree 1-4;
- optional smoothing buttons for the overview and detail charts (one button per file in `src/mining/smoothing/`;
  delete a file and its button disappears). With a smoother on, lines and bars show only smoothed values, the hover
  still gives each day's raw value, and spike/drop markers sit on the smoothed values. The PDF report draws its
  overview and mine profile charts the same way. Tests, statistics and incident close-ups use the raw values;
- per-series detail with test diagnostics and Grubbs iterations, and incident cards: overlapping anomalies of
  several mines are grouped into one incident and matched with the events configured on the Generator tab.

**Download PDF report** builds an A4 report with the same settings: cover with key figures and contents, executive
summary, statistics and trend tables, detection settings and counts, anomaly map, configured events versus findings,
a profile per mine, one section per incident (spike or drop) with chart and readings, methodology and the daily data.

## Tests

```powershell
python -m pytest tests
```

Covers the generator twin (distributions, smoothing, mine link, weekday factors, events, mine counts), the four
tests and incident grouping, statistics and trendlines, sheet link parsing, PDF building, and that
`sheet/formulas.md` shows the same formulas as `sheet/build_sheet.gs`.

## Layout

| Path | Role |
|------|------|
| `sheet/build_sheet.gs` | One-time builder of the Google Sheet (formulas are the source of truth) |
| `sheet/formulas.md` | Sheet layout, named ranges, formulas and how they work |
| `src/mining/simulator.py` | Python twin of the sheet formulas for demo data and tests |
| `src/mining/source.py` | Google Sheet / CSV loading |
| `src/mining/stats.py` | Summary statistics, polynomial trendlines, weekday profile |
| `src/mining/anomalies.py` | IQR, z-score, moving average and Grubbs tests; episodes and incidents |
| `src/mining/analysis.py` | One `Analysis` bundle shared by the dashboard and the report |
| `src/mining/charts.py` | Plotly figures |
| `src/mining/report.py` | PDF report (reportlab + matplotlib) |
| `src/dashboard/` | Streamlit sidebar controls and page sections |
| `streamlit_app.py` | Entry point: data loading, caching, tabs |

## Deploy to Streamlit Community Cloud (free)

Push this folder to GitHub, then share.streamlit.io > Create app > pick the repository, main file
`streamlit_app.py`, Python 3.13, and add the secret `SHEET_URL = "<spreadsheet link>"`.
