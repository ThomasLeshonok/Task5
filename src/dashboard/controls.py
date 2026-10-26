import os

import streamlit as st

from mining.anomalies import TESTS, Settings
from mining.smoothing import Choice, available

SHEET, DEMO, UPLOAD = "Google Sheet", "Demo", "CSV"
NO_SMOOTHING = "None"
CHART_KINDS = ("Line", "Bar", "Stacked")
TREND_DEGREES = (None, 1, 2, 3, 4)


def default_sheet_url() -> str:
    try:
        return st.secrets.get("SHEET_URL", "") or os.environ.get("SHEET_URL", "")
    except FileNotFoundError:
        return os.environ.get("SHEET_URL", "")


def source_controls() -> tuple[str, str, bytes | None, str | None]:
    st.markdown("##### Data source")
    url_default = default_sheet_url()
    kind = st.segmented_control("Source", (SHEET, DEMO, UPLOAD), default=SHEET if url_default else DEMO,
                                required=True, label_visibility="collapsed", key="source", width="stretch")
    url, upload, name = "", None, None
    if kind == SHEET:
        url = st.text_input("Spreadsheet link", value=url_default, placeholder="https://docs.google.com/spreadsheets/d/...",
                            help="Link of the Mining Ops Simulator spreadsheet. It must be shared as 'Anyone with the link'.")
        if st.button("Reload from sheet", icon=":material/refresh:", width="stretch",
                     help="Data is cached for two minutes; reload to pick up parameter changes at once."):
            st.cache_data.clear()
    elif kind == UPLOAD:
        file = st.file_uploader("CSV with a Date column and one column per mine", type="csv")
        if file is not None:
            upload, name = file.getvalue(), file.name
    else:
        st.caption("Built-in twin of the sheet formulas with their default parameters.")
    return kind, url.strip(), upload, name


def chart_controls(series: list[str], mines: list[str]) -> tuple[str, int | None, tuple[str, ...]]:
    st.markdown("##### Charts")
    kind = st.segmented_control("Chart type", CHART_KINDS, default="Line", required=True, key="kind", width="stretch")
    degree = st.selectbox("Trendline", TREND_DEGREES, index=1, key="degree",
                          format_func=lambda d: "None" if d is None else f"Polynomial, degree {d}")
    chosen = st.multiselect("Series", series, default=mines, key="series",
                            help="Stacked charts stack the selected mines; Total adds its own anomaly markers on top.")
    return kind, degree, tuple(chosen or mines)


def smoothing_controls() -> Choice | None:
    smoothers = available()
    picked = st.pills("Smoothing", (NO_SMOOTHING, *smoothers), default=NO_SMOOTHING, required=True, key="smoothing",
                      help="Draws a smoothed line over the faded raw values. Anomaly tests always use raw values.")
    if picked not in smoothers:
        return None
    smoother = smoothers[picked]
    values = []
    for p in smoother.params:
        whole = all(float(v).is_integer() for v in (p.low, p.high, p.default, p.step))
        cast = int if whole else float
        value = st.slider(p.label, cast(p.low), cast(p.high), cast(p.default), cast(p.step), help=p.help,
                          key=f"smooth-{smoother.module.__name__}-{p.key}")
        values.append((p.key, value))
    return Choice(smoother, tuple(values))


def test_controls() -> Settings:
    st.markdown("##### Anomaly tests")
    enabled = []
    with st.expander("IQR rule", expanded=False):
        on = st.toggle("Use IQR rule", value=True, key="iqr_on")
        k = st.slider("Fence multiplier k", 0.5, 4.0, 1.5, 0.1, key="iqr_k",
                      help="Outlier when below Q1 - k x IQR or above Q3 + k x IQR. 1.5 is Tukey's classic choice.")
        enabled += ["iqr"] if on else []
    with st.expander("Z-score"):
        on = st.toggle("Use z-score", value=True, key="z_on")
        z = st.slider("Threshold |z|", 1.5, 5.0, 3.0, 0.1, key="z_thr",
                      help="Outlier when the value is more than this many standard deviations from the mean.")
        enabled += ["zscore"] if on else []
    with st.expander("Distance from moving average"):
        on = st.toggle("Use moving average", value=True, key="ma_on")
        window = st.slider("Window, days", 3, 30, 7, 1, key="ma_window")
        pct = st.slider("Max distance, %", 5, 100, 25, 1, key="ma_pct")
        centered = st.toggle("Centred window", value=True, key="ma_centered",
                             help="On: average of the days around each day. Off: average of the previous days only.")
        enabled += ["ma"] if on else []
    with st.expander("Grubbs' test"):
        on = st.toggle("Use Grubbs' test", value=True, key="g_on")
        alpha = st.select_slider("Significance level alpha", (0.001, 0.01, 0.025, 0.05, 0.1), value=0.05, key="g_alpha",
                                 help="Lower alpha means stronger evidence is needed before a value is called an outlier.")
        enabled += ["grubbs"] if on else []
    if len(enabled) > 1:
        votes = st.slider("Tests that must agree", 1, len(enabled), min(2, len(enabled)), key=f"votes-{len(enabled)}",
                          help="A day is reported as an anomaly when at least this many enabled tests flag it.")
    else:
        votes = 1
        st.caption("Enable at least one test." if not enabled else "One test enabled: every flag counts as an anomaly.")
    weekday = st.toggle("Remove weekday pattern before testing", value=True, key="weekday",
                        help="Divides each day by its typical weekday level so planned weekend slowdowns are not flagged.")
    return Settings(iqr_k=k, z_threshold=z, ma_window=window, ma_pct=float(pct), ma_centered=centered,
                    grubbs_alpha=alpha, tests=tuple(t for t in TESTS if t in enabled), min_votes=votes,
                    weekday_adjust=weekday)
