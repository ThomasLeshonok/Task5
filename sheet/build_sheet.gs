/**
 * Weyland-Yutani Mining Ops Simulator: one-time builder.
 *
 * The generator itself is plain spreadsheet formulas (see formulas.md). This script only lays them out:
 * it writes the parameter table, named ranges, the three formulas, formatting, validation and charts,
 * so the sheet can be rebuilt identically. After it has run once the script can be deleted.
 *
 * Use: open a blank Google Sheet > Extensions > Apps Script > paste this file > Run buildMiningSimulator.
 */

const PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const LABEL_BG = '#d9d9d9';
const HEADER_BG = '#bfbfbf';
const BORDER = '#a6a6a6';
const HINT = '#6b6a66';
const MAX_DAYS = 1000;
const LAST_COL = 'Z'; // mines may be added up to column Z (25 mines)

const DATA_FORMULA = `=ARRAYFORMULA(LET(
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
    HSTACK(SEQUENCE(nDays, 1, start), BYROW(output, LAMBDA(dayRow, ROUND(SUM(dayRow), 1))), output))))`;

const IMPACT_FORMULA = `=LET(
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
  VSTACK(HSTACK("Event", names), HSTACK(SEQUENCE(nEvents), hits)))`;

const CHECK_FORMULA = `=LET(
  issues, TEXTJOIN(" · ", TRUE,
    IF(N(DaysCount)<1, "Days count must be at least 1", ""),
    IF(N(DaysCount)>${MAX_DAYS}, "Days count is limited to ${MAX_DAYS}", ""),
    IF(COUNTA(MineNames)=0, "Add at least one mine name", ""),
    IF(AND(Distribution="Uniform", ParamB<=ParamA), "Uniform needs Max greater than Min", ""),
    IF(AND(Distribution<>"Uniform", ParamB<0), "Deviation cannot be negative", ""),
    IF(AND(Distribution="Lognormal", ParamA<=0), "Lognormal needs a positive Mean", ""),
    IF(OR(Smoothing<0, Smoothing>0.99), "Smoothing must be between 0 and 0.99", ""),
    IF(OR(MineLink<0, MineLink>1), "Mine link must be between 0 and 1", "")),
  IF(issues="",
    "✓ Ready: " & DaysCount & " days × " & COUNTA(MineNames) & " mines, " & TEXT(StartDate, "yyyy-mm-dd") & " to " & TEXT(StartDate+DaysCount-1, "yyyy-mm-dd"),
    "⚠ " & issues))`;

function buildMiningSimulator() {
  const ss = SpreadsheetApp.getActive();
  ss.setSpreadsheetLocale('en_US'); // '.' decimals and yyyy-mm-dd dates in the CSV the dashboard reads
  ss.rename('Weyland-Yutani · Mining Ops Simulator');

  const gen = sheet_(ss, 'Generator', 0);
  const impact = sheet_(ss, 'Impact', 1);
  const data = sheet_(ss, 'Data', 2);
  ss.getSheets().filter(s => !['Generator', 'Impact', 'Data'].includes(s.getName())).forEach(s => ss.deleteSheet(s));

  buildGenerator_(gen);
  ss.getNamedRanges().forEach(r => r.remove());
  const names = {
    StartDate: 'B4', DaysCount: 'C4', MineNames: `B5:${LAST_COL}5`, MineSize: `B6:${LAST_COL}6`,
    Distribution: 'B8', ParamA: 'C8', ParamB: 'D8', Smoothing: 'E8', MineLink: 'F8', Seed: 'G8',
    WeekdayFactors: 'B10:H10', DailyGrowth: 'B11',
    EventDay: 'B13:B18', EventDuration: 'C13:C18', EventFactor: 'D13:D18', EventProb: 'E13:E18', EventMines: 'F13:F18',
  };
  Object.entries(names).forEach(([name, a1]) => ss.setNamedRange(name, gen.getRange(a1)));

  buildImpact_(impact);
  buildData_(data);
  formulasOnGenerator_(gen);
  SpreadsheetApp.flush();
  charts_(gen, data);
  ss.setActiveSheet(gen);
}

/** Date as a spreadsheet serial number, so the script time zone cannot shift it by a day. */
function day_(year, month, date) {
  return (Date.UTC(year, month - 1, date) - Date.UTC(1899, 11, 30)) / 86400000;
}

function sheet_(ss, name, index) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = index === 0 && ss.getSheets().length ? ss.getSheets()[0].setName(name) : ss.insertSheet(name);
  }
  sh.getCharts().forEach(c => sh.removeChart(c));
  sh.getProtections(SpreadsheetApp.ProtectionType.SHEET).forEach(p => p.remove());
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.getDataRange().clearDataValidations();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).breakApart();
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(index + 1);
  return sh;
}

function buildGenerator_(sh) {
  sh.setHiddenGridlines(true).setTabColor('#0f1f2e');
  if (sh.getMaxColumns() < 26) sh.insertColumnsAfter(sh.getMaxColumns(), 26 - sh.getMaxColumns());
  sh.setColumnWidth(1, 135);
  sh.setColumnWidths(2, 25, 112);
  sh.setRowHeight(1, 56);
  sh.setRowHeights(2, 18, 30);

  const values = [
    ['Weyland-Yutani Corporation', '', '', '', '', '', '', '', ''],
    ['Mining Ops Simulator', '', '', '', '', '', '', '', ''],
    ['Range:', 'Start date', 'Days count', 'End date', '', '', '', '', ''],
    ['', day_(2099, 11, 2), 120, '', '', '', '', '', ''],
    ['Mines:', 'LV-426', 'Origae-6', 'Fiorina 161', 'LV-223', '', '', '', ''],
    ['Capacity:', 1, 1.4, 0.7, 1.1, '', '', '', ''],
    ['Random:', 'Distribution', '', '', 'Smoothing', 'Mine link', 'Seed', '', ''],
    ['', 'Normal', 50, 7, 0.6, 0.35, 2099, '', ''],
    ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun', ''],
    ['Daily output:', 1, 1, 1, 1, 1, 0.8, 0.6, ''],
    ['Daily growth:', 0.002, '', '', '', '', '', '', ''],
    ['Events:', 'Day', 'Duration', 'Factor', 'Probability', 'Mines', 'Affected mines', '', ''],
    ['', day_(2099, 11, 10), 3, 0.4, 1, '', '', '', ''],
    ['', day_(2099, 11, 20), 1, 1.4, 0.33, '', '', '', ''],
    ['', day_(2099, 12, 14), 4, 1.6, '', 2, '', '', ''],
    ['', day_(2100, 1, 18), 2, 0.3, 0.5, '', '', '', ''],
    ['', day_(2100, 2, 6), 1, 1.8, 0.5, '', '', '', ''],
    ['', '', '', '', '', '', '', '', ''],
    ['Check:', '', '', '', '', '', '', '', ''],
  ];
  sh.getRange(1, 1, values.length, 9).setValues(values);

  const table = sh.getRange('A2:I19');
  table.setFontFamily('Arial').setFontSize(11).setVerticalAlignment('middle')
    .setBorder(true, true, true, true, true, true, BORDER, SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange('A1:I1').merge().setFontSize(22).setHorizontalAlignment('center').setVerticalAlignment('middle')
    .setFontColor('#0b0b0b');
  sh.getRange('A2:I2').merge().setBackground(HEADER_BG).setFontWeight('bold').setHorizontalAlignment('center');

  ['A3', 'A5', 'A6', 'A7', 'A10', 'A11', 'A12', 'A13:A18', 'A19'].forEach(a1 =>
    sh.getRange(a1).setBackground(LABEL_BG).setFontWeight('bold').setHorizontalAlignment('right'));
  ['B3:D3', 'B7:G7', 'B12:G12'].forEach(a1 =>
    sh.getRange(a1).setFontWeight('bold').setHorizontalAlignment('center'));
  sh.getRange('B9:H9').setFontWeight('bold').setFontSize(9).setFontColor(HINT).setHorizontalAlignment('center');
  sh.getRange('G12:I12').merge();
  for (let r = 13; r <= 18; r++) sh.getRange(`G${r}:I${r}`).merge();
  sh.getRange('H8:I8').merge();
  sh.getRange('C11:E11').merge();
  sh.getRange('F11:I11').merge();
  sh.getRange('B19:I19').merge();

  sh.getRange('B4').setNumberFormat('yyyy-mm-dd').setHorizontalAlignment('center');
  sh.getRange('C4').setNumberFormat('0');
  sh.getRange('D4').setNumberFormat('yyyy-mm-dd').setHorizontalAlignment('center');
  sh.getRange(`B6:${LAST_COL}6`).setNumberFormat('0.0#');
  sh.getRange('B8').setHorizontalAlignment('center');
  sh.getRange('C8:D8').setNumberFormat('0.0#');
  sh.getRange('E8:F8').setNumberFormat('0.00');
  sh.getRange('G8').setNumberFormat('0');
  sh.getRange('B10:H10').setNumberFormat('0.0#');
  sh.getRange('B11').setNumberFormat('0.0#%');
  sh.getRange('B13:B18').setNumberFormat('yyyy-mm-dd').setHorizontalAlignment('center');
  sh.getRange('C13:C18').setNumberFormat('0');
  sh.getRange('D13:D18').setNumberFormat('0.0#');
  sh.getRange('E13:E18').setNumberFormat('0.0#');
  sh.getRange('F13:F18').setNumberFormat('0');

  // computed cells: grey italic so they read as outputs, not inputs
  ['D4', 'C7', 'D7', 'H8', 'C11', 'F11', 'G13:G18'].forEach(a1 =>
    sh.getRange(a1).setFontColor(HINT).setFontStyle('italic'));
  sh.getRange('C7:D7').setFontStyle('normal').setFontColor('#0b0b0b');
  sh.getRange('H8').setFontSize(9).setWrap(true);
  sh.getRange('C11').setValue('compound, per day').setFontSize(9);
  sh.getRange('G13:G18').setFontSize(9).setWrap(true);
  sh.getRange('B19').setFontWeight('bold');

  validation_(sh);
  notes_(sh);
  sh.setFrozenRows(0);
}

function validation_(sh) {
  const rule = () => SpreadsheetApp.newDataValidation().setAllowInvalid(false);
  sh.getRange('B4').setDataValidation(rule().requireDate().setHelpText('Any date, e.g. 2099-11-02').build());
  sh.getRange('C4').setDataValidation(rule().requireNumberBetween(1, MAX_DAYS).setHelpText(`1 to ${MAX_DAYS} days`).build());
  sh.getRange(`B6:${LAST_COL}6`).setDataValidation(rule().requireNumberBetween(0, 100)
    .setHelpText('Relative size of the mine: 1 = standard, 1.5 = 50% larger. Empty = 1.').build());
  sh.getRange('B8').setDataValidation(rule().requireValueInList(['Normal', 'Uniform', 'Lognormal'], true).build());
  sh.getRange('C8').setDataValidation(rule().requireFormulaSatisfied('=AND(ISNUMBER(C8), OR($B$8<>"Lognormal", C8>0))')
    .setHelpText('Normal / Lognormal: mean daily output. Uniform: minimum.').build());
  sh.getRange('D8').setDataValidation(rule().requireFormulaSatisfied('=AND(ISNUMBER(D8), IF($B$8="Uniform", D8>C8, D8>=0))')
    .setHelpText('Normal / Lognormal: standard deviation (>= 0). Uniform: maximum (> Min).').build());
  sh.getRange('E8').setDataValidation(rule().requireNumberBetween(0, 0.99).setHelpText('0 = independent days, 0.9 = slow drifts').build());
  sh.getRange('F8').setDataValidation(rule().requireNumberBetween(0, 1).setHelpText('0 = mines independent, 1 = all mines move together').build());
  sh.getRange('G8').setDataValidation(rule().requireNumberBetween(0, 1000000).setHelpText('Change to draw a new random scenario').build());
  sh.getRange('B10:H10').setDataValidation(rule().requireNumberBetween(0, 10).setHelpText('Multiplier for this weekday, 1 = normal').build());
  sh.getRange('B11').setDataValidation(rule().requireNumberBetween(-0.05, 0.05).setHelpText('-5% to +5% per day').build());
  sh.getRange('B13:B18').setDataValidation(rule().requireDate().build());
  sh.getRange('C13:C18').setDataValidation(rule().requireNumberBetween(1, 365).setHelpText('Length of the event in days').build());
  sh.getRange('D13:D18').setDataValidation(rule().requireNumberBetween(0, 10).setHelpText('Output multiplier at the peak: 0.4 = drop to 40%, 1.5 = +50%').build());
  sh.getRange('E13:E18').setDataValidation(rule().requireNumberBetween(0, 1).setHelpText('Chance that each mine is hit. Ignored when Mines is set.').build());
  sh.getRange('F13:F18').setDataValidation(rule().requireNumberBetween(0, 25).setHelpText('Exact number of mines hit (random choice). Leave empty to use Probability.').build());

  const rules = [
    SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=LEFT($B$19,1)="✓"')
      .setFontColor('#006300').setBackground('#eef7ee').setRanges([sh.getRange('B19')]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=LEFT($B$19,1)="⚠"')
      .setFontColor('#b42318').setBackground('#fdecea').setRanges([sh.getRange('B19')]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=AND($B$8="Uniform", $D$8<=$C$8)')
      .setBackground('#fdecea').setRanges([sh.getRange('C8:D8')]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=AND($B13<>"", $F13<>"")')
      .setFontColor('#a8a8a8').setStrikethrough(true).setRanges([sh.getRange('E13:E18')]).build(),
  ];
  sh.setConditionalFormatRules(rules);
}

function notes_(sh) {
  const notes = {
    A3: 'First day and number of days to generate (1-1000). The Data tab grows or shrinks with it.',
    A5: 'Type mine names from B5 to the right (up to column Z). Empty cells are skipped; the Data tab gets one column per name.',
    A6: 'Optional relative capacity of each mine (1 = standard). Multiplies its whole series.',
    A7: 'Distribution of daily output. Labels C7:D7 switch with it: Normal and Lognormal use Mean / Deviation, Uniform uses Min / Max.\n\n' +
        'Smoothing: day-to-day correlation (AR(1) coefficient). 0 = independent days, 0.6 = realistic inertia, 0.95 = slow drifts.\n\n' +
        'Mine link: share of the daily shock common to all mines (weather, supply, power). 0 = independent, 1 = identical noise.\n\n' +
        'Seed: change it to draw a new scenario; the same seed always reproduces the same data.',
    A10: 'Multiplier per weekday (Mon-Sun). 0.6 on Sunday = output reduced by 40%.',
    A11: 'Overall trend: compound growth per day. 0.2% per day is about +27% over 120 days. Negative values give decline.',
    A12: 'Up to six spikes or drops. Day = first day, Duration = days, Factor = output multiplier at the peak ' +
         '(0.4 = drop to 40%, 1.6 = +60%), shaped as a smooth bell over the duration.\n\n' +
         'Probability = chance each mine is hit. Mines = exact number of mines hit instead (overrides Probability).',
    A19: 'Validation of the parameters above.',
  };
  Object.entries(notes).forEach(([a1, note]) => sh.getRange(a1).setNote(note));
}

function formulasOnGenerator_(sh) {
  sh.getRange('D4').setFormula('=StartDate+DaysCount-1');
  sh.getRange('C7').setFormula('=IF(Distribution="Uniform", "Min", "Mean")');
  sh.getRange('D7').setFormula('=IF(Distribution="Uniform", "Max", "Deviation")');
  sh.getRange('H8').setFormula('=SWITCH(Distribution, "Normal", "Bell curve around Mean, spread = Deviation", ' +
    '"Uniform", "Flat: every value from Min to Max equally likely", ' +
    '"Lognormal", "Skewed right, never negative; Mean and Deviation of output", "Choose a distribution")');
  sh.getRange('F11').setFormula('="≈ " & TEXT((1+N(DailyGrowth))^(DaysCount-1)-1, "+0%;-0%") & " over the whole period"');
  for (let r = 13; r <= 18; r++) {
    sh.getRange(`G${r}`).setFormula(
      `=IF($B${r}="", "", IFERROR(TEXTJOIN(", ", TRUE, FILTER(Impact!$B$1:$Z$1, Impact!$B${r - 11}:$Z${r - 11}=1)), "none"))`);
  }
  sh.getRange('B19').setFormula(CHECK_FORMULA);
}

function buildImpact_(sh) {
  sh.setTabColor('#c3c2b7');
  sh.getRange('A1').setFormula(IMPACT_FORMULA);
  sh.getRange('1:1').setFontWeight('bold').setBackground('#f0efec');
  sh.getRange('B2:Z7').setNumberFormat('"●";"";"·"').setHorizontalAlignment('center');
  sh.getRange('A9').setValue('1 = the event on that Generator row hits the mine. Random choice uses the Seed; '
    + 'with Mines set, exactly that many mines are chosen.').setFontColor(HINT).setFontStyle('italic');
  sh.setColumnWidth(1, 70);
  sh.setFrozenRows(1);
  sh.protect().setDescription('Formula output').setWarningOnly(true);
}

function buildData_(sh) {
  sh.setTabColor('#2a78d6');
  if (sh.getMaxRows() < MAX_DAYS + 1) sh.insertRowsAfter(sh.getMaxRows(), MAX_DAYS + 1 - sh.getMaxRows());
  if (sh.getMaxColumns() < 27) sh.insertColumnsAfter(sh.getMaxColumns(), 27 - sh.getMaxColumns());
  sh.getRange('A1').setFormula(DATA_FORMULA);
  sh.getRange('1:1').setFontWeight('bold').setBackground('#f0efec');
  sh.getRange(`A2:A${MAX_DAYS + 1}`).setNumberFormat('yyyy-mm-dd');
  sh.getRange(`B2:AA${MAX_DAYS + 1}`).setNumberFormat('0.0');
  sh.setColumnWidth(1, 100);
  sh.setFrozenRows(1);
  sh.setFrozenColumns(1);
  sh.protect().setDescription('Formula output').setWarningOnly(true);
}

function charts_(gen, data) {
  const rows = MAX_DAYS + 1;
  const mines = gen.newChart()
    .setChartType(Charts.ChartType.LINE)
    .addRange(data.getRange(`A1:A${rows}`))
    .addRange(data.getRange(`C1:${LAST_COL}${rows}`))
    .setMergeStrategy(Charts.ChartMergeStrategy.MERGE_COLUMNS)
    .setNumHeaders(1)
    .setOption('title', 'Daily output by mine')
    .setOption('titleTextStyle', {fontSize: 14, bold: true, color: '#0b0b0b'})
    .setOption('legend', {position: 'top', textStyle: {color: '#52514e'}})
    .setOption('colors', PALETTE)
    .setOption('lineWidth', 2)
    .setOption('hAxis', {format: 'MMM d', textStyle: {color: '#52514e'}, gridlines: {color: 'transparent'}})
    .setOption('vAxis', {minValue: 0, textStyle: {color: '#52514e'}, gridlines: {color: '#e1e0d9'}})
    .setOption('width', 1020)
    .setOption('height', 360)
    .setPosition(21, 1, 0, 8)
    .build();
  gen.insertChart(mines);

  const total = gen.newChart()
    .setChartType(Charts.ChartType.COLUMN)
    .addRange(data.getRange(`A1:B${rows}`))
    .setNumHeaders(1)
    .setOption('title', 'Total daily output with linear trend')
    .setOption('titleTextStyle', {fontSize: 14, bold: true, color: '#0b0b0b'})
    .setOption('legend', {position: 'none'})
    .setOption('colors', ['#3d3c38'])
    .setOption('bar', {groupWidth: '82%'})
    .setOption('trendlines', {0: {type: 'linear', color: '#c8a24a', lineWidth: 3, opacity: 0.9}})
    .setOption('hAxis', {format: 'MMM d', textStyle: {color: '#52514e'}, gridlines: {color: 'transparent'}})
    .setOption('vAxis', {minValue: 0, textStyle: {color: '#52514e'}, gridlines: {color: '#e1e0d9'}})
    .setOption('width', 1020)
    .setOption('height', 320)
    .setPosition(40, 1, 0, 8)
    .build();
  gen.insertChart(total);
}
