import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates 
import matplotlib.pyplot as plt  
import pandas as pd  
from reportlab.lib import colors 
from reportlab.lib.enums import TA_RIGHT  
from reportlab.lib.pagesizes import A4  
from reportlab.lib.styles import ParagraphStyle   
from reportlab.lib.units import mm   
from reportlab.pdfgen import canvas as rl_canvas   
from reportlab.platypus import (   
    BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents   

from mining.analysis import Analysis   
from mining.anomalies import TESTS, Detection, Incident
from mining.smoothing import Choice, drawn
from mining.stats import fit_trend
from mining.theme import (   
    AXIS, BRAND, BRAND_ACCENT, CRITICAL, GRID, INK, INK_SECONDARY, MUTED, TOTAL, TOTAL_NAME,
)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
BAND_H = 100 * mm
STRIPE = colors.HexColor("#f4f3ef")
HAIRLINE = colors.HexColor("#dcdad2")


def _style(name: str, **kw) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 9.2, "leading": 13.2, "textColor": colors.HexColor("#1f1f1d")}
    return ParagraphStyle(name, **(base | kw))


S = {
    "h1": _style("H1", fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=colors.HexColor(BRAND),
                 spaceBefore=4, spaceAfter=10),
    "h2": _style("H2", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=colors.HexColor(BRAND),
                 spaceBefore=12, spaceAfter=6),
    "contents": _style("Contents", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=colors.HexColor(BRAND),
                       spaceAfter=6),
    "h3": _style("H3", fontName="Helvetica-Bold", fontSize=9.5, leading=13, spaceBefore=8, spaceAfter=4),
    "body": _style("Body", spaceAfter=6),
    "lead": _style("Lead", fontSize=10.5, leading=15.5, spaceAfter=8),
    "caption": _style("Caption", fontSize=7.8, leading=10.5, textColor=colors.HexColor(MUTED), spaceBefore=2, spaceAfter=10),
    "cell": _style("Cell", fontSize=7.8, leading=10),
    "cell_r": _style("CellR", fontSize=7.8, leading=10, alignment=TA_RIGHT),
    "head": _style("Head", fontName="Helvetica-Bold", fontSize=7.6, leading=9.5, textColor=colors.white),
    "head_r": _style("HeadR", fontName="Helvetica-Bold", fontSize=7.6, leading=9.5, textColor=colors.white, alignment=TA_RIGHT),
    "kpi_label": _style("KpiLabel", fontSize=7.5, leading=9, textColor=colors.HexColor(INK_SECONDARY)),
    "kpi_value": _style("KpiValue", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor(INK)),
    "kpi_note": _style("KpiNote", fontSize=7.2, leading=9, textColor=colors.HexColor(MUTED)),
    "toc0": _style("TOC0", fontSize=10, leading=17),
    "toc1": _style("TOC1", fontSize=8.6, leading=13, leftIndent=14, textColor=colors.HexColor(INK_SECONDARY)),
}

MPL_STYLE = {
    "font.family": "DejaVu Sans",
    "font.size": 7.5,
    "axes.edgecolor": AXIS,
    "axes.linewidth": 0.6,
    "axes.labelcolor": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "xtick.major.size": 2.5,
    "ytick.major.size": 0,
    "legend.frameon": False,
    "legend.fontsize": 7,
    "figure.dpi": 100,
    "savefig.dpi": 190,
}



class NumberedCanvas(rl_canvas.Canvas):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self.setFont("Helvetica", 7.2)
                self.setFillColor(colors.HexColor(MUTED))
                self.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


class ReportDoc(BaseDocTemplate):
    def __init__(self, buffer, analysis: Analysis, source: str, generated: datetime):
        super().__init__(buffer, pagesize=A4, title="Mining Operations Report", author="Weyland-Yutani Corporation",
                         subject=f"Daily output analysis {analysis.period}", leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=MARGIN, bottomMargin=MARGIN)
        self.analysis, self.source, self.generated = analysis, source, generated
        cover = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - BAND_H - MARGIN - 10 * mm, id="cover")
        body = Frame(MARGIN, MARGIN + 4 * mm, CONTENT_W, PAGE_H - 2 * MARGIN - 10 * mm, id="body")
        self.addPageTemplates([PageTemplate("cover", [cover], onPage=self._cover),
                               PageTemplate("body", [body], onPage=self._decorate)])
        self._entries = 0

    def beforeDocument(self):
        self._entries = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("H1", "H2"):
            level = 0 if flowable.style.name == "H1" else 1
            text = flowable.getPlainText()
            key = f"entry-{self._entries}"
            self._entries += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            if level == 0 or getattr(flowable, "_toc", False):
                self.notify("TOCEntry", (level, text, self.page, key))

    def _cover(self, canv, doc):
        a = self.analysis
        canv.saveState()
        canv.setFillColor(colors.HexColor(BRAND))
        canv.rect(0, PAGE_H - BAND_H, PAGE_W, BAND_H, stroke=0, fill=1)
        canv.setFillColor(colors.HexColor(BRAND_ACCENT))
        canv.rect(0, PAGE_H - BAND_H, PAGE_W, 1.6 * mm, stroke=0, fill=1)
        x = MARGIN
        canv.setFont("Helvetica-Bold", 9)
        canv.drawString(x, PAGE_H - 26 * mm, "W E Y L A N D - Y U T A N I   C O R P O R A T I O N")
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 30)
        canv.drawString(x, PAGE_H - 50 * mm, "Mining Operations Report")
        canv.setFont("Helvetica", 12.5)
        canv.setFillColor(colors.HexColor("#c9d3dc"))
        canv.drawString(x, PAGE_H - 60 * mm, "Daily output statistics, trends and anomaly review")
        canv.setFont("Helvetica-Bold", 10.5)
        canv.setFillColor(colors.white)
        canv.drawString(x, PAGE_H - 78 * mm, f"Reporting period: {a.period}")
        canv.setFont("Helvetica", 9)
        canv.setFillColor(colors.HexColor("#c9d3dc"))
        canv.drawString(x, PAGE_H - 84.5 * mm, f"{len(a.mines)} mines  ·  {a.days} days  ·  "
                                               f"prepared {self.generated:%Y-%m-%d %H:%M}")
        canv.setFont("Helvetica-Oblique", 8.5)
        canv.drawRightString(PAGE_W - MARGIN, PAGE_H - 84.5 * mm, "Building Better Worlds")
        self._footer(canv)
        canv.restoreState()

    def _decorate(self, canv, doc):
        canv.saveState()
        top = PAGE_H - 11 * mm
        canv.setFont("Helvetica-Bold", 7.2)
        canv.setFillColor(colors.HexColor(BRAND))
        canv.drawString(MARGIN, top, "WEYLAND-YUTANI CORPORATION")
        canv.setFont("Helvetica", 7.2)
        canv.setFillColor(colors.HexColor(MUTED))
        canv.drawRightString(PAGE_W - MARGIN, top, f"Mining Operations Report  ·  {self.analysis.period}")
        canv.setStrokeColor(colors.HexColor(BRAND_ACCENT))
        canv.setLineWidth(0.8)
        canv.line(MARGIN, top - 2.6 * mm, PAGE_W - MARGIN, top - 2.6 * mm)
        self._footer(canv)
        canv.restoreState()

    def _footer(self, canv):
        canv.setStrokeColor(HAIRLINE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        canv.setFont("Helvetica", 7.2)
        canv.setFillColor(colors.HexColor(MUTED))
        canv.drawString(MARGIN, 10 * mm, f"Generated {self.generated:%Y-%m-%d %H:%M}  ·  Source: {self.source}"[:120])



def _num(value: float, digits: int = 1) -> str:
    return "-" if pd.isna(value) else f"{value:,.{digits}f}"


def _table(rows: list[list], widths: list[float], numeric_from: int = 1, swatches: dict[int, str] | None = None,
           bold_last: bool = False, repeat: int = 1, font_size: float | None = None, text_cols: tuple[int, ...] = (),
           alerts: set[tuple[int, int]] | None = None) -> Table:

    cell, cell_r, head, head_r = S["cell"], S["cell_r"], S["head"], S["head_r"]
    if font_size:
        cell = ParagraphStyle("c", parent=cell, fontSize=font_size, leading=font_size + 2)
        cell_r = ParagraphStyle("cr", parent=cell_r, fontSize=font_size, leading=font_size + 2)

    def right(c: int) -> bool:
        return c >= numeric_from and c not in text_cols

    def text(r: int, c: int, v) -> str:
        if alerts and (r, c) in alerts:
            return f'<font color="{CRITICAL}"><b>{v}</b></font>'
        return f"<b>{v}</b>" if bold_last and r == len(rows) - 1 else str(v)

    body = [[Paragraph(str(v), head_r if right(c) else head) for c, v in enumerate(rows[0])]]
    body += [[Paragraph(text(r, c, v), cell_r if right(c) else cell) for c, v in enumerate(row)]
             for r, row in enumerate(rows[1:], start=1)]
    table = Table(body, colWidths=widths, repeatRows=repeat, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, HAIRLINE),
    ]
    style += [("BACKGROUND", (0, r), (-1, r), STRIPE) for r in range(2, len(body), 2)]
    for r, colour in (swatches or {}).items():
        style.append(("LINEBEFORE", (0, r), (0, r), 3, colors.HexColor(colour)))
    if bold_last:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.9, colors.HexColor(INK)))
    table.setStyle(TableStyle(style))
    return table


def _kpis(items: list[tuple[str, str, str]]) -> Table:
    cells = [[Paragraph(label, S["kpi_label"]), Paragraph(value, S["kpi_value"]), Paragraph(note, S["kpi_note"])]
             for label, value, note in items]
    width = CONTENT_W / len(items)
    table = Table([cells], colWidths=[width] * len(items), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), STRIPE),
        ("LINEBEFORE", (1, 0), (-1, -1), 4, colors.white),
        ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(BRAND_ACCENT)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def _h1(number: int, text: str) -> Paragraph:
    return Paragraph(f"{number}.&nbsp;&nbsp;{text}", S["h1"])


def _h2(text: str, toc: bool = False) -> Paragraph:
    p = Paragraph(text, S["h2"])
    p._toc = toc
    return p



def _image(fig, width: float = CONTENT_W, tight: bool = True) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight" if tight else None, pad_inches=0.04, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    img.drawWidth = width
    img.drawHeight = width * img.imageHeight / img.imageWidth
    return img


def _figure(height_mm: float):
    with plt.rc_context(MPL_STYLE):
        fig, ax = plt.subplots(figsize=(CONTENT_W / 72, height_mm / 25.4))
    _dates(ax)
    return fig, ax


def _dates(ax) -> None:
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def _flags(ax, frame: pd.DataFrame, y: pd.Series | None = None, size: float = 38) -> None:
    a = frame[frame["anomaly"]]
    ys = (y if y is not None else frame["value"]).loc[a.index]
    for direction, marker in (("spike", "^"), ("drop", "v")):
        mask = a["direction"] == direction
        if mask.any():
            ax.scatter(a.loc[mask, "Date"], ys[mask], marker=marker, s=size, color=CRITICAL, edgecolor="white",
                       linewidth=0.8, zorder=5, label=direction.capitalize())


def _legend(ax, ncol: int = 8) -> None:
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    reference = ("Trend", "Moving average", "Below consensus")
    order = sorted(unique, key=lambda label: 2 if label in ("Spike", "Drop")
                   else 1 if label.startswith(reference) or label.endswith("-day average") else 0)
    ax.legend([unique[k] for k in order], order, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol,
              handlelength=1.6, columnspacing=1.2, borderaxespad=0.3)


def overview_figure(a: Analysis, kind: str, degree: int | None, series: list[str], smooth: Choice | None) -> Image:
    with plt.rc_context(MPL_STYLE):
        fig, ax = _figure(78)
        d, colours = a.data, a.colours
        if kind == "Stacked":
            mines = [s for s in series if s != TOTAL_NAME] or a.mines
            bottom = pd.Series(0.0, index=d.index)
            for name in mines:
                height = drawn(d[name], smooth)
                ax.bar(d["Date"], height, bottom=bottom, width=0.82, color=colours[name], label=name, linewidth=0)
                bottom = bottom + height
                _flags(ax, a.detections[name].frame, bottom)
            if degree:
                ax.plot(d["Date"], fit_trend(bottom, degree).fitted, color=INK, ls=":", lw=1.6, label=f"Trend (degree {degree})")
        else:
            n = max(len(series), 1)
            width = 0.84 / n
            for i, name in enumerate(series):
                values = drawn(d[name], smooth)
                if kind == "Bar":
                    offset = pd.to_timedelta((i - (n - 1) / 2) * width, unit="D")
                    ax.bar(d["Date"] + offset, values, width=width, color=colours[name], label=name, linewidth=0)
                else:
                    ax.plot(d["Date"], values, color=colours[name], lw=1.3, label=name)
                if degree:
                    ax.plot(d["Date"], fit_trend(d[name], degree).fitted, color=colours[name], ls=":", lw=1.5)
                _flags(ax, a.detections[name].frame, values)
            if degree:
                ax.plot([], [], color=MUTED, ls=":", lw=1.5, label=f"Trend (degree {degree})")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Daily output")
        _legend(ax)
        return _image(fig)


HALF_W = CONTENT_W / 2 - 6


def _half_figure(title: str):
    fig, ax = plt.subplots(figsize=(HALF_W / 72, 2.45), layout="constrained")
    ax.set_title(title, loc="left", fontsize=8, color=INK, fontweight="bold", pad=16)
    return fig, ax


def share_figure(a: Analysis) -> Image:
    with plt.rc_context(MPL_STYLE):
        fig, ax = _half_figure("Total output by mine")
        totals = a.summary.loc[a.mines, "total"].sort_values()
        share = totals / totals.sum() * 100
        ax.barh(totals.index, totals, color=[a.colours[n] for n in totals.index], height=0.62)
        for y, (v, s) in enumerate(zip(totals, share)):
            ax.text(v, y, f"  {v:,.0f} ({s:.0f}%)", va="center", fontsize=7, color=INK_SECONDARY)
        ax.set_xlim(0, totals.max() * 1.35)
        ax.grid(False)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        return _image(fig, HALF_W, tight=False)


def weekday_figure(a: Analysis) -> Image:
    with plt.rc_context(MPL_STYLE):
        fig, ax = _half_figure("Weekday profile (1.0 = average day)")
        profile = a.weekday()[a.mines]
        n = len(profile.columns)
        width = 0.8 / n
        for i, name in enumerate(profile.columns):
            ax.bar([x + (i - (n - 1) / 2) * width for x in range(len(profile))], profile[name], width=width,
                   color=a.colours[name], linewidth=0, label=name)
        ax.axhline(1, color=MUTED, lw=0.8)
        ax.set_xticks(range(len(profile)), profile.index)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 0.99), ncol=4, fontsize=6.3, handlelength=0.9,
                  columnspacing=0.8, borderaxespad=0.1)
        return _image(fig, HALF_W, tight=False)


def series_figure(det: Detection, colour: str, kind: str, degree: int | None, window: int,
                  smooth: Choice | None) -> Image:
    f = det.frame
    values = drawn(f["value"], smooth)
    label = f"{det.series} (smoothed)" if smooth else det.series
    with plt.rc_context(MPL_STYLE):
        fig, ax = _figure(58)
        if kind == "Line":
            ax.plot(f["Date"], values, color=colour, lw=1.4, label=label)
        else:
            ax.bar(f["Date"], values, color=colour, width=0.8, lw=0, label=label)
        ax.plot(f["Date"], drawn(f["expected"], smooth), color=MUTED, lw=1, label=f"{window}-day average")
        if degree:
            trend = fit_trend(f["value"], degree)
            ax.plot(f["Date"], trend.fitted, color=INK, ls=":", lw=1.5, label=f"Trend (degree {degree}, R² {trend.r2:.2f})")
        single = f[(f["votes"] > 0) & ~f["anomaly"]]
        if len(single):
            ax.scatter(single["Date"], values.loc[single.index], s=22, facecolor="none", edgecolor=INK_SECONDARY,
                       lw=0.9, zorder=4, label="Below consensus")
        _flags(ax, f, values)
        ax.set_ylim(bottom=0)
        _legend(ax)
        return _image(fig)


def incident_figure(a: Analysis, incident: Incident, pad_days: int = 10) -> Image:
    lo, hi = incident.start - pd.Timedelta(days=pad_days), incident.end + pd.Timedelta(days=pad_days)
    mines = [s for s in incident.series if s != TOTAL_NAME]
    panels = [p for p in (mines, [TOTAL_NAME] if TOTAL_NAME in incident.series else []) if p]
    with plt.rc_context(MPL_STYLE):
        fig, axes = plt.subplots(len(panels), 1, sharex=True, squeeze=False,
                                 figsize=(CONTENT_W / 72, (52 if len(panels) == 1 else 74) / 25.4),
                                 gridspec_kw={"height_ratios": [1.7, 1][: len(panels)], "hspace": 0.12})
        for ax, names in zip(axes[:, 0], panels):
            _dates(ax)
            ax.axvspan(incident.start - pd.Timedelta(hours=12), incident.end + pd.Timedelta(hours=12), color=CRITICAL,
                       alpha=0.08, lw=0)
            for name in names:
                f = a.detections[name].frame
                f = f[(f["Date"] >= lo) & (f["Date"] <= hi)]
                ax.plot(f["Date"], f["value"], color=a.colours[name], lw=1.4, marker="o", ms=2.4, label=name)
                ax.plot(f["Date"], f["expected"], color=a.colours[name], lw=0.8, ls="--", alpha=0.6)
                _flags(ax, f[(f["Date"] >= incident.start) & (f["Date"] <= incident.end)], size=46)
            ax.set_ylim(bottom=0)
        top = axes[0, 0]
        for name in panels[-1] if len(panels) > 1 else []:
            top.plot([], [], color=a.colours[name], lw=1.4, marker="o", ms=2.4, label=f"{name} (lower panel)")
        top.plot([], [], color=MUTED, lw=0.8, ls="--", label="Moving average")
        _legend(top)
        return _image(fig)


def anomaly_map_figure(a: Analysis) -> Image:
    with plt.rc_context(MPL_STYLE):
        fig, ax = _figure(10 + 7 * len(a.series))
        for y, name in enumerate(reversed(a.series)):
            f = a.detections[name].frame
            ax.plot(f["Date"], [y] * len(f), color=GRID, lw=0.8, zorder=1)
            _flags(ax, f, pd.Series(float(y), index=f.index), size=34)
        ax.set_yticks(range(len(a.series)), list(reversed(a.series)))
        ax.set_ylim(-0.7, len(a.series) - 0.3)
        ax.grid(False)
        _legend(ax)
        return _image(fig)



def _cover(a: Analysis) -> list:
    total = a.summary.loc[TOTAL_NAME]
    spikes = sum(i.direction == "spike" for i in a.incidents)
    toc = TableOfContents(dotsMinLevel=0, levelStyles=[S["toc0"], S["toc1"]])
    return [
        Spacer(1, 4 * mm),
        _kpis([
            ("Total output", _num(total["total"], 0), f"{a.days} days, {len(a.mines)} mines"),
            ("Average per day", _num(total["mean"]), f"median {_num(total['median'])}"),
            ("Variability", f"{total['cv']:.1f}%", f"std dev {_num(total['std'])} (total)"),
            ("Anomaly incidents", str(len(a.incidents)), f"{spikes} spikes · {len(a.incidents) - spikes} drops"),
        ]),
        Spacer(1, 9 * mm),
        Paragraph("Contents", S["contents"]),
        toc,
        NextPageTemplate("body"),
        PageBreak(),
    ]


def _smoothing_note(smooth: Choice | None) -> str:
    return (f" Values are smoothed with {smooth.label}; anomalies come from tests on the raw data."
            if smooth else "")


def _summary_section(a: Analysis, kind: str, degree: int | None, series: list[str], smooth: Choice | None) -> list:
    out = [_h1(1, "Executive summary")]
    out += [Paragraph(line, S["lead"]) for line in a.headline()]
    out += [Spacer(1, 2 * mm), overview_figure(a, kind, degree, series, smooth),
            Paragraph(f"Daily output, {kind.lower()} chart{' with polynomial trendlines' if degree else ''}. "
                      "Red triangles mark anomalies (up = spike, down = drop) confirmed by the test consensus."
                      + _smoothing_note(smooth), S["caption"])]
    out += [Table([[share_figure(a), weekday_figure(a)]], colWidths=[CONTENT_W / 2] * 2,
                  style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)])]
    return out


def _stats_section(a: Analysis) -> list:
    head = ["Series", "Mean", "Std dev", "Median", "Q1", "Q3", "IQR", "Min", "Max", "CV %", "Total"]
    rows = [head]
    for name, r in a.summary.iterrows():
        rows.append([name, *[_num(r[c]) for c in ("mean", "std", "median", "q1", "q3", "iqr", "min", "max", "cv")],
                     _num(r["total"], 0)])
    widths = [CONTENT_W * 0.17] + [CONTENT_W * 0.083] * 10
    swatches = {i + 1: a.colours[n] for i, n in enumerate(a.summary.index)}
    trend_rows = [["Series", "Linear slope / day", "Change over period", "R² (linear)", "R² (degree 3)"]]
    for name in a.series:
        lin, cubic = fit_trend(a.data[name], 1), fit_trend(a.data[name], 3)
        trend_rows.append([name, f"{lin.coefficients[1]:+,.3f}" if len(lin.coefficients) > 1 else "-",
                           f"{lin.change_pct:+.1f}%", f"{lin.r2:.3f}", f"{cubic.r2:.3f}"])
    return [
        _h1(2, "Output statistics"),
        Paragraph("Daily output per mine and for the whole operation. Quartiles use linear interpolation; "
                  "standard deviation is the sample estimate (n - 1); CV is the standard deviation as a share of the mean.",
                  S["body"]),
        _table(rows, widths, swatches=swatches, bold_last=True),
        Spacer(1, 6 * mm),
        Paragraph("Trend", S["h3"]),
        _table(trend_rows, [CONTENT_W * 0.2] + [CONTENT_W * 0.2] * 4, swatches=swatches),
        Paragraph("Slope and change come from a least-squares line through the daily values; R² shows how much of "
                  "the day-to-day variation each polynomial explains.", S["caption"]),
    ]


def _detection_section(a: Analysis) -> list:
    s = a.settings
    params = [["Test", "Rule"]] + [[name, rule] for name, rule in s.describe()]
    counts = [["Series", *TESTS.values(), "Anomalies", "Spikes", "Drops"]]
    for name, r in a.counts.iterrows():
        counts.append([name, *[str(int(r[c])) for c in [*TESTS.values(), "Anomalies", "Spikes", "Drops"]]])
    out = [
        _h1(3, "Anomaly detection"),
        Paragraph("Each series is checked by four independent tests. A day counts as an anomaly when enough tests agree; "
                  "consecutive anomalous days form an episode, and episodes of different series that overlap in time "
                  "and point the same way are reported together as one incident (section 5).", S["body"]),
        _table(params, [CONTENT_W * 0.22, CONTENT_W * 0.78], numeric_from=99),
        Spacer(1, 5 * mm),
        KeepTogether([
            Paragraph("Days flagged per test", S["h3"]),
            _table(counts, [CONTENT_W * 0.2] + [CONTENT_W * 0.8 / 7] * 7,
                   swatches={i + 1: a.colours[n] for i, n in enumerate(a.counts.index)}),
            Paragraph("Per-test columns count every flag; the anomaly columns count only days that reached the consensus.",
                      S["caption"]),
        ]),
        KeepTogether([Paragraph("Anomaly map", S["h3"]), anomaly_map_figure(a),
                      Paragraph("Confirmed anomalies of every series on one timeline.", S["caption"])]),
    ]
    if a.planned is not None and not a.planned.empty:
        out += _planned_table(a)
    return out


def _planned_table(a: Analysis) -> list:
    rows = [["#", "Day", "Days", "Factor", "Probability", "Mines", "Affected", "Detected as"]]
    for n, ev in a.planned.reset_index(drop=True).iterrows():
        label = f"Generator event {n + 1}:"
        found = [f"incident {i.number}" for i in a.incidents if i.planned and i.planned.startswith(label)]
        rows.append([str(n + 1), f"{ev['Day']:%Y-%m-%d}", _num(ev.get("Duration"), 0), _num(ev.get("Factor"), 2),
                     _num(ev.get("Probability"), 2), _num(ev.get("Mines"), 0), str(ev.get("Affected") or "-"),
                     ", ".join(found) or "not detected"])
    widths = [CONTENT_W * w for w in (0.05, 0.12, 0.07, 0.08, 0.1, 0.07, 0.33, 0.18)]
    return [KeepTogether([
        Paragraph("Configured generator events", S["h3"]),
        _table(rows, widths, numeric_from=1, text_cols=(6, 7)),
        Paragraph("Events set on the Generator sheet, compared with what the tests found. Events with a small factor "
                  "change or low probability can stay inside normal variation and go undetected.", S["caption"]),
    ])]


def _profiles_section(a: Analysis, kind: str, degree: int | None, smooth: Choice | None) -> list:
    out = [PageBreak(), _h1(4, "Mine profiles")]
    if smooth:
        out.append(Paragraph(f"Charts in this section are smoothed with {smooth.label}. Statistics, markers and the "
                             "tables of anomalous days use the raw daily values.", S["body"]))
    for name in a.series:
        det, r = a.detections[name], a.summary.loc[name]
        anomalies = det.anomalies
        block = [
            _h2(name, toc=True),
            Paragraph(f"Mean <b>{_num(r['mean'])}</b> · std dev <b>{_num(r['std'])}</b> · median <b>{_num(r['median'])}</b> · "
                      f"IQR <b>{_num(r['iqr'])}</b> ({_num(r['q1'])} - {_num(r['q3'])}) · range {_num(r['min'])} - "
                      f"{_num(r['max'])} · {len(anomalies)} anomalous day(s)", S["body"]),
            series_figure(det, a.colours[name], "Bar" if kind == "Bar" else "Line", degree, a.settings.ma_window, smooth),
        ]
        if len(anomalies):
            rows = [["Date", "Type", "Value", "Expected", "Deviation", "z", "Tests"]]
            for _, p in anomalies.iterrows():
                rows.append([f"{p['Date']:%Y-%m-%d} ({p['Date']:%a})", p["direction"].capitalize(), _num(p["value"]),
                             _num(p["expected"]), f"{p['deviation_pct']:+.1f}%", f"{p['z']:+.2f}",
                             ", ".join(label for t, label in TESTS.items() if p[t])])
            widths = [CONTENT_W * w for w in (0.17, 0.08, 0.09, 0.1, 0.1, 0.07, 0.39)]
            block.append(_table(rows, widths, numeric_from=2, text_cols=(6,)))
        else:
            block.append(Paragraph("No anomalies reached the consensus for this series.", S["caption"]))
        out += [CondPageBreak(95 * mm), *block, Spacer(1, 4 * mm)]
    return out


def _incident_block(a: Analysis, incident: Incident) -> list:
    direction = "above" if incident.direction == "spike" else "below"
    tests = sorted({t for e in incident.episodes for t in e.tests}, key=list(TESTS.values()).index)
    meta = [
        ["Type", incident.direction.capitalize(), "Period", incident.title.split(" ", 1)[1]],
        ["Duration", f"{incident.days} day(s)", "Peak deviation", f"{incident.peak_deviation:+.1f}%"],
        ["Series", ", ".join(incident.series), "Tests", ", ".join(tests)],
    ]
    meta_rows = [[Paragraph(f"<b>{c}</b>" if i % 2 == 0 else c, S["cell"]) for i, c in enumerate(row)] for row in meta]
    meta_table = Table(meta_rows, colWidths=[CONTENT_W * w for w in (0.13, 0.37, 0.15, 0.35)], hAlign="LEFT")
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), STRIPE), ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(CRITICAL)),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    cause = (f"It overlaps <b>{incident.planned}</b>." if incident.planned
             else "No configured generator event covers these days, so it is natural variation or an unplanned event.")
    worst = max(incident.episodes, key=lambda e: abs(e.peak["deviation_pct"]))
    story = (f"Output of {', '.join(incident.series)} moved up to {abs(incident.peak_deviation):.1f}% {direction} the "
             f"{a.settings.ma_window}-day moving average. The strongest reading was {worst.series} on "
             f"{worst.peak['Date']:%Y-%m-%d}: {_num(worst.peak['value'])} against an expected {_num(worst.peak['expected'])}. "
             + cause)
    rows = [["Date", "Series", "Value", "Expected", "Deviation", "z", "Tests"]]
    for ep in incident.episodes:
        for _, p in ep.rows.iterrows():
            rows.append([f"{p['Date']:%Y-%m-%d}", ep.series, _num(p["value"]), _num(p["expected"]),
                         f"{p['deviation_pct']:+.1f}%", f"{p['z']:+.2f}", ", ".join(l for t, l in TESTS.items() if p[t])])
    widths = [CONTENT_W * w for w in (0.12, 0.15, 0.09, 0.1, 0.1, 0.07, 0.37)]
    return [
        CondPageBreak(120 * mm),
        KeepTogether([_h2(f"Incident {incident.number}  ·  {incident.title}", toc=True), meta_table, Spacer(1, 3 * mm),
                      Paragraph(story, S["body"]), incident_figure(a, incident)]),
        Spacer(1, 2 * mm),
        _table(rows, widths, numeric_from=2, text_cols=(6,)),
        Spacer(1, 7 * mm),
    ]


def _incidents_section(a: Analysis, smooth: Choice | None) -> list:
    out = [PageBreak(), _h1(5, "Anomaly incidents")]
    if not a.incidents:
        return out + [Paragraph("No anomalies reached the consensus with the current test settings.", S["body"])]
    raw = " Close-ups show the raw daily readings; smoothing would hide the events they document." if smooth else ""
    out.append(Paragraph(f"{len(a.incidents)} incident(s), in date order. Each section lists the affected series, "
                         "the tests that fired and the readings around the event; the shaded band marks the incident days "
                         "and dashed lines the moving average each series was compared with." + raw, S["body"]))
    for incident in a.incidents:
        out += _incident_block(a, incident)
    return out


def _appendix(a: Analysis, smooth: Choice | None) -> list:
    s = a.settings
    method = [
        ("Weekday adjustment", "Each value is divided by the median output of its weekday relative to the overall median, "
                               "so planned weekend slowdowns are not reported as drops." if s.weekday_adjust else
                               "Off: tests run on raw daily values, so weekly patterns can trigger flags."),
        ("IQR rule", f"Q1 and Q3 are the 25th and 75th percentiles. Values below Q1 - {s.iqr_k:g} x IQR or above "
                     f"Q3 + {s.iqr_k:g} x IQR are outliers (Tukey fences)."),
        ("Z-score", f"z = (x - mean) / standard deviation over the whole period; |z| > {s.z_threshold:g} is an outlier."),
        ("Moving average", f"Expected value = mean of the {s.ma_window} {'surrounding' if s.ma_centered else 'previous'} "
                           f"days, excluding the day itself. Flag when |x - expected| / expected > {s.ma_pct:g}%."),
        ("Grubbs' test", f"G = max |x - mean| / sd is compared with the critical value for n values at alpha = "
                         f"{s.grubbs_alpha:g} (Student t based). The most extreme value is removed and the test repeats "
                         "until G falls below the critical value."),
        ("Consensus", f"A day is an anomaly when at least {s.votes_needed} enabled test(s) flag it. Direction (spike or drop) "
                      "follows the sign of the deviation from the moving average."),
        ("Trendlines", "Least-squares polynomial of the chosen degree fitted to the daily values against the day number."),
        ("Chart smoothing", f"{smooth.label}, applied to the overview and profile charts only (values below zero are "
                            "cut off). Tests, statistics and tables use raw values." if smooth else "Off: charts show raw values."),
    ]
    out = [PageBreak(), _h1(6, "Appendix")]
    out += [Paragraph("A. Methodology", S["h2"])]
    out += [_table([["Item", "Definition"], *[[k, v] for k, v in method]], [CONTENT_W * 0.2, CONTENT_W * 0.8], numeric_from=99)]
    head = ["Date", *a.series]
    rows = [head] + [[f"{r['Date']:%Y-%m-%d} {r['Date']:%a}", *[_num(r[c]) for c in a.series]]
                     for _, r in a.data.iterrows()]
    alerts = {(int(r) + 1, c) for c, name in enumerate(a.series, start=1)
              for r in a.detections[name].frame.index[a.detections[name].frame["anomaly"]]}
    first = CONTENT_W * 0.18
    rest = (CONTENT_W - first) / (len(head) - 1)
    out += [Paragraph("B. Daily data", S["h2"]),
            Paragraph("Values in red are anomalies confirmed by the test consensus.", S["caption"]),
            _table(rows, [first] + [rest] * (len(head) - 1), font_size=6.8, alerts=alerts)]
    return out


def build_report(a: Analysis, *, kind: str = "Line", degree: int | None = 1, series: list[str] | None = None,
                 source: str = "Google Sheets", generated: datetime | None = None, smooth: Choice | None = None) -> bytes:
    """smooth: the smoother chosen in the app; the overview and profile charts are drawn with it, like on screen."""
    buffer = io.BytesIO()
    doc = ReportDoc(buffer, a, source, generated or datetime.now())
    series = series or a.mines
    story = [
        *_cover(a),
        *_summary_section(a, kind, degree, series, smooth),
        PageBreak(),
        *_stats_section(a),
        Spacer(1, 4 * mm),
        *_detection_section(a),
        *_profiles_section(a, kind, degree, smooth),
        *_incidents_section(a, smooth),
        *_appendix(a, smooth),
    ]
    doc.multiBuild(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
