import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np
import pandas as pd

DISTRIBUTIONS = ("Normal", "Uniform", "Lognormal")
STANDARD = NormalDist()


@dataclass(frozen=True)
class Event:
    day: date
    duration: int = 1
    factor: float = 1.0
    probability: float | None = 1.0
    mines: int | None = None


@dataclass(frozen=True)
class Params:
    start: date = date(2099, 11, 2)
    days: int = 120
    mines: tuple[str, ...] = ("LV-426", "Origae-6", "Fiorina 161", "LV-223")
    sizes: tuple[float | None, ...] = (1.0, 1.4, 0.7, 1.1)
    distribution: str = "Normal"
    param_a: float = 50.0  
    param_b: float = 7.0  
    smoothing: float = 0.7
    mine_link: float = 0.35
    seed: int = 2099
    weekday: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0, 1.0, 0.8, 0.6)
    growth: float = 0.002
    events: tuple[Event, ...] = field(default_factory=lambda: (
        Event(date(2099, 11, 10), 3, 0.4, 1.0),
        Event(date(2099, 11, 20), 1, 1.4, 0.33),
        Event(date(2099, 12, 14), 4, 1.6, None, 2),
        Event(date(2100, 1, 18), 2, 0.3, 0.5),
        Event(date(2100, 2, 6), 1, 1.8, 0.5),
    ))


def sheet_hash(x: float, y: float, salt: float, seed: float) -> float:
    return math.fmod(abs(math.sin(x * 12.9898 + y * 78.233 + salt * 37.719 + seed * 0.618034)) * 43758.5453, 1.0)


def gauss(u: float) -> float:
    return STANDARD.inv_cdf(min(max(u, 1e-6), 1 - 1e-6))


def sheet_round(value: float, digits: int = 1) -> float:
    scale = 10 ** digits
    return math.copysign(math.floor(abs(value) * scale + 0.5) / scale, value)


def impact_matrix(p: Params) -> np.ndarray:
    k = len(p.mines)
    hits = np.zeros((len(p.events), k))
    for e, ev in enumerate(p.events, start=1):
        keys = [sheet_hash(e, m, 3, p.seed) for m in range(1, k + 1)]
        for m, key in enumerate(keys):
            if ev.mines is not None:
                hits[e - 1, m] = 1 + sum(other < key for other in keys) <= ev.mines
            else:
                hits[e - 1, m] = key < (1.0 if ev.probability is None else ev.probability)
    return hits


def latent(p: Params) -> np.ndarray:
    phi = min(max(p.smoothing, 0.0), 0.99)
    rho = min(max(p.mine_link, 0.0), 1.0)
    out = np.zeros((p.days, len(p.mines)))
    for m in range(1, len(p.mines) + 1):
        prev = 0.0
        for t in range(1, p.days + 1):
            shock = math.sqrt(rho) * gauss(sheet_hash(t, 0, 1, p.seed)) + math.sqrt(1 - rho) * gauss(sheet_hash(t, m, 2, p.seed))
            prev = shock if t == 1 else phi * prev + math.sqrt(1 - phi ** 2) * shock
            out[t - 1, m - 1] = prev
    return out


def base_values(z: np.ndarray, p: Params) -> np.ndarray:
    a, b = p.param_a, p.param_b
    if p.distribution == "Uniform":
        return a + (b - a) * np.vectorize(STANDARD.cdf)(z)
    if p.distribution == "Lognormal":
        s2 = math.log(1 + (b / a) ** 2)
        return np.exp(math.log(a) - s2 / 2 + math.sqrt(s2) * z)
    return a + b * z


def pulses(p: Params) -> np.ndarray:
    out = np.zeros((p.days, len(p.events)))
    for e, ev in enumerate(p.events):
        dur = max(1, ev.duration)
        factor = max(ev.factor, 0.01)
        centre = ev.day.toordinal() + (dur - 1) / 2
        for t in range(p.days):
            offset = (p.start.toordinal() + t - centre) / (dur / 2)
            out[t, e] = math.log(1 + (factor - 1) / (1 + offset ** 4))
    return out


def generate(p: Params = Params()) -> pd.DataFrame:
    days = [p.start + timedelta(days=t) for t in range(p.days)]
    sizes = np.array([1.0 if s is None else s for s in p.sizes[: len(p.mines)]])
    weekday = np.array([p.weekday[d.weekday()] for d in days])[:, None]
    growth = ((1 + p.growth) ** np.arange(p.days))[:, None]
    events = np.exp(pulses(p) @ impact_matrix(p))
    raw = base_values(latent(p), p) * sizes[None, :] * weekday * growth * events
    output = np.vectorize(sheet_round)(raw).clip(min=0)
    frame = pd.DataFrame(output, columns=list(p.mines))
    frame.insert(0, "Total", np.vectorize(sheet_round)(output.sum(axis=1)))
    frame.insert(0, "Date", pd.to_datetime(days))
    return frame


def planned_events(p: Params = Params()) -> pd.DataFrame:
    hits = impact_matrix(p)
    rows = []
    for e, ev in enumerate(p.events):
        hit = [name for name, flag in zip(p.mines, hits[e]) if flag]
        rows.append({
            "Day": pd.Timestamp(ev.day), "Duration": ev.duration, "Factor": ev.factor,
            "Probability": ev.probability, "Mines": ev.mines, "Affected": ", ".join(hit) or "none",
        })
    return pd.DataFrame(rows)
