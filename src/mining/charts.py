import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from mining.anomalies import TESTS, Detection, Incident, Settings
from mining.smoothing import Choice, drawn
from mining.stats import fit_trend
from mining.theme import AXIS, BAND, CRITICAL, GRID, INK, INK_SECONDARY, MUTED, TOTAL, TOTAL_NAME, rgba

FONT = '"Source Sans", "Source Sans Pro", system-ui, -apple-system, "Segoe UI", sans-serif'
MARKERS = {"spike": ("triangle-up", "Spike"), "drop": ("triangle-down", "Drop")}


def _style(fig: go.Figure, height: int, ytitle: str | None = "Daily output") -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 36, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": INK_SECONDARY, "size": 12},
        hovermode="x unified",
        hoverlabel={"font": {"family": FONT}},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "title": None, "font": {"color": INK}},
        bargap=0.18,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, ticks="outside", tickcolor=AXIS, title=None, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, automargin=True, rangemode="tozero",
                     title={"text": ytitle, "font": {"color": MUTED}, "standoff": 8})
    return fig


def _trend_legend(fig: go.Figure, degree: int) -> None:
    fig.add_scatter(x=[None], y=[None], mode="lines", name=f"Trendline (degree {degree})",
                    line={"color": MUTED, "dash": "dot", "width": 2})


def _hover(raw: pd.Series, smooth: Choice | None) -> dict:
    """With smoothing the chart shows only smoothed values; the raw value of the day stays in the hover."""
    if smooth:
        return {"customdata": raw, "hovertemplate": "%{y:,.1f} smoothed (raw %{customdata:,.1f})"}
    return {"hovertemplate": "%{y:,.1f}"}


def _series(fig: go.Figure, x: pd.Series, y: pd.Series, name: str, colour: str, kind: str,
            smooth: Choice | None) -> pd.Series:
    """Draws one series as bars or a line, smoothed when a smoother is chosen. Returns the drawn values."""
    shown = drawn(y, smooth)
    if kind == "Bar":
        fig.add_bar(x=x, y=shown, name=name, legendgroup=name, marker={"color": colour, "line": {"width": 0}},
                    **_hover(y, smooth))
    else:
        fig.add_scatter(x=x, y=shown, mode="lines", name=name, legendgroup=name, line={"color": colour, "width": 2},
                        **_hover(y, smooth))
    return shown


def _flag_traces(fig: go.Figure, points: pd.DataFrame, **kwargs) -> None:
    for direction, (symbol, label) in MARKERS.items():
        part = points[points["direction"] == direction]
        if part.empty:
            continue
        fig.add_scatter(
            x=part["Date"], y=part["y"], mode="markers", name=label,
            marker={"symbol": symbol, "size": 12, "color": CRITICAL, "line": {"color": "white", "width": 1.5}},
            customdata=part[["series", "value", "deviation_pct", "tests"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b> " + label.lower() + ": %{customdata[1]:,.1f}"
                          " (%{customdata[2]:+.1f}% vs average)<br>%{customdata[3]}<extra></extra>",
            **kwargs,
        )


def _flag_points(detection: Detection, y: pd.Series | None = None) -> pd.DataFrame:
    a = detection.anomalies.copy()
    a["series"] = detection.series
    a["y"] = (y if y is not None else detection.frame["value"]).loc[a.index]
    a["tests"] = a.apply(lambda r: ", ".join(label for t, label in TESTS.items() if r[t]), axis=1) if len(a) else []
    return a


def overview_chart(data: pd.DataFrame, series: list[str], kind: str, degree: int | None,
                   detections: dict[str, Detection], colours: dict[str, str], smooth: Choice | None = None) -> go.Figure:
    fig = go.Figure()
    x = data["Date"]
    flags = []
    if kind == "Stacked":
        mines = [s for s in series if s != TOTAL_NAME] or [c for c in data.columns if c not in ("Date", TOTAL_NAME)]
        # segments are smoothed one by one, so the stack top is the smoothed total; markers sit on their segment
        heights = pd.DataFrame({name: _series(fig, x, data[name], name, colours[name], "Bar", smooth) for name in mines})
        top = heights.cumsum(axis=1)
        for name in mines:
            flags.append(_flag_points(detections[name], top[name]))
        total = top[mines[-1]]
        fig.add_scatter(x=x, y=total, mode="lines", name="Stack total", line={"color": TOTAL, "width": 1.2},
                        **_hover(data[mines].sum(axis=1), smooth))
        if TOTAL_NAME in series and TOTAL_NAME in detections:
            flags.append(_flag_points(detections[TOTAL_NAME], total))
        if degree:
            fig.add_scatter(x=x, y=fit_trend(total, degree).fitted, mode="lines", showlegend=False, hoverinfo="skip",
                            line={"color": INK, "dash": "dot", "width": 2})
        fig.update_layout(barmode="stack", bargap=0.12, legend_traceorder="normal")
    else:
        for name in series:
            colour = colours[name]
            shown = _series(fig, x, data[name], name, colour, kind, smooth)
            if degree:
                fig.add_scatter(x=x, y=fit_trend(data[name], degree).fitted, mode="lines", legendgroup=name,
                                showlegend=False, hoverinfo="skip", line={"color": colour, "dash": "dot", "width": 2})
            flags.append(_flag_points(detections[name], shown))
        fig.update_layout(barmode="group")
    if degree:
        _trend_legend(fig, degree)
    points = pd.concat(flags) if flags else pd.DataFrame()
    if not points.empty:
        _flag_traces(fig, points)
    return _style(fig, 470)


def series_chart(detection: Detection, colour: str, kind: str, degree: int | None, settings: Settings,
                 fences: bool = False, smooth: Choice | None = None) -> go.Figure:
    f = detection.frame
    fig = go.Figure()
    if fences:
        fig.add_scatter(x=f["Date"], y=f["iqr_high"], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=f["Date"], y=f["iqr_low"], mode="lines", line={"width": 0}, fill="tonexty", fillcolor=BAND,
                        name="IQR fences", hoverinfo="skip")
    shown = _series(fig, f["Date"], f["value"], detection.series, colour, kind, smooth)
    fig.add_scatter(x=f["Date"], y=drawn(f["expected"], smooth), mode="lines", name=f"{settings.ma_window}-day average",
                    line={"color": MUTED, "width": 1.4}, **_hover(f["expected"], smooth))
    if degree:
        trend = fit_trend(f["value"], degree)
        fig.add_scatter(x=f["Date"], y=trend.fitted, mode="lines", name=f"Trendline (degree {degree}, R² {trend.r2:.2f})",
                        line={"color": INK, "dash": "dot", "width": 2}, hoverinfo="skip")
    single = f[(f["votes"] > 0) & ~f["anomaly"]]
    if len(single):
        fig.add_scatter(x=single["Date"], y=shown.loc[single.index], mode="markers", name="Flagged below consensus",
                        marker={"symbol": "circle-open", "size": 9, "color": INK_SECONDARY, "line": {"width": 1.5}},
                        customdata=single[["votes", "value"]].to_numpy(),
                        hovertemplate="flagged by %{customdata[0]} test(s), raw %{customdata[1]:,.1f}<extra></extra>")
    _flag_traces(fig, _flag_points(detection, shown))
    return _style(fig, 420)


def diagnostics_chart(detection: Detection, settings: Settings) -> go.Figure:
    f = detection.frame
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                        subplot_titles=("Z-score", "Distance from moving average, %"))
    for row, column, limit in ((1, "z", settings.z_threshold), (2, "deviation_pct", settings.ma_pct)):
        colours = [CRITICAL if abs(v) > limit else AXIS for v in f[column].fillna(0)]
        fig.add_bar(x=f["Date"], y=f[column], marker={"color": colours, "line": {"width": 0}}, showlegend=False,
                    hovertemplate="%{y:+.2f}", row=row, col=1)
        for sign in (1, -1):
            fig.add_hline(y=sign * limit, line={"color": CRITICAL, "dash": "dash", "width": 1}, row=row, col=1)
    fig.update_annotations(font={"size": 12, "color": INK_SECONDARY}, x=0, xanchor="left")
    _style(fig, 380, None)
    fig.update_yaxes(rangemode="normal")
    return fig


def incident_chart(data: pd.DataFrame, incident: Incident, detections: dict[str, Detection],
                   colours: dict[str, str], pad_days: int = 10) -> go.Figure:
    lo, hi = incident.start - pd.Timedelta(days=pad_days), incident.end + pd.Timedelta(days=pad_days)
    window = data[(data["Date"] >= lo) & (data["Date"] <= hi)]
    mines = [s for s in incident.series if s != TOTAL_NAME]
    panels = [p for p in (mines, [TOTAL_NAME] if TOTAL_NAME in incident.series else []) if p]
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.62, 0.38][: len(panels)] if len(panels) > 1 else None)
    for row, names in enumerate(panels, start=1):
        fig.add_vrect(x0=incident.start - pd.Timedelta(hours=12), x1=incident.end + pd.Timedelta(hours=12),
                      fillcolor=rgba(CRITICAL, 0.08), line_width=0, row=row, col=1)
        flags = []
        for name in names:
            fig.add_scatter(x=window["Date"], y=window[name], mode="lines+markers", name=name,
                            line={"color": colours[name], "width": 2}, marker={"size": 5}, hovertemplate="%{y:,.1f}",
                            row=row, col=1)
            points = _flag_points(detections[name])
            flags.append(points[(points["Date"] >= incident.start) & (points["Date"] <= incident.end)])
        sub = go.Figure()
        _flag_traces(sub, pd.concat(flags), showlegend=False)
        for trace in sub.data:
            fig.add_trace(trace, row=row, col=1)
    return _style(fig, 300 if len(panels) == 1 else 380)


def weekday_chart(profile: pd.DataFrame, colours: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for name in profile.columns:
        fig.add_bar(x=profile.index, y=profile[name], name=name, marker={"color": colours[name], "line": {"width": 0}},
                    hovertemplate="%{y:.2f}× average")
    fig.add_hline(y=1, line={"color": MUTED, "width": 1})
    fig.update_layout(barmode="group", hovermode="x")
    return _style(fig, 320, "Share of average day")


def share_chart(totals: pd.Series, colours: dict[str, str]) -> go.Figure:
    totals = totals.sort_values()
    share = totals / totals.sum() * 100
    fig = go.Figure(go.Bar(
        x=totals, y=totals.index, orientation="h", marker={"color": [colours[n] for n in totals.index], "line": {"width": 0}},
        text=[f"{v:,.0f}  ·  {s:.0f}%" for v, s in zip(totals, share)], textposition="outside", cliponaxis=False,
        textfont={"color": INK_SECONDARY}, hovertemplate="%{y}: %{x:,.1f}<extra></extra>",
    ))
    _style(fig, 320, None)
    fig.update_layout(hovermode="closest", margin={"r": 90})
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig
