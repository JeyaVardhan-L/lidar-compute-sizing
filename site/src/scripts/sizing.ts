// Charts for the sizing page. Data: public/data/sizing.json (written by tools/sizing_analysis.py).
// @ts-ignore
import Plotly from 'plotly.js-dist-min';

const root = document.getElementById('sizing-charts')!;
const BASE = root.dataset.base || '/';
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const S = [1, 2, 3, 4, 5].map((i) => css(`--series-${i}`));
const ink = css('--color-ink'), mid = css('--color-mid-gray'), hair = css('--color-hairline');
const cfg = { responsive: true, displaylogo: false };
const layout = (title: string, y: string, extra: any = {}) => ({
  title: { text: title, font: { size: 14 } }, margin: { l: 64, r: 16, t: 40, b: 56 }, font: { family: css('--font-geist'), color: ink },
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', hovermode: 'closest',
  yaxis: { title: y, gridcolor: hair, zeroline: false }, xaxis: { gridcolor: hair, zeroline: false },
  legend: { orientation: 'h', y: -0.22 }, ...extra,
});
const hline = (y: number, label: string, dash = 'dash') => ({
  shape: { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: y, y1: y, line: { color: ink, dash, width: 1.5 } },
  ann: { xref: 'paper', x: 1, y, text: label, showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { size: 11, color: mid } },
});
const vline = (x: number, label: string) => ({
  shape: { type: 'line', yref: 'paper', y0: 0, y1: 1, x0: x, x1: x, line: { color: ink, dash: 'dash', width: 1.5 } },
  ann: { yref: 'paper', y: 1, x, text: label, showarrow: false, xanchor: 'left', yanchor: 'top', font: { size: 11, color: mid } },
});

(async () => {
  const data = await (await fetch(`${BASE}data/sizing.json`)).json().catch(() => null);
  if (!data || !data.rows?.length) return;
  const rows: any[] = data.rows;

  // 1. Python -> compiled ladder (bag 9, laptop-full)
  const order = ['baseline', 'optimized', 'p2plane', 'c-icp', 'c-gicp'];
  const names: Record<string, string> = { baseline: 'Python ICP', optimized: 'Python ICP, tuned', p2plane: 'Python point-to-plane', 'c-icp': 'C++ ICP', 'c-gicp': 'C++ GICP' };
  const lad = order.map((v) => rows.find((r) => r.dataset === 'newer_college_bag9' && r.variant === v && r.profile === 'laptop-full' && r.phase === 'A')).filter(Boolean);
  if (lad.length) {
    const x = lad.map((r) => names[r.variant]);
    const d = hline(100, '100 ms frame period');
    Plotly.react('c-ladder', [
      { x, y: lad.map((r) => r.latency_ms.p50), type: 'bar', name: 'median', marker: { color: S[0] }, hovertemplate: '%{x}<br>median %{y:.1f} ms<extra></extra>' },
      { x, y: lad.map((r) => r.latency_ms.p99), type: 'bar', name: 'P99', marker: { color: S[1] }, hovertemplate: '%{x}<br>P99 %{y:.1f} ms<extra></extra>' },
    ], layout('Frame time by implementation (bag 9, laptop)', 'ms per frame', { barmode: 'group', bargap: 0.3, bargroupgap: 0.08, shapes: [d.shape], annotations: [d.ann] }), cfg);
  }

  // 3. cost: points after voxel vs median frame time, pinned tiers, runs that kept tracking
  const tiers = [['laptop-4e', '4 E-cores (N100-class proxy)'], ['laptop-1e', '1 E-core']];
  const cost = rows.filter((r) => r.variant === 'c-gicp' && r.voxel_m === 0.15 && (r.accepted_pct ?? 0) >= 99 && r.dataset.startsWith('ncd21'));
  const tr: any[] = tiers.map(([t, lbl], i) => {
    const rr = cost.filter((r) => r.profile === t);
    return { x: rr.map((r) => r.points_voxel_p50 / 1000), y: rr.map((r) => r.latency_ms.p50), mode: 'markers', name: lbl,
      marker: { color: S[i], size: 9, line: { color: '#fff', width: 2 } },
      text: rr.map((r) => `${r.sensor.label}<br>${r.motion}, ${r.rate_hz} Hz`), hovertemplate: '%{text}<br>%{x:.1f} k points after voxel<br>median %{y:.1f} ms<extra>' + lbl + '</extra>' };
  });
  for (const [i, [t]] of tiers.entries()) {
    const m = (data.cost_model || []).find((c: any) => c.variant === 'c-gicp' && c.profile === t);
    if (m) tr.push({ x: m.kpts_range, y: m.kpts_range.map((k: number) => m.a_ms + m.b_ms_per_kpt * k), mode: 'lines', line: { color: S[i], width: 2, dash: 'dot' },
      name: `cost model, ${t}`, showlegend: false, hovertemplate: `model: ${m.a_ms.toFixed(1)} ms + ${m.b_ms_per_kpt.toFixed(2)} ms per 1000 points (R² ${m.r2.toFixed(2)})<extra></extra>` });
  }
  const h50 = hline(50, '50 ms: the FEASIBLE limit at 10 Hz'), h100 = hline(100, '100 ms period');
  Plotly.react('c-cost', tr, layout('Median frame time against points per scan (compiled GICP, pinned cores)', 'median ms per scan', {
    xaxis: { title: 'thousand points after the 0.15 m voxel filter', gridcolor: hair, zeroline: false }, shapes: [h50.shape, h100.shape], annotations: [h50.ann, h100.ann] }), cfg);

  // 4. board projection (4 cores; ASSUMED)
  const pick = data.posthoc?.at_10hz?.sensor?.sensor;
  const proj = (data.projection || []).find((p: any) => p.sensor === pick && p.dataset === 'ncd21_quad_hard');
  if (proj) {
    const b = proj.boards.filter((x: any) => x.p99_4c_ms != null).sort((a: any, c: any) => a.p99_4c_ms - c.p99_4c_ms);
    const v50 = vline(proj.period_ms * 0.5, '50 %'), v100 = vline(proj.period_ms, '100 ms');
    Plotly.react('c-boards', [{
      y: b.map((x: any) => x.board), x: b.map((x: any) => x.p99_4c_ms), type: 'bar', orientation: 'h', marker: { color: S[0] },
      error_x: { type: 'data', symmetric: false, array: b.map((x: any) => x.p99_4c_range_ms[1] - x.p99_4c_ms), arrayminus: b.map((x: any) => x.p99_4c_ms - x.p99_4c_range_ms[0]), color: mid, thickness: 1.5 },
      hovertemplate: '%{y}<br>projected P99 %{x:.0f} ms (4 cores)<extra>ASSUMED</extra>',
    }], layout('Projected P99 on 4 cores, hardest motion (ASSUMED)', '', { margin: { l: 230, r: 24, t: 40, b: 48 },
      xaxis: { title: 'ms per scan', gridcolor: hair, zeroline: false }, shapes: [v50.shape, v100.shape], annotations: [v50.ann, v100.ann], showlegend: false }), cfg);
  }

  // 6. accuracy vs points per second, by motion level
  const W = [['ncd21_quad_easy', 'easy'], ['ncd21_quad_medium', 'medium'], ['ncd21_quad_hard', 'hard'], ['ncd21_stairs', 'stairs']];
  const acc = rows.filter((r) => r.variant === 'c-gicp' && r.profile === 'laptop-full' && r.phase === 'C' && r.rpe10_pct != null && (r.accepted_pct ?? 0) >= 90);
  const at = W.map(([d, lbl], i) => {
    const rr = acc.filter((r) => r.dataset === d);
    return { x: rr.map((r) => r.points_per_s / 1000), y: rr.map((r) => r.rpe10_pct), mode: 'markers', name: lbl,
      marker: { color: S[i], size: 9, symbol: rr.map((r) => (r.rate_hz === 5 ? 'diamond' : 'circle')), line: { color: '#fff', width: 2 } },
      text: rr.map((r) => `${r.sensor.label}`), hovertemplate: '%{text}<br>%{x:.0f} k points/s<br>RPE 10 m %{y:.2f} %<extra>' + lbl + '</extra>' };
  });
  const r2 = hline(2, '2 % accuracy rule');
  Plotly.react('c-acc', at, layout('Drift against sensor output (circle 10 Hz, diamond 5 Hz)', 'RPE over 10 m (% of distance)', {
    xaxis: { title: 'thousand points per second (sensor output)', type: 'log', tickvals: [100, 200, 500, 1000, 1300], ticktext: ['100', '200', '500', '1000', '1300'], gridcolor: hair, zeroline: false }, shapes: [r2.shape], annotations: [r2.ann] }), cfg);
})();
