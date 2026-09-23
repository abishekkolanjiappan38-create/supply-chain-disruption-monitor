/* =====================================================================
   Supply Chain Disruption Monitor — dashboard data + drawing
   =====================================================================
   How this page works:
     1. It asks Supabase for the data (read-only, see config.js).
     2. It keeps everything in one object called `state`.
     3. It calculates the numbers (KPIs, map colours, weekly counts).
     4. It draws the page from `state`.
   Nothing here can change the database: the key in config.js may only read.
   ===================================================================== */

/* ---------- settings ---------------------------------------------- */
const WINDOW_DAYS = 30;     // KPIs, map and region list look back this far
const CHART_WEEKS = 8;      // trend chart length
const SEV = {high:'oklch(0.55 0.20 25)', medium:'oklch(0.70 0.145 75)', low:'oklch(0.58 0.13 155)'};
const SEV_RANK = {low:1, medium:2, high:3};
const NEUTRAL = 'oklch(0.925 0.012 250)';
// One colour per region, used by the chart and the region list.
const REGION_COLORS = ['oklch(0.50 0.19 258)','oklch(0.60 0.17 20)','oklch(0.62 0.15 150)',
                       'oklch(0.66 0.15 65)','oklch(0.58 0.16 310)','oklch(0.60 0.13 200)',
                       'oklch(0.55 0.15 330)','oklch(0.45 0.05 260)'];

/* ---------- talking to Supabase ------------------------------------ */
// Supabase gives every table a web address. We only ever send GET (= read).
async function api(path, extraHeaders = {}) {
  const headers = {apikey: window.SUPABASE.key, ...extraHeaders};
  // Old-style keys (long JWT) also need this header; new sb_... keys don't.
  if (!window.SUPABASE.key.startsWith('sb_')) headers.Authorization = 'Bearer ' + window.SUPABASE.key;

  const response = await fetch(window.SUPABASE.url + '/rest/v1/' + path, {headers});
  if (!response.ok) throw new Error(`Supabase ${response.status}: ${(await response.text()).slice(0, 200)}`);
  return response;
}

const daysAgo = (days) => new Date(Date.now() - days * 86400000);

async function countRows(path) {
  // "count=exact" makes Supabase report the total in a header like "0-0/27"
  const response = await api(path + '&limit=1', {Prefer: 'count=exact'});
  return Number((response.headers.get('content-range') || '/0').split('/')[1]) || 0;
}

const state = {
  signals: [],        // rows of the disruption_feed view (last CHART_WEEKS weeks)
  regions: [],        // regions table
  countries: [],      // countries table
  types: [],          // disruption_types table
  screened: 0,        // articles the model has judged (last 30 days)
  lastRun: null,      // newest successful pipeline run
  filterRegion: null, // region_id or null
  filterType: '',     // disruption_type_id as text, '' = all
  groupBy: 'region',
  world: null,        // map shapes (downloaded once)
};

async function loadData() {
  const chartStart = daysAgo(CHART_WEEKS * 7).toISOString();
  const windowStart = daysAgo(WINDOW_DAYS).toISOString();

  const [feed, regions, countries, types, screened, runs] = await Promise.all([
    api(`disruption_feed?select=*&published_at=gte.${chartStart}&order=published_at.desc&limit=2000`)
      .then(r => r.json()),
    api('regions?select=region_id,name,show_on_map&order=region_id').then(r => r.json()),
    api('countries?select=country_code,name,map_id,region_id').then(r => r.json()),
    api('disruption_types?select=disruption_type_id,name&order=name').then(r => r.json()),
    countRows(`articles?select=article_id&status=in.(disruption,not_disruption)&published_at=gte.${windowStart}`),
    api('pipeline_runs?select=finished_at,disruptions_found&status=eq.success&order=finished_at.desc&limit=1')
      .then(r => r.json()),
  ]);

  Object.assign(state, {signals: feed, regions, countries, types, screened, lastRun: runs[0] || null});
}

/* ---------- small helpers ------------------------------------------ */
const regionName = (id) => (state.regions.find(r => r.region_id === id) || {}).name || 'Unknown';
const regionColor = (id) => REGION_COLORS[(id - 1) % REGION_COLORS.length];
const inWindow = (rows, days) => rows.filter(r => new Date(r.published_at) >= daysAgo(days));

// Rows after the region + type filters the user picked.
function filteredSignals() {
  return state.signals.filter(s =>
    (state.filterRegion === null || s.region_id === state.filterRegion) &&
    (state.filterType === '' || String(s.disruption_type_id) === state.filterType));
}

// Monday 00:00 UTC of the week a date falls in — used to group by week.
function weekStart(date) {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d;
}
const fmtDay = (d) => d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'});
const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

/* ---------- header, banner, KPIs ----------------------------------- */
function renderHeader() {
  const stamp = document.getElementById('stamp');
  if (state.lastRun && state.lastRun.finished_at) {
    const when = new Date(state.lastRun.finished_at);
    const time = String(when.getUTCHours()).padStart(2, '0') + ':' + String(when.getUTCMinutes()).padStart(2, '0');
    stamp.textContent = `LAST RUN ${fmtDay(when).toUpperCase()} ${when.getUTCFullYear()}, ${time} UTC`;
  } else {
    stamp.textContent = 'NO SUCCESSFUL RUN YET';
  }
  document.getElementById('build').textContent = 'BUILD ' + new Date().toISOString().slice(0, 10).replace(/-/g, '.');

  const newest = state.signals[0];
  document.getElementById('modelname').textContent = newest ? newest.model_name : 'no extractions yet';
}

function renderKpis() {
  const recent = inWindow(state.signals, WINDOW_DAYS);
  const high = recent.filter(s => s.severity === 'high').length;
  // "Global" is a real region but not a place on the map, so it isn't counted here.
  const regionsHit = new Set(recent.filter(s => regionName(s.region_id) !== 'Global')
                                   .map(s => s.region_id)).size;

  document.getElementById('kpi-screened').textContent = state.screened;
  document.getElementById('kpi-signals').textContent = recent.length;
  document.getElementById('kpi-high').textContent = high;

  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  document.getElementById('headline').innerHTML = recent.length
    ? `<em>${plural(recent.length, 'disruption signal')}</em> across ${plural(regionsHit, 'region')}, ` +
      `extracted from ${plural(state.screened, 'news article')}.`
    : `No disruption signals in the last ${WINDOW_DAYS} days, from ${plural(state.screened, 'news article')} screened.`;
}

/* ---------- world map ---------------------------------------------- */
// For each country: its worst severity, how many signals, and what kind.
function mapDataByMapId() {
  const byCountry = {};
  for (const s of inWindow(state.signals, WINDOW_DAYS)) {
    if (!s.country_code) continue;                     // e.g. "Red Sea" has no single country
    const entry = byCountry[s.country_code] || (byCountry[s.country_code] = {signals: 0, worst: null});
    entry.signals++;
    // Keep the most severe signal; if two are equally severe, the newest wins
    // (rows arrive newest first, so only replace on a strictly higher severity).
    if (!entry.worst || SEV_RANK[s.severity] > SEV_RANK[entry.worst.severity]) entry.worst = s;
  }
  const byMapId = {};
  for (const country of state.countries) {
    const entry = byCountry[country.country_code];
    if (entry) byMapId[country.map_id] = {...entry, country};
  }
  return byMapId;
}

function drawMap() {
  if (!state.world) return;
  const data = mapDataByMapId();
  const svg = d3.select('#map');
  const width = document.querySelector('.mapwrap').clientWidth;
  const height = Math.round(width * 0.46);
  svg.attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height)
     .selectAll('*').remove();

  const projection = d3.geoNaturalEarth1().fitSize([width, height * 1.16], state.world);
  const tip = document.getElementById('tip');

  svg.append('g').selectAll('path').data(state.world.features).join('path')
    .attr('d', d3.geoPath(projection))
    // The map file's country id is the ISO number, the same value as countries.map_id.
    .attr('class', d => 'country' + (data[d.id] ? ' hit' : ''))
    .style('cursor', d => data[d.id] ? 'pointer' : 'default')
    .attr('fill', d => data[d.id] ? SEV[data[d.id].worst.severity] : NEUTRAL)
    .on('mousemove', (event, d) => {
      const entry = data[d.id];
      if (!entry) return;
      tip.style.opacity = 1;
      tip.style.left = Math.min(event.clientX + 14, innerWidth - 250) + 'px';
      tip.style.top = (event.clientY + 14) + 'px';
      tip.innerHTML = `<b>${escapeHtml(entry.country.name)}</b>` +
        `<span class="mono" style="color:${SEV[entry.worst.severity]};font-size:11px;` +
        `text-transform:uppercase;letter-spacing:.08em">${entry.worst.severity}</span>` +
        `<div style="color:var(--ink-2);margin-top:5px">${escapeHtml(entry.worst.disruption_type)} · ` +
        `${entry.signals} signal${entry.signals === 1 ? '' : 's'}</div>`;
    })
    .on('mouseleave', () => tip.style.opacity = 0)
    .on('click', (event, d) => {
      const entry = data[d.id];
      if (entry) setFilter(entry.country.region_id, state.filterType, entry.country.name);
    });
}

/* ---------- trend chart + region list ------------------------------- */
// Weekly buckets: one row per week, one column per series (region or severity).
function weeklySeries() {
  const weeks = [];
  const thisWeek = weekStart(new Date());
  for (let i = CHART_WEEKS - 1; i >= 0; i--) {
    const start = new Date(thisWeek);
    start.setUTCDate(start.getUTCDate() - i * 7);
    weeks.push(start);
  }

  const rows = filteredSignals();
  const byKey = new Map();          // series key -> counts per week
  const keyOf = (s) => state.groupBy === 'region' ? regionName(s.region_id) : s.severity;
  const colorOf = (s) => state.groupBy === 'region' ? regionColor(s.region_id) : SEV[s.severity];

  for (const s of rows) {
    const start = weekStart(new Date(s.published_at));
    const index = weeks.findIndex(w => w.getTime() === start.getTime());
    if (index < 0) continue;        // older than the chart window
    const key = keyOf(s);
    if (!byKey.has(key)) byKey.set(key, {name: key, color: colorOf(s), values: weeks.map(() => 0)});
    byKey.get(key).values[index]++;
  }
  return {weeks, series: [...byKey.values()].sort((a, b) =>
    d3.sum(b.values) - d3.sum(a.values))};
}

function drawChart() {
  const {weeks, series} = weeklySeries();
  const svg = d3.select('#chart');
  const width = document.querySelector('.chartpad').clientWidth;
  const height = 330;
  // Extra space at the top when grouping by severity: the key is drawn there.
  const margin = {top: state.groupBy === 'severity' ? 34 : 14, right: 46, bottom: 30, left: 34};
  svg.attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height)
     .selectAll('*').remove();

  document.getElementById('chartrange').textContent =
    `${CHART_WEEKS} weeks · ${fmtDay(weeks[0])} – ${fmtDay(new Date())}`;

  const maxCount = Math.max(1, d3.max(series, s => d3.max(s.values)) || 0);
  const x = d3.scalePoint().domain(d3.range(weeks.length)).range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain([0, maxCount]).nice(Math.min(maxCount, 4))
              .range([height - margin.bottom, margin.top]);
  const ticks = y.ticks(Math.min(maxCount, 4)).filter(Number.isInteger);

  svg.append('g').selectAll('line').data(ticks).join('line')
    .attr('x1', margin.left).attr('x2', width - margin.right).attr('y1', y).attr('y2', y)
    .attr('stroke', 'oklch(0.90 0.014 250)').attr('stroke-width', 1);
  svg.append('g').selectAll('text').data(ticks).join('text')
    .attr('x', margin.left - 10).attr('y', d => y(d) + 4).attr('text-anchor', 'end')
    .attr('fill', 'oklch(0.60 0.028 260)').attr('font-size', 11)
    .attr('font-family', 'IBM Plex Mono, monospace').text(d => d);
  svg.append('g').selectAll('text').data(weeks).join('text')
    .attr('x', (d, i) => x(i)).attr('y', height - 10).attr('text-anchor', 'middle')
    .attr('fill', 'oklch(0.60 0.028 260)').attr('font-size', 11)
    .attr('font-family', 'IBM Plex Mono, monospace').text(d => fmtDay(d));

  if (!series.length) {         // nothing to draw yet — say so instead of showing an empty grid
    svg.append('text').attr('x', width / 2).attr('y', height / 2).attr('text-anchor', 'middle')
      .attr('fill', 'oklch(0.60 0.028 260)').attr('font-size', 13)
      .text('No disruption signals in this period yet');
    return;
  }

  // Straight lines, not curves: a curve would suggest values between weeks
  // that we never measured. Dots mark the weeks we actually counted.
  const line = d3.line().x((d, i) => x(i)).y(d => y(d));
  // Dash patterns so two series with identical counts don't hide each other.
  const DASHES = [null, '6 3', '2 3', '10 4'];
  series.forEach((s, index) => {
    svg.append('path').datum(s.values).attr('fill', 'none').attr('stroke', s.color)
      .attr('stroke-width', 2).attr('stroke-dasharray', DASHES[index % DASHES.length])
      .attr('d', line);
    svg.append('g').selectAll('circle').data(s.values).join('circle')
      .attr('cx', (d, i) => x(i)).attr('cy', d => y(d)).attr('r', 2.5).attr('fill', s.color);
    svg.append('circle').attr('cx', x(weeks.length - 1)).attr('cy', y(s.values[weeks.length - 1]))
      .attr('r', 3.5).attr('fill', s.color);
    svg.append('text').attr('x', x(weeks.length - 1) + 9)
      .attr('y', y(s.values[weeks.length - 1]) + 4).attr('fill', s.color)
      .attr('font-size', 11).attr('font-family', 'IBM Plex Mono, monospace')
      .text(s.values[weeks.length - 1]);
  });

  // Key for the dash patterns when grouping by severity (regions have the list on the right).
  if (state.groupBy === 'severity') {
    const key = svg.append('g');
    series.forEach((s, index) => {
      key.append('text').attr('x', margin.left + index * 90).attr('y', 14)
        .attr('fill', s.color).attr('font-size', 11)
        .attr('font-family', 'IBM Plex Mono, monospace').text(`${s.name} (${d3.sum(s.values)})`);
    });
  }
}

function renderRegionList() {
  const recent = inWindow(state.signals, WINDOW_DAYS);
  const counts = new Map();
  for (const s of recent) counts.set(s.region_id, (counts.get(s.region_id) || 0) + 1);

  const rows = state.regions
    .map(r => ({...r, count: counts.get(r.region_id) || 0}))
    .filter(r => r.count > 0)               // only regions that actually have signals
    .sort((a, b) => b.count - a.count);

  const list = document.getElementById('rlist');
  list.innerHTML = `<span class="eyebrow" style="margin-bottom:8px">Signals · ${WINDOW_DAYS} days</span>` +
    (rows.length ? rows.map(r => `
      <button class="rrow" aria-pressed="${state.filterRegion === null || state.filterRegion === r.region_id}"
              data-region="${r.region_id}">
        <span class="key" style="background:${regionColor(r.region_id)}"></span>${escapeHtml(r.name)}
        <span class="val">${r.count}</span>
      </button>`).join('')
      : '<span style="font-size:12.5px;color:var(--ink-3)">No signals yet</span>');

  list.querySelectorAll('.rrow').forEach(button => button.addEventListener('click', () => {
    const id = Number(button.dataset.region);
    setFilter(state.filterRegion === id ? null : id, state.filterType);   // click again = unfilter
  }));
}

/* ---------- feed ---------------------------------------------------- */
function renderFeed() {
  const rows = filteredSignals();
  const feed = document.getElementById('feed');

  feed.innerHTML = rows.length ? rows.map(s => `
    <article class="card">
      <div class="ctop">
        <span class="sev" style="color:${SEV[s.severity]};background:color-mix(in oklab, ${SEV[s.severity]} 14%, transparent)">
          <span class="sw" style="background:${SEV[s.severity]}"></span>${s.severity}</span>
        <span class="mono" style="font-size:11px;color:var(--ink-3)">${fmtDay(new Date(s.published_at))}</span>
      </div>
      <h4>${escapeHtml(s.title)}</h4>
      <p class="summary">${escapeHtml(s.summary)}</p>
      <div class="fields">
        <span class="fk">region</span><span class="fv">${escapeHtml(s.region)}</span>
        <span class="fk">country</span><span class="fv">${escapeHtml(s.country || '—')}</span>
        <span class="fk">type</span><span class="fv">${escapeHtml(s.disruption_type)}</span>
        <span class="fk">severity</span><span class="fv" style="color:${SEV[s.severity]}">${s.severity}</span>
      </div>
      <div class="csrc"><span>${escapeHtml(s.source_name || 'unknown source')}</span>
        <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">Open source article &rarr;</a></div>
    </article>`).join('')
    : `<div class="empty">No stored signals match this filter${
         state.signals.length ? '' : ' — the pipeline has not flagged any disruptions yet'}.</div>`;

  // The cards sit on a grid; without this, empty cells in the last row show
  // the grid's grey background. These blank cards fill the gap.
  if (rows.length) {
    const perRow = Math.max(1, Math.floor(feed.clientWidth / 360));
    const blanks = (perRow - (rows.length % perRow)) % perRow;
    feed.insertAdjacentHTML('beforeend', '<div class="card"></div>'.repeat(blanks));
  }

  // Filter bar: says what is filtered, and offers a way out.
  const bar = document.getElementById('filterbar');
  const parts = [];
  if (state.filterRegion !== null) parts.push(`<strong>${escapeHtml(regionName(state.filterRegion))}</strong>`);
  if (state.filterType) {
    const type = state.types.find(t => String(t.disruption_type_id) === state.filterType);
    if (type) parts.push(`<strong>${escapeHtml(type.name)}</strong>`);
  }
  bar.hidden = parts.length === 0;
  if (parts.length) {
    document.getElementById('filtertext').innerHTML =
      `Filtered to ${parts.join(' · ')}${state.clickedCountry ? ' · selected ' + escapeHtml(state.clickedCountry) : ''}` +
      ` — showing ${rows.length} of ${state.signals.length} signals.`;
  }
}

function renderTypeOptions() {
  const select = document.getElementById('typefilter');
  select.innerHTML = '<option value="">All types</option>' +
    state.types.map(t => `<option value="${t.disruption_type_id}">${escapeHtml(t.name)}</option>`).join('');
  select.value = state.filterType;
}

/* ---------- putting it together ------------------------------------- */
function setFilter(regionId, typeId, clickedCountry = null) {
  state.filterRegion = regionId;
  state.filterType = typeId;
  state.clickedCountry = clickedCountry;

  // Put the filters in the address bar, so a filtered view can be bookmarked or shared.
  const params = new URLSearchParams();
  if (regionId !== null) params.set('region', regionId);
  if (typeId) params.set('type', typeId);
  const query = params.toString();
  history.replaceState(null, '', query ? '?' + query : location.pathname);
  renderRegionList();
  drawChart();
  renderFeed();
}

function renderAll() {
  renderHeader();
  renderKpis();
  renderTypeOptions();
  renderRegionList();
  drawMap();
  drawChart();
  renderFeed();
}

function showError(error) {
  const box = document.getElementById('error');
  box.hidden = false;
  box.innerHTML = `<strong>Could not load data from Supabase.</strong><br>${escapeHtml(error.message)}` +
    `<br><span style="color:var(--ink-3)">Check web/config.js (project URL and publishable key) and that the tables are readable.</span>`;
}

async function refresh() {
  const button = document.getElementById('refresh');
  if (button.dataset.busy === '1') return;
  button.dataset.busy = '1';                       // spins the icon while loading
  try {
    await loadData();
    document.getElementById('error').hidden = true;
    renderAll();
  } catch (error) {
    showError(error);
  } finally {
    button.dataset.busy = '0';
  }
}

async function start() {
  // Filters can be set in the address bar: index.html?region=5&type=6
  const params = new URLSearchParams(location.search);
  if (params.has('region')) state.filterRegion = Number(params.get('region'));
  if (params.has('type')) state.filterType = params.get('type');
  if (params.get('group') === 'severity') state.groupBy = 'severity';

  document.getElementById('refresh').addEventListener('click', refresh);
  document.getElementById('groupby').addEventListener('change', (e) => {
    state.groupBy = e.target.value;
    drawChart();
  });
  document.getElementById('typefilter').addEventListener('change', (e) => {
    setFilter(state.filterRegion, e.target.value);
  });
  document.getElementById('clearfilter').addEventListener('click', () => setFilter(null, ''));
  document.getElementById('groupby').value = state.groupBy;
  document.getElementById('typefilter').value = state.filterType;
  addEventListener('resize', () => { drawMap(); drawChart(); });

  // The map shapes come from a public file and never change, so load them once.
  d3.json('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json')
    .then(topo => { state.world = topojson.feature(topo, topo.objects.countries); drawMap(); })
    .catch(() => {});

  await refresh();
}

start();
