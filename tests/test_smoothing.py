import numpy as np
import pytest

from mining.smoothing import Choice, available

SMOOTHERS = list(available().values())  # tests follow the files in mining/smoothing, so deleting one is safe


def defaults(smoother) -> Choice:
    return Choice(smoother, tuple((p.key, p.default) for p in smoother.params))


@pytest.fixture
def noisy_wave():
    t = np.arange(120.0)
    clean = 50 + 10 * np.sin(2 * np.pi * t / 60)
    return clean, clean + np.random.default_rng(4).normal(0, 4, len(t))


def test_registry_finds_smoothers_in_order():
    assert SMOOTHERS, "mining/smoothing has no smoother modules"
    assert [s.order for s in SMOOTHERS] == sorted(s.order for s in SMOOTHERS)


@pytest.mark.parametrize("smoother", SMOOTHERS, ids=lambda s: s.name)
def test_smoothing_reduces_noise_and_keeps_length(smoother, noisy_wave):
    clean, noisy = noisy_wave
    smoothed = defaults(smoother)(noisy)
    assert smoothed.shape == noisy.shape
    assert np.abs(smoothed - clean).mean() < 0.6 * np.abs(noisy - clean).mean()


@pytest.mark.parametrize("smoother", SMOOTHERS, ids=lambda s: s.name)
def test_constant_series_stays_constant(smoother):
    assert np.allclose(defaults(smoother)(np.full(40, 7.5)), 7.5)


@pytest.mark.parametrize("smoother", SMOOTHERS, ids=lambda s: s.name)
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 8])
def test_short_series_do_not_fail(smoother, n):
    values = np.arange(n, dtype=float)
    assert len(defaults(smoother)(values)) == n


@pytest.mark.parametrize("smoother", SMOOTHERS, ids=lambda s: s.name)
def test_parameter_extremes(smoother, noisy_wave):
    _, noisy = noisy_wave
    for pick in ("low", "high"):
        choice = Choice(smoother, tuple((p.key, getattr(p, pick)) for p in smoother.params))
        assert np.isfinite(choice(noisy)).all()


@pytest.fixture(scope="module")
def analysis():
    from mining.analysis import analyze
    from mining.anomalies import Settings
    from mining.simulator import generate

    return analyze(generate(), Settings())


@pytest.mark.parametrize("kind", ["Line", "Bar", "Stacked"])
def test_charts_draw_only_smoothed_values_with_raw_in_hover(kind, analysis):
    from mining.charts import overview_chart

    a, choice = analysis, defaults(SMOOTHERS[0])
    fig = overview_chart(a.data, a.mines, kind, None, a.detections, a.colours, choice)
    drawn_series = {t.name: t for t in fig.data if t.name in a.mines}
    assert sorted(drawn_series) == sorted(a.mines)  # one trace per mine: no raw copies
    assert len([t for t in fig.data if t.name in a.mines]) == len(a.mines)
    for name, trace in drawn_series.items():
        assert np.allclose(trace.y, np.clip(choice(a.data[name]), 0, None))
        assert np.allclose(trace.customdata, a.data[name])  # raw value kept for the hover


@pytest.mark.parametrize("kind", ["Line", "Bar"])
def test_anomaly_markers_sit_on_smoothed_values(kind, analysis):
    from mining.charts import overview_chart

    a, choice = analysis, defaults(SMOOTHERS[0])
    fig = overview_chart(a.data, a.mines, kind, None, a.detections, a.colours, choice)
    expected = {}
    for name in a.mines:
        anomalies = a.detections[name].anomalies
        smoothed = np.clip(choice(a.data[name]), 0, None)
        for i in anomalies.index:
            expected[(name, a.data["Date"][i])] = smoothed[i]
    markers = [t for t in fig.data if t.name in ("Spike", "Drop")]
    found = {(c[0], x): y for t in markers for x, y, c in zip(t.x, t.y, t.customdata)}
    assert found.keys() == expected.keys()
    assert all(np.isclose(found[k], expected[k]) for k in expected)


def test_drawn_keeps_gaps_and_raw_without_smoother():
    from mining.smoothing import drawn
    import pandas as pd

    series = pd.Series([np.nan, 5.0, 6, 5, 6, 5, 6, 5, 6, np.nan])
    assert drawn(series, None) is series
    out = drawn(series, defaults(SMOOTHERS[0]))
    assert out.isna().tolist() == series.isna().tolist()
    assert out.notna().sum() == 8 and (out.dropna() >= 0).all()


def test_pdf_report_with_smoothing(analysis):
    from mining.report import build_report

    pdf = build_report(analysis, kind="Stacked", degree=2, smooth=defaults(SMOOTHERS[-1]))
    assert pdf.startswith(b"%PDF") and len(pdf) > 100_000


def test_label_names_parameters_with_units():
    smoother = next(iter(available().values()))
    label = defaults(smoother).label
    assert label.startswith(smoother.name)
    for p in smoother.params:
        assert p.label.partition(", ")[0].lower() in label
