SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
EXTRA = "#898781"  
TOTAL = "#3d3c38"

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
BAND = "rgba(137, 135, 129, 0.13)"

CRITICAL = "#d03b3b"  
WARNING = "#fab219"
GOOD = "#0ca30c"

BRAND = "#0f1f2e" 
BRAND_ACCENT = "#c8a24a"

TOTAL_NAME = "Total"


def colour_map(mines: list[str]) -> dict[str, str]:
    colours = {name: SERIES[i] if i < len(SERIES) else EXTRA for i, name in enumerate(mines)}
    colours[TOTAL_NAME] = TOTAL
    return colours


def rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"
