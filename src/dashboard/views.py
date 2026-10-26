from collections.abc import Callable

import pandas as pd
import streamlit as st

from mining import charts
from mining.analysis import Analysis
from mining.anomalies import TESTS, Incident
from mining.smoothing import Choice
from mining.stats import fit_trend
from mining.theme import TOTAL_NAME

STYLE = """
<style>
  .block-container { padding-top: 3.4rem; max-width: 1500px; }
  .wy-overline { font-size: 0.72rem; letter-spacing: 0.22em; font-weight: 700; color: #b08a2e; margin-bottom: 0.1rem; }
  .wy-title { font-size: 2.05rem; font-weight: 700; color: #0f1f2e; line-height: 1.15; margin: 0; }
  .wy-sub { color: #52514e; font-size: 0.92rem; margin-top: 0.35rem; }
  .wy-insight { border-left: 3px solid #c8a24a; background: #fcfcfb; padding: 0.7rem 1rem; border-radius: 4px;
                color: #2b2a27; font-size: 0.93rem; line-height: 1.55; }
  .wy-insight p { margin: 0.15rem 0; }
  [data-testid="stMetric"] { background: #fcfcfb; }
  [data-testid="stMetricLabel"] p { color: #52514e; font-weight: 500; }
  [data-testid="stSidebar"] h5 { margin-top: 0.6rem; color: #0f1f2e; }
</style>
"""

NUMBER = st.column_config.NumberColumn(format="%.1f")


def _plot(fig, key: str | None = None) -> None:
    st.plotly_chart(fig, theme=None, config={"displaylogo": False}, key=key)


def apply_styles() -> None:
    st.html(STYLE)


def header(a: Analysis, source_label: str, report: Callable[[], bytes]) -> None:
    left, right = st.columns([4, 1.2], vertical_alignment="bottom")
    left.html(
        '<div class="wy-overline">WEYLAND-YUTANI CORPORATION</div>'
        '<div class="wy-title">Mining Operations Dashboard</div>'
        f'<div class="wy-sub">{len(a.mines)} mines · {a.days} days · {a.period} · source: {source_label}</div>'
    )
    right.download_button(
        "Download PDF report", data=report, file_name=f"wy-mining-report-{a.start:%Y%m%d}-{a.end:%Y%m%d}.pdf",
        mime="application/pdf", type="primary", icon=":material/picture_as_pdf:", on_click="ignore", width="stretch",
        help="Statistics, charts and a section for every anomaly, built with the settings on the left.",
    )
    st.html('<div class="wy-insight">' + "".join(f"<p>{line}</p>" for line in a.headline()) + "</div>")


def kpis(a: Analysis) -> None:
    total = a.summary.loc[TOTAL_NAME]
    shares = a.summary.loc[a.mines, "total"] / total["total"] * 100
    lead = shares.idxmax()
    trend = fit_trend(a.data[TOTAL_NAME], 1)
    spikes = sum(i.direction == "spike" for i in a.incidents)
    cols = st.columns(5)
    cols[0].metric("Total output", f"{total['total']:,.0f}", f"{a.days} days", delta_color="off", delta_arrow="off",
                   border=True)
    cols[1].metric("Average per day", f"{total['mean']:,.1f}", f"{trend.change_pct:+.1f}% linear trend", border=True,
                   help="Mean daily total; the delta is the change of the fitted linear trend across the period.")
    cols[2].metric("Largest mine", lead, f"{shares[lead]:.0f}% of output", delta_color="off", delta_arrow="off",
                   border=True)
    cols[3].metric("Variability (CV)", f"{total['cv']:.1f}%", f"std dev {total['std']:,.1f}", delta_color="off",
                   delta_arrow="off", border=True, help="Standard deviation of daily total output relative to its mean.")
    cols[4].metric("Anomaly incidents", len(a.incidents), f"{spikes} spikes · {len(a.incidents) - spikes} drops",
                   delta_color="off", delta_arrow="off", border=True)


def stats_table(a: Analysis) -> None:
    frame = a.summary.rename(columns={"mean": "Mean", "std": "Std dev", "median": "Median", "q1": "Q1", "q3": "Q3",
                                      "iqr": "IQR", "min": "Min", "max": "Max", "cv": "CV %", "total": "Total output"})
    frame = frame.join(a.counts[["Anomalies", "Spikes", "Drops"]]).rename_axis("Series")
    frame["Total output"] = frame["Total output"].round(0)
    st.dataframe(frame.round(1), width="stretch", column_config={
        **{c: NUMBER for c in ("Mean", "Std dev", "Median", "Q1", "Q3", "IQR", "Min", "Max", "CV %")},
        "Total output": st.column_config.NumberColumn(format="localized"),
    })


def _smoothing_caption(smooth: Choice | None) -> None:
    if smooth:
        st.caption(f"Smoothed with {smooth.label}; hover a day for its raw value. Spike and drop markers sit on the "
                   "smoothed values but come from tests on the raw data, like all statistics.")


def overview_tab(a: Analysis, kind: str, degree: int | None, series: tuple[str, ...], smooth: Choice | None) -> None:
    _plot(charts.overview_chart(a.data, list(series), kind, degree, a.detections, a.colours, smooth))
    _smoothing_caption(smooth)
    st.markdown("#### Summary statistics")
    st.caption("Daily output per mine and in total. Sample standard deviation; quartiles by linear interpolation.")
    stats_table(a)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Share of output")
        _plot(charts.share_chart(a.summary.loc[a.mines, "total"], a.colours))
    with right:
        st.markdown("#### Weekday profile")
        _plot(charts.weekday_chart(a.weekday()[a.mines], a.colours))
    st.markdown("#### Days flagged per test")
    st.caption("Per-test columns count every flag; Anomalies counts days where enough tests agree.")
    st.dataframe(a.counts.rename_axis("Series"), width="stretch")


def _readings(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    if "tests" in out:
        out["Tests"] = out["tests"]
    else:
        out["Tests"] = out.apply(lambda r: ", ".join(label for t, label in TESTS.items() if r[t]), axis=1) if len(out) else []
    out = out.rename(columns={"value": "Value", "expected": "Expected", "deviation_pct": "Deviation %", "z": "z",
                              "direction": "Type", "votes": "Votes"})
    columns = [c for c in ("Date", "Series", "Type", "Value", "Expected", "Deviation %", "z", "Votes", "Tests") if c in out]
    return out[columns]


READING_CONFIG = {
    "Date": st.column_config.DateColumn(format="YYYY-MM-DD, ddd"),
    "Value": NUMBER, "Expected": NUMBER,
    "Deviation %": st.column_config.NumberColumn(format="%+.1f%%"),
    "z": st.column_config.NumberColumn(format="%+.2f"),
}


def detail_tab(a: Analysis, kind: str, degree: int | None, smooth: Choice | None) -> None:
    name = st.segmented_control("Series", a.series, default=a.mines[0], required=True, key="detail_series")
    det, r = a.detections[name], a.summary.loc[name]
    cols = st.columns(6)
    for col, (label, value) in zip(cols, [("Mean", r["mean"]), ("Std dev", r["std"]), ("Median", r["median"]),
                                          ("IQR", r["iqr"]), ("CV", None), ("Anomalous days", None)]):
        if label == "CV":
            col.metric(label, f"{r['cv']:.1f}%", border=True)
        elif label == "Anomalous days":
            col.metric(label, len(det.anomalies), border=True)
        else:
            col.metric(label, f"{value:,.1f}", border=True)
    show_fences = st.toggle("Show IQR fences", value=False, key="fences",
                            help="Shaded band between the IQR fences, scaled by the weekday pattern when it is removed.")
    detail_kind = "Bar" if kind == "Bar" else "Line"
    fig = charts.series_chart(det, a.colours[name], detail_kind, degree, a.settings, show_fences, smooth)
    _plot(fig)
    _smoothing_caption(smooth)
    st.markdown("#### Test diagnostics")
    st.caption("Bars beyond the dashed limits are flagged by that test. Values are computed after the weekday "
               "adjustment when it is on.")
    _plot(charts.diagnostics_chart(det, a.settings))
    left, right = st.columns([3, 1.2])
    with left:
        st.markdown("#### Anomalous days")
        if det.anomalies.empty:
            st.info("No day reached the test consensus for this series.", icon=":material/check_circle:")
        else:
            st.dataframe(_readings(det.anomalies), hide_index=True, width="stretch", column_config=READING_CONFIG)
    with right:
        st.markdown("#### Grubbs iterations")
        if det.grubbs_steps:
            steps = pd.DataFrame(det.grubbs_steps, columns=["Date", "G", "G critical"])
            st.dataframe(steps, hide_index=True, width="stretch", column_config={
                "Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "G": st.column_config.NumberColumn(format="%.3f"),
                "G critical": st.column_config.NumberColumn(format="%.3f")})
        else:
            st.caption("Grubbs found no outlier" + ("" if "grubbs" in a.settings.tests else " (test is off)") + ".")


def incident_card(a: Analysis, incident: Incident) -> None:
    with st.container(border=True):
        title, badge = st.columns([5, 1], vertical_alignment="center")
        title.markdown(f"**Incident {incident.number}** · {incident.title}")
        with badge:
            if incident.direction == "spike":
                st.badge("Spike", icon=":material/arrow_upward:", color="red")
            else:
                st.badge("Drop", icon=":material/arrow_downward:", color="red")
        tests = sorted({t for e in incident.episodes for t in e.tests}, key=list(TESTS.values()).index)
        st.markdown(f"**{incident.days}** day(s) · peak deviation **{incident.peak_deviation:+.1f}%** · "
                    f"{', '.join(incident.series)}")
        st.caption(f"Tests: {', '.join(tests)}")
        if incident.planned:
            st.caption(f":material/event: Matches {incident.planned}")
        else:
            st.caption(":material/help: No generator event configured for these days.")
        _plot(charts.incident_chart(a.data, incident, a.detections, a.colours), f"incident-{incident.number}")
        rows = pd.concat([e.rows.assign(Series=e.series) for e in incident.episodes])
        with st.expander("Readings"):
            st.dataframe(_readings(rows), hide_index=True, width="stretch", column_config=READING_CONFIG)


def anomalies_tab(a: Analysis) -> None:
    if not a.incidents:
        st.success("No anomalies reached the consensus with the current settings.", icon=":material/check_circle:")
    else:
        st.caption(f"{len(a.incidents)} incident(s). Episodes of different series that overlap in time and point the same "
                   "way are grouped into one incident.")
        left, right = st.columns(2)
        for n, incident in enumerate(a.incidents):
            with left if n % 2 == 0 else right:
                incident_card(a, incident)
    st.markdown("#### All anomalous days")
    st.dataframe(_readings(a.flagged.rename(columns={"series": "Series"})), hide_index=True, width="stretch",
                 column_config=READING_CONFIG)


def data_tab(a: Analysis) -> None:
    st.dataframe(a.data, hide_index=True, width="stretch", height=420, column_config={
        "Date": st.column_config.DateColumn(format="YYYY-MM-DD, ddd"), **{s: NUMBER for s in a.series}})
    st.download_button("Download CSV", a.data.to_csv(index=False, date_format="%Y-%m-%d"), file_name="mining-output.csv",
                       mime="text/csv", icon=":material/download:", on_click="ignore")
    if a.planned is not None and not a.planned.empty:
        st.markdown("#### Events configured on the Generator sheet")
        st.dataframe(a.planned, hide_index=True, width="stretch",
                     column_config={"Day": st.column_config.DateColumn(format="YYYY-MM-DD")})
