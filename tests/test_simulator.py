from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from mining.simulator import Event, Params, generate, impact_matrix, planned_events, sheet_round

QUIET = Params(days=200, weekday=(1,) * 7, growth=0.0, events=(), sizes=(1, 1, 1, 1))


def test_table_shape_and_total():
    p = Params()
    data = generate(p)
    assert list(data.columns) == ["Date", "Total", *p.mines]
    assert len(data) == p.days
    assert data["Date"].iloc[0].date() == p.start
    assert (data[list(p.mines)] >= 0).all().all()
    assert np.allclose(data["Total"], data[list(p.mines)].sum(axis=1), atol=0.051)


def test_same_seed_same_data_and_new_seed_new_data():
    assert generate().equals(generate())
    assert not generate().equals(generate(replace(Params(), seed=7)))


def test_sheet_round_is_half_away_from_zero():
    assert sheet_round(2.25) == 2.3
    assert sheet_round(-2.25) == -2.3
    assert sheet_round(0.05) == 0.1


def test_uniform_stays_inside_min_max_with_any_smoothing():
    data = generate(replace(QUIET, distribution="Uniform", param_a=30, param_b=70, smoothing=0.9))
    values = data[list(QUIET.mines)]
    assert values.min().min() >= 30 and values.max().max() <= 70


def test_lognormal_matches_requested_mean_and_is_positive():
    data = generate(replace(QUIET, distribution="Lognormal", param_a=50, param_b=10, smoothing=0, days=800))
    values = data[list(QUIET.mines)].to_numpy()
    assert values.min() > 0
    assert values.mean() == pytest.approx(50, rel=0.05)


def test_smoothing_adds_day_to_day_correlation():
    def lag1(p):
        series = generate(p)["LV-426"]
        return series.autocorr(1)

    assert abs(lag1(replace(QUIET, smoothing=0.0))) < 0.2
    assert lag1(replace(QUIET, smoothing=0.8)) > 0.6


def test_mine_link_correlates_mines():
    def cross(p):
        data = generate(p)
        return data["LV-426"].corr(data["Origae-6"])

    assert abs(cross(replace(QUIET, mine_link=0.0))) < 0.25
    assert cross(replace(QUIET, mine_link=0.9)) > 0.75


def test_weekday_factor_and_growth():
    p = replace(QUIET, weekday=(1, 1, 1, 1, 1, 1, 0.5), growth=0.005, days=210)
    data = generate(p)
    sunday = data[data["Date"].dt.day_of_week == 6]["Total"].mean()
    other = data[data["Date"].dt.day_of_week < 6]["Total"].mean()
    assert sunday / other == pytest.approx(0.5, abs=0.08)
    first, last = data["Total"].head(30).mean(), data["Total"].tail(30).mean()
    assert last / first > 2


def test_event_drop_hits_all_mines_with_probability_one():
    p = replace(QUIET, events=(Event(date(2099, 12, 1), 3, 0.3, 1.0),))
    data = generate(p).set_index("Date")
    during = data.loc["2099-12-01":"2099-12-03", "Total"].mean()
    before = data.loc["2099-11-15":"2099-11-25", "Total"].mean()
    assert during / before < 0.45
    assert impact_matrix(p).sum() == len(p.mines)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_mines_count_hits_exactly_that_many(count):
    p = replace(Params(), events=(Event(date(2099, 12, 1), 2, 1.5, None, count),))
    assert impact_matrix(p).sum() == count


def test_probability_zero_hits_nobody_and_planned_table_lists_hits():
    p = replace(Params(), events=(Event(date(2099, 12, 1), 2, 1.5, 0.0), Event(date(2099, 12, 9), 1, 0.5, 1.0)))
    assert impact_matrix(p)[0].sum() == 0
    table = planned_events(p)
    assert table.loc[0, "Affected"] == "none"
    assert table.loc[1, "Affected"] == ", ".join(p.mines)
