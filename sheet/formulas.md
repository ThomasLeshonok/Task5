# Mining Ops Simulator: Google Sheet formulas

The data source is a Google Sheet with three tabs. Every number in it comes from formulas in cells; no script
runs when parameters change. `build_sheet.gs` only lays the sheet out once (cells, named ranges, formatting,
validation, charts) so it can be rebuilt identically.

| Tab | Role |
|-----|------|
| `Generator` | Parameter table (layout from the brief), validation message, two charts |
| `Impact` | Which mine each event hits (one spilled formula) |
| `Data` | The generated table `Date, Total, <mine 1>, <mine 2>, ...` (one spilled formula). The dashboard reads this tab |

## Generator layout

| Cell(s) | Content | Default |
|---------|---------|---------|
| A1:I1 | Title | Weyland-Yutani Corporation |
| A2:I2 | Header | Mining Ops Simulator |
| B4, C4 | Start date, Days count (1-1000) | 2099-11-02, 120 |
| D4 | End date (formula) | `=StartDate+DaysCount-1` |
| B5:Z5 | Mine names, one per cell; add or delete freely | LV-426, Origae-6, Fiorina 161, LV-223 |
| B6:Z6 | Capacity of each mine (relative size, empty = 1) | 1, 1.4, 0.7, 1.1 |
| B8 | Distribution: Normal, Uniform or Lognormal (dropdown) | Normal |
| C7:D7 | Parameter labels, switch with the distribution (formulas) | Mean / Deviation, or Min / Max |
| C8, D8 | Distribution parameters | 50, 7 |
| E8 | Smoothing: day-to-day autocorrelation, 0-0.99 | 0.6 |
| F8 | Mine link: share of the daily shock common to all mines, 0-1 | 0.35 |
| G8 | Seed: change it for a new scenario | 2099 |
| H8:I8 | Hint for the chosen distribution (formula) | |
| B10:H10 | Weekday factors Mon-Sun | 1, 1, 1, 1, 1, 0.8, 0.6 |
| B11 | Daily growth (compound), F11 shows the total effect | 0.2% |
| B13:F18 | Six events: Day, Duration, Factor, Probability, Mines | five filled |
| G13:G18 | Mines each event hits (formula) | |
| B19:I19 | Parameter check (formula) | ✓ Ready ... |

Charts on `Generator` (from row 21): "Daily output by mine" (line, `Data!A:A` + `Data!C:Z`) and
"Total daily output with linear trend" (column chart of `Data!A:B` with a trendline). Both read whole columns,
so they follow every parameter change, including more or fewer days and mines.

## Named ranges

| Name | Range | Name | Range |
|------|-------|------|-------|
| `StartDate` | Generator!B4 | `Seed` | Generator!G8 |
| `DaysCount` | Generator!C4 | `WeekdayFactors` | Generator!B10:H10 |
| `MineNames` | Generator!B5:Z5 | `DailyGrowth` | Generator!B11 |
| `MineSize` | Generator!B6:Z6 | `EventDay` | Generator!B13:B18 |
| `Distribution` | Generator!B8 | `EventDuration` | Generator!C13:C18 |
| `ParamA` | Generator!C8 | `EventFactor` | Generator!D13:D18 |
| `ParamB` | Generator!D8 | `EventProb` | Generator!E13:E18 |
| `Smoothing` | Generator!E8 | `EventMines` | Generator!F13:F18 |
| `MineLink` | Generator!F8 | | |

## How the numbers are made

For mine *m* on day *t* (day 1 = start date):

```
output[t,m] = max(0, round( base[t,m] * capacity[m] * weekday[t] * (1 + growth)^(t-1) * events[t,m], 1))
```

1. **Random numbers.** `rnd(x, y, salt) = frac(|sin(12.9898x + 78.233y + 37.719salt + 0.618034Seed)| * 43758.5453)`,
   a deterministic hash in [0, 1). Unlike `RAND()` it does not change on every edit; the same Seed always gives
   the same data. `zOf(u) = NORMSINV(u)` turns it into a standard normal value.
2. **Correlated noise (smoothing).** Each day's shock mixes a part shared by all mines with a part of its own,
   `shock = sqrt(MineLink) * common_t + sqrt(1 - MineLink) * own_t,m`, and each mine follows an AR(1) process
   `x_t = Smoothing * x_(t-1) + sqrt(1 - Smoothing^2) * shock_t`. The `sqrt(1 - phi^2)` factor keeps the variance at 1,
   so Smoothing changes how output moves from day to day without changing its spread. It runs as one `SCAN` over all
   mines one after another, folded back into columns with `WRAPCOLS`.
3. **Distribution.** `x` is standard normal, so it is mapped to the chosen distribution (a Gaussian copula):
   Normal `Mean + Deviation * x`; Uniform `Min + (Max - Min) * NORMSDIST(x)`; Lognormal
   `exp(ln(Mean) - s2/2 + sqrt(s2) * x)` with `s2 = ln(1 + (Deviation/Mean)^2)`, which has exactly that mean and deviation.
   Each distribution keeps its exact shape whatever the smoothing.
4. **Pattern.** Capacity, the weekday factor (`WEEKDAY(date, 2)`, Monday = 1) and the compound trend multiply the base.
5. **Events.** Every event is a smooth bell centred on its days:
   `effect = 1 + (Factor - 1) / (1 + ((date - centre) / (Duration / 2))^4)`, `centre = Day + (Duration - 1)/2`.
   The curve is flat near the peak, covers the duration and fades within a day or two, which looks like a real
   breakdown or a rich seam rather than a single bad cell. Several events combine by multiplication, computed as
   `EXP(MMULT(LN(effects), hits))`, where `hits` is the `Impact` matrix (1 = event hits the mine).
6. **Which mines an event hits.** With *Probability* set, mine *m* is hit when `rnd(event, m, 3) < Probability`.
   With *Mines* set, the mines are ranked by the same random key and the first *Mines* are hit, so exactly that many
   mines are affected. The Generator shows the result in "Affected mines".

## Formulas

Formulas are written with English function names and comma separators. When pasting them by hand, set
File > Settings > Locale to United States first (the builder does this too, which also keeps `.` as the decimal
separator in the CSV the dashboard downloads).

### Generator cells

```
D4   =StartDate+DaysCount-1
C7   =IF(Distribution="Uniform", "Min", "Mean")
D7   =IF(Distribution="Uniform", "Max", "Deviation")
H8   =SWITCH(Distribution, "Normal", "Bell curve around Mean, spread = Deviation", "Uniform", "Flat: every value from Min to Max equally likely", "Lognormal", "Skewed right, never negative; Mean and Deviation of output", "Choose a distribution")
F11  ="≈ " & TEXT((1+N(DailyGrowth))^(DaysCount-1)-1, "+0%;-0%") & " over the whole period"
G13  =IF($B13="", "", IFERROR(TEXTJOIN(", ", TRUE, FILTER(Impact!$B$1:$Z$1, Impact!$B2:$Z2=1)), "none"))
     (copied down to G18; row 14 reads Impact row 3, and so on)
```

B19, parameter check:

```
=LET(
  issues, TEXTJOIN(" · ", TRUE,
    IF(N(DaysCount)<1, "Days count must be at least 1", ""),
    IF(N(DaysCount)>1000, "Days count is limited to 1000", ""),
    IF(COUNTA(MineNames)=0, "Add at least one mine name", ""),
    IF(AND(Distribution="Uniform", ParamB<=ParamA), "Uniform needs Max greater than Min", ""),
    IF(AND(Distribution<>"Uniform", ParamB<0), "Deviation cannot be negative", ""),
    IF(AND(Distribution="Lognormal", ParamA<=0), "Lognormal needs a positive Mean", ""),
    IF(OR(Smoothing<0, Smoothing>0.99), "Smoothing must be between 0 and 0.99", ""),
    IF(OR(MineLink<0, MineLink>1), "Mine link must be between 0 and 1", "")),
  IF(issues="",
    "✓ Ready: " & DaysCount & " days × " & COUNTA(MineNames) & " mines, " & TEXT(StartDate, "yyyy-mm-dd") & " to " & TEXT(StartDate+DaysCount-1, "yyyy-mm-dd"),
    "⚠ " & issues))
```

### Impact!A1

```
=LET(
  names, FILTER(MineNames, MineNames<>""),
  nMines, COLUMNS(names),
  nEvents, ROWS(EventDay),
  rnd, LAMBDA(x, y, salt, MOD(ABS(SIN(x*12.9898 + y*78.233 + salt*37.719 + N(Seed)*0.618034)) * 43758.5453, 1)),
  hits, MAKEARRAY(nEvents, nMines, LAMBDA(ei, mi, LET(
    evDay, INDEX(EventDay, ei),
    evProb, INDEX(EventProb, ei),
    evMines, INDEX(EventMines, ei),
    key, rnd(ei, mi, 3),
    keyRank, 1 + SUM(MAP(SEQUENCE(1, nMines), LAMBDA(jx, IF(rnd(ei, jx, 3) < key, 1, 0)))),
    IF(evDay="", 0,
      IF(evMines<>"", IF(keyRank <= evMines, 1, 0),
        IF(key < IF(evProb="", 1, evProb), 1, 0)))))),
  VSTACK(HSTACK("Event", names), HSTACK(SEQUENCE(nEvents), hits)))
```

### Data!A1

```
=ARRAYFORMULA(LET(
  nDays, DaysCount,
  start, StartDate,
  names, FILTER(MineNames, MineNames<>""),
  sizes, FILTER(MineSize, MineNames<>""),
  nMines, COLUMNS(names),
  nEvents, ROWS(EventDay),
  phi, MIN(MAX(N(Smoothing), 0), 0.99),
  rho, MIN(MAX(N(MineLink), 0), 1),
  pA, ParamA,
  pB, ParamB,
  rnd, LAMBDA(x, y, salt, MOD(ABS(SIN(x*12.9898 + y*78.233 + salt*37.719 + N(Seed)*0.618034)) * 43758.5453, 1)),
  zOf, LAMBDA(u, NORMSINV(MIN(MAX(u, 0.000001), 0.999999))),
  latent, WRAPCOLS(SCAN(0, SEQUENCE(nDays*nMines), LAMBDA(prev, ix, LET(
    ti, MOD(ix-1, nDays) + 1,
    mi, INT((ix-1)/nDays) + 1,
    shock, SQRT(rho)*zOf(rnd(ti, 0, 1)) + SQRT(1-rho)*zOf(rnd(ti, mi, 2)),
    IF(ti=1, shock, phi*prev + SQRT(1-phi^2)*shock)))), nDays),
  baseline, MAP(latent, LAMBDA(z, SWITCH(Distribution,
    "Uniform", pA + (pB-pA)*NORMSDIST(z),
    "Lognormal", LET(logVar, LN(1 + (pB/pA)^2), EXP(LN(pA) - logVar/2 + SQRT(logVar)*z)),
    pA + pB*z))),
  pattern, MAKEARRAY(nDays, nMines, LAMBDA(ti, mi, LET(
    size, INDEX(sizes, 1, mi),
    IF(size="", 1, size) * INDEX(WeekdayFactors, 1, WEEKDAY(start+ti-1, 2)) * (1+N(DailyGrowth))^(ti-1)))),
  pulses, MAKEARRAY(nDays, nEvents, LAMBDA(ti, ei, LET(
    evDay, INDEX(EventDay, ei),
    evLength, MAX(1, N(INDEX(EventDuration, ei))),
    evFactor, INDEX(EventFactor, ei),
    IF(OR(evDay="", evFactor=""), 0,
      LN(1 + (MAX(evFactor, 0.01)-1) / (1 + ((start+ti-1 - evDay - (evLength-1)/2) / (evLength/2))^4)))))),
  hits, ARRAY_CONSTRAIN(Impact!B2:Z7, nEvents, nMines),
  output, MAP(baseline * pattern * EXP(MMULT(pulses, hits)), LAMBDA(v, MAX(0, ROUND(v, 1)))),
  VSTACK(
    HSTACK("Date", "Total", names),
    HSTACK(SEQUENCE(nDays, 1, start), BYROW(output, LAMBDA(dayRow, ROUND(SUM(dayRow), 1))), output))))
```

## Building the sheet

**With the builder (2 minutes).** Create a blank sheet at sheets.new, open Extensions > Apps Script, replace the code
with `build_sheet.gs`, save, choose `buildMiningSimulator` and Run. Google asks once to allow the script to edit this
spreadsheet. Then go back to the sheet.

**By hand.** Rename the tabs to `Generator`, `Impact`, `Data`; type the parameter table from "Generator layout"; create
the named ranges (Data > Named ranges); paste the formulas above into the listed cells; format `Data!A:A` as
`yyyy-mm-dd` and `Data!B:Z` as `0.0`; insert the two charts from `Data`.

**Share for editing.** Share > General access > Anyone with the link > Editor. Copy the link into the dashboard
(sidebar, or `SHEET_URL` in `.streamlit/secrets.toml`). The dashboard reads
`https://docs.google.com/spreadsheets/d/<id>/gviz/tq?tqx=out:csv&sheet=Data` and the events from `Generator!B12:G18`.
