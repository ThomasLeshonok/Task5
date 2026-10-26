import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from dashboard import views
from dashboard.controls import DEMO, SHEET, UPLOAD, chart_controls, smoothing_controls, source_controls, test_controls
from mining import simulator, source
from mining.analysis import Analysis, analyze
from mining.anomalies import Settings
from mining.report import build_report

st.set_page_config(page_title="Mining Ops · Weyland-Yutani", page_icon=":material/precision_manufacturing:",
                   layout="wide")


@st.cache_data(ttl=120, show_spinner="Reading the Google Sheet...")
def sheet_data(url: str) -> tuple[pd.DataFrame, pd.DataFrame | None, str]:
    return source.load_sheet(url), source.load_sheet_events(url), datetime.now().strftime("%H:%M:%S")


@st.cache_data
def demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return simulator.generate(), simulator.planned_events()


@st.cache_data
def uploaded_data(content: bytes) -> pd.DataFrame:
    return source.parse_table(content)


@st.cache_data(show_spinner="Running the anomaly tests...")
def run_analysis(data: pd.DataFrame, settings: Settings, planned: pd.DataFrame | None) -> Analysis:
    return analyze(data, settings, planned)


def load(kind: str, url: str, upload: bytes | None, upload_name: str | None):
    """Returns (data, planned events, source label) or stops the page with a message."""
    if kind == SHEET:
        if not url:
            st.info("Paste the link of the Mining Ops Simulator spreadsheet in the sidebar, or switch to Demo.",
                    icon=":material/link:")
            st.stop()
        try:
            data, planned, loaded = sheet_data(url)
        except source.SourceError as error:
            st.error(str(error), icon=":material/error:")
            st.stop()
        return data, planned, f"Google Sheet (read {loaded})"
    if kind == UPLOAD:
        if upload is None:
            st.info("Upload a CSV file with a Date column and one numeric column per mine.", icon=":material/upload_file:")
            st.stop()
        try:
            return uploaded_data(upload), None, upload_name or "CSV file"
        except (source.SourceError, ValueError) as error:
            st.error(f"Could not read the file: {error}", icon=":material/error:")
            st.stop()
    data, planned = demo_data()
    return data, planned, DEMO


def main() -> None:
    views.apply_styles()
    with st.sidebar:
        kind, url, upload, upload_name = source_controls()
    data, planned, label = load(kind, url, upload, upload_name)
    mines = [c for c in data.columns if c not in ("Date", "Total")]
    with st.sidebar:
        chart_kind, degree, series = chart_controls([*mines, "Total"], mines)
        smooth = smoothing_controls()
        settings = test_controls()

    a = run_analysis(data, settings, planned)
    views.header(a, label, lambda: build_report(a, kind=chart_kind, degree=degree, series=list(series), source=label,
                                                smooth=smooth))
    views.kpis(a)
    overview, detail, anomalies, table = st.tabs(["Overview", "Mine detail", "Anomalies", "Data"])
    with overview:
        views.overview_tab(a, chart_kind, degree, series, smooth)
    with detail:
        views.detail_tab(a, chart_kind, degree, smooth)
    with anomalies:
        views.anomalies_tab(a)
    with table:
        views.data_tab(a)


main()
