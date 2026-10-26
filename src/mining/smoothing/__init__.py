import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    low: float
    high: float
    default: float
    step: float
    help: str = ""

    def describe(self, value: float) -> str:
        name, _, unit = self.label.partition(", ")
        return f"{name.lower()} {value:g}" + (f" {unit}" if unit else "")


@dataclass(frozen=True)
class Smoother:
    name: str
    order: int
    params: tuple[Param, ...]
    module: ModuleType

    def apply(self, values: pd.Series | np.ndarray, **params) -> np.ndarray:
        y = np.asarray(values, dtype=float)
        return y.copy() if len(y) < 3 else np.asarray(self.module.smooth(y, **params), dtype=float)


@dataclass(frozen=True)
class Choice:
    smoother: Smoother
    values: tuple[tuple[str, float], ...]

    def __call__(self, series: pd.Series | np.ndarray) -> np.ndarray:
        return self.smoother.apply(series, **dict(self.values))

    @property
    def label(self) -> str:
        chosen = dict(self.values)
        details = ", ".join(p.describe(chosen[p.key]) for p in self.smoother.params)
        return f"{self.smoother.name} ({details})" if details else self.smoother.name


def drawn(series: pd.Series, choice: Choice | None) -> pd.Series:
    """Values a chart draws: smoothed (never below zero) when a smoother is chosen, otherwise the raw series."""
    if choice is None:
        return series
    gaps = series.isna()
    if gaps.all():
        return series
    filled = series.interpolate(limit_direction="both") if gaps.any() else series  # filters spread NaN otherwise
    out = pd.Series(np.clip(choice(filled), 0, None), index=series.index, name=series.name)
    return out.mask(gaps)


def available() -> dict[str, Smoother]:
    found = []
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "NAME") and hasattr(module, "smooth"):
            found.append(Smoother(module.NAME, getattr(module, "ORDER", 99), tuple(getattr(module, "PARAMS", ())), module))
    return {s.name: s for s in sorted(found, key=lambda s: (s.order, s.name))}
