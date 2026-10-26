import re
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mining import source
from mining.analysis import analyze
from mining.anomalies import Settings
from mining.report import build_report
from mining.simulator import Params, generate, planned_events
from mining.stats import fit_trend, summarize

SHEET = Path(__file__).resolve().parents[1] / "sheet"


def test_summary_statistics():
    s = summarize("x", pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8]))
    assert (s.mean, s.median, s.q1, s.q3, s.iqr) == (4.5, 4.5, 2.75, 6.25, 3.5)
    assert s.std == pytest.approx(2.449, abs=0.001)
    assert s.total == 36


@pytest.mark.parametrize("degree", [1, 2, 3, 4])
def test_trend_recovers_exact_polynomial(degree):
    x = np.arange(60.0)
    y = pd.Series(sum((0.5 / (k + 1) ** 3) * x ** k for k in range(degree + 1)) + 10)
    trend = fit_trend(y, degree)
    assert trend.r2 == pytest.approx(1.0)
    assert np.allclose(trend.fitted, y)


@pytest.mark.parametrize("url", [
    "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-ab/edit?usp=sharing",
    "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-ab/edit#gid=0",
    "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-ab",
])
def test_sheet_links(url):
    assert source.sheet_id(url) == "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-ab"
    assert source.csv_url(url).endswith("/gviz/tq?tqx=out:csv&headers=1&sheet=Data")


def test_bad_link_and_published_csv_link():
    with pytest.raises(source.SourceError):
        source.sheet_id("https://example.com/table")
    published = "https://docs.google.com/spreadsheets/d/e/2PACX-abc/pub?gid=1&single=true&output=csv"
    assert source.csv_url(published) == published


def test_parse_table_recomputes_total_and_skips_empty_columns():
    text = 'Date,Total,LV-426,Origae-6,,\n2099-11-02,999,"1,050.5",20\n2099-11-03,999,30,\n,1,2,3\n'
    data = source.parse_table(text)
    assert list(data.columns) == ["Date", "Total", "LV-426", "Origae-6"]
    assert data["Total"].tolist() == [1070.5, 30.0]
    assert len(data) == 2


def test_parse_events():
    events = source.parse_events("Day,Duration,Factor,Probability,Mines,Affected mines\n"
                                 "2099-11-10,3,0.4,1,,LV-426\n,,,,,\n2099-12-14,4,1.6,,2,\"A, B\"\n")
    assert events["Day"].dt.strftime("%Y-%m-%d").tolist() == ["2099-11-10", "2099-12-14"]
    assert events["Mines"].isna().tolist() == [True, False]


def test_pdf_report_builds():
    a = analyze(generate(), Settings(), planned_events())
    pdf = build_report(a, kind="Stacked", degree=3, source="test")
    assert pdf.startswith(b"%PDF") and len(pdf) > 100_000
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) >= 10


def test_pdf_report_without_anomalies():
    quiet = generate(replace(Params(), events=(), days=40))
    a = analyze(quiet, Settings(tests=("grubbs",), grubbs_alpha=0.001), None)
    assert build_report(a, kind="Bar", degree=None).startswith(b"%PDF")


@pytest.mark.skipif(not SHEET.exists(), reason="sheet/ is kept out of the repository")
def test_formula_doc_matches_builder():
    gs = (SHEET / "build_sheet.gs").read_text(encoding="utf-8")
    doc = (SHEET / "formulas.md").read_text(encoding="utf-8")
    for name in ("DATA_FORMULA", "IMPACT_FORMULA", "CHECK_FORMULA"):
        body = re.search(rf"const {name} = `(.*?)`;", gs, re.S).group(1).replace("${MAX_DAYS}", "1000")
        assert body in doc, name
