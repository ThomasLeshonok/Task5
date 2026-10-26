import numpy as np
from scipy.signal import savgol_filter

from mining.smoothing import Param

NAME = "Savitzky-Golay"
ORDER = 1
PARAMS = (
    Param("window", "Window, days", 5, 31, 11, 2, "Odd number of days in each local fit. Wider is smoother."),
    Param("polyorder", "Polynomial order", 1, 5, 3, 1, "Degree of the local fit. Higher keeps spikes sharper."),
)


def smooth(values: np.ndarray, window: int = 11, polyorder: int = 3) -> np.ndarray:
    n = len(values)
    window = int(window) | 1
    window = min(window, n if n % 2 else n - 1)
    polyorder = min(int(polyorder), window - 1)
    return savgol_filter(values, window, polyorder, mode="interp")
