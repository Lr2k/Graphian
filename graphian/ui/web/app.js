/**
 * Graphian Web UI — 保存済みスナップショットの可視化(§9.6 / §9.9)。
 *
 * 3 つのビュー:
 *   1. 環境モニタ  : x・energy・fitness の時系列(Chart.js 折れ線グラフ)
 *   2. ネットワーク: 同心円グラフの SVG 描画(ノード値を色で表現)
 *   3. 系統樹      : genome の親子関係を SVG で描画
 *   4. 事象ログ    : events.jsonl の内容をテーブル表示
 *
 * データは /api/sessions・/api/session・/api/events から取得する。
 * ビルド工程なし。Chart.js は CDN から読み込む(§9.9)。
 */

'use strict';

// ─── 状態 ────────────────────────────────────────────────────────────────────
let _sessionData = null;   // parse_session() の返り値
let _trialIdx = 0;         // 現在表示中の試行インデックス
let _chartXE = null;       // Chart.js インスタンス(位置/エネルギー)
let _chartFit = null;      // Chart.js インスタンス(適応度)

// ─── 初期化 ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadSessionList();
});

// ─── タブ切り替え ─────────────────────────────────────────────────────────────

function initTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
    });
  });
}

// ─── セッション一覧 ───────────────────────────────────────────────────────────

async function loadSessionList() {
  setStatus('セッション一覧を読込中...');
  try {
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    const ul = document.getElementById('session-list');
    ul.innerHTML = '';
    if (!sessions.length) {
      ul.innerHTML = '<li style="color:#555;font-size:0.75rem">セッションがありません</li>';
      setStatus('graphian run でセッションを作成してください');
      return;
    }
    sessions.forEach((s, i) => {
      const li = document.createElement('li');
      li.textContent = s.name;
      li.title = s.name;
      li.addEventListener('click', () => {
        ul.querySelectorAll('li').forEach(x => x.classList.remove('active'));
        li.classList.add('active');
        loadSession(s.name);
      });
      ul.appendChild(li);
      if (i === 0) { li.classList.add('active'); loadSession(s.name); }
    });
    setStatus('');
  } catch (err) {
    setStatus('読込エラー: ' + err.message);
  }
}

// ─── セッションデータ読込 ─────────────────────────────────────────────────────

async function loadSession(dirName) {
  setStatus('読込中: ' + dirName);
  try {
    const [snapRes, evRes] = await Promise.all([
      fetch('/api/session?dir=' + encodeURIComponent(dirName)),
      fetch('/api/events?dir=' + encodeURIComponent(dirName)),
    ]);
    _sessionData = await snapRes.json();
    const events = await evRes.json();
    renderTrialList();
    renderEvents(events);
    if (_sessionData.trials.length > 0) {
      selectTrial(0);
    }
    setStatus(dirName);
  } catch (err) {
    setStatus('読込エラー: ' + err.message);
  }
}

// ─── 試行一覧 ────────────────────────────────────────────────────────────────

function renderTrialList() {
  const ul = document.getElementById('trial-list');
  ul.innerHTML = '';
  (_sessionData.trials || []).forEach((t, i) => {
    const li = document.createElement('li');
    const badge = document.createElement('span');
    badge.className = t.alive ? 'trial-fitness' : 'trial-dead';
    badge.textContent = t.alive ? `f=${t.fitness.toFixed(2)}` : '死亡';
    li.textContent = `試行 ${t.trial}`;
    li.appendChild(badge);
    li.addEventListener('click', () => selectTrial(i));
    ul.appendChild(li);
  });
}

function selectTrial(idx) {
  _trialIdx = idx;
  document.querySelectorAll('#trial-list li').forEach((li, i) => {
    li.classList.toggle('active', i === idx);
  });
  const trial = _sessionData.trials[idx];
  if (!trial) return;
  renderEnvCharts(trial);
  renderNetwork(trial.network, _sessionData.session_info);
}

// ─── 環境モニタ(Chart.js) ────────────────────────────────────────────────────

function renderEnvCharts(trial) {
  const series = trial.env_series || [];
  const steps   = series.map(d => d.step);
  const xs      = series.map(d => d.x);
  const energies = series.map(d => d.energy);
  const fitnesses = series.map(d => d.fitness);

  // x_light は session_info.config.environment.x_light から取れる場合に表示
  const xLight = _sessionData?.session_info?.config?.environment?.x_light ?? null;

  // ─ 位置 & エネルギー ─
  if (_chartXE) { _chartXE.destroy(); _chartXE = null; }
  const ctxXE = document.getElementById('chart-xe').getContext('2d');
  const datasetsXE = [
    {
      label: '位置 x',
      data: steps.map((s, i) => ({ x: s, y: xs[i] })),
      borderColor: '#7c8cf8',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
    },
    {
      label: 'エネルギー',
      data: steps.map((s, i) => ({ x: s, y: energies[i] })),
      borderColor: '#f0a04b',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
    },
  ];
  if (xLight !== null) {
    // x_light を水平線として追加
    datasetsXE.push({
      label: '光源 x_light',
      data: steps.length ? [{ x: steps[0], y: xLight }, { x: steps[steps.length - 1], y: xLight }] : [],
      borderColor: '#f7ca45',
      borderDash: [4, 4],
      borderWidth: 1,
      pointRadius: 0,
    });
  }
  _chartXE = new Chart(ctxXE, {
    type: 'line',
    data: { datasets: datasetsXE },
    options: chartOptions('ステップ', '値 (−1 〜 +1)', [-1.1, 1.1]),
  });

  // ─ 累積適応度 ─
  if (_chartFit) { _chartFit.destroy(); _chartFit = null; }
  const ctxFit = document.getElementById('chart-fitness').getContext('2d');
  _chartFit = new Chart(ctxFit, {
    type: 'line',
    data: {
      datasets: [{
        label: '累積適応度',
        data: steps.map((s, i) => ({ x: s, y: fitnesses[i] })),
        borderColor: '#5cb85c',
        backgroundColor: 'rgba(92,184,92,0.1)',
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
      }],
    },
    options: chartOptions('ステップ', '適応度'),
  });
}

function chartOptions(xLabel, yLabel, yRange) {
  const opts = {
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    parsing: false,
    plugins: {
      legend: { labels: { color: '#aaa', font: { size: 11 } } },
    },
    scales: {
      x: {
        type: 'linear',
        title: { display: true, text: xLabel, color: '#777', font: { size: 10 } },
        ticks: { color: '#666', maxTicksLimit: 8, font: { size: 10 } },
        grid: { color: '#22253a' },
      },
      y: {
        title: { display: true, text: yLabel, color: '#777', font: { size: 10 } },
        ticks: { color: '#666', font: { size: 10 } },
        grid: { color: '#22253a' },
      },
    },
  };
  if (yRange) opts.scales.y.min = yRange[0], opts.scales.y.max = yRange[1];
  return opts;
}

// ─── ネットワーク SVG ─────────────────────────────────────────────────────────
// 同心円構造(§5.1)を描く。接続点専用円(conn_circle)はノードが点線で示される。

const NET_CX = 220, NET_CY = 220, NET_R = 175;  // SVG 中心と最大半径

function renderNetwork(net, sessionInfo) {
  const svg = document.getElementById('network-svg');
  svg.innerHTML = '';

  if (!net || !net.nodes) {
    svgText(svg, NET_CX, NET_CY, 'ネットワークデータなし', '#555', 13);
    return;
  }

  const connCircle = net.conn_circle ?? -1;
  const nodes = net.nodes;        // [{c, s, v}, ...]
  const edges = net.edges || [];  // [{from:{c,s}, to:{c,s}}, ...]
  const rn    = net.reward_node;  // {c, s}

  // 各円の半径を推定: ゲノムの circle_diameters が config に入っているが、
  // ネットワークスナップショットには含まれていないため最大 circle からスケール。
  const maxCircle = nodes.reduce((m, n) => Math.max(m, n.c), connCircle);
  const circleRadii = {}; // circle index → SVG radius
  for (let c = 0; c <= maxCircle; c++) {
    if (c === connCircle) {
      circleRadii[c] = NET_R;
    } else {
      // 内側の円ほど小さい。単純な等分割でよい(実際の diameter は §8 以降で利用)。
      const innerCircles = maxCircle - (connCircle >= 0 ? 1 : 0);
      circleRadii[c] = Math.round(NET_R * (c + 1) / (innerCircles + 1));
    }
  }

  // 背景の同心円を描く
  const drawnCircles = new Set(nodes.map(n => n.c));
  if (connCircle >= 0) drawnCircles.add(connCircle);
  drawnCircles.forEach(c => {
    const r = circleRadii[c] ?? NET_R;
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    el.setAttribute('cx', NET_CX); el.setAttribute('cy', NET_CY);
    el.setAttribute('r', r);
    el.setAttribute('fill', 'none');
    el.setAttribute('stroke', c === connCircle ? '#3a3d55' : '#22253a');
    el.setAttribute('stroke-width', c === connCircle ? '1' : '0.5');
    if (c === connCircle) el.setAttribute('stroke-dasharray', '4,4');
    svg.appendChild(el);
  });

  // スロット位置計算(§5.1: angle = 2π * slot / slots_in_circle)
  const slotCounts = {};
  nodes.forEach(n => {
    if (!(n.c in slotCounts) || slotCounts[n.c] < n.s + 1)
      slotCounts[n.c] = n.s + 1;
  });
  function nodeXY(c, s) {
    const r = circleRadii[c] ?? NET_R;
    const count = slotCounts[c] || 1;
    const angle = (2 * Math.PI * s / count) - Math.PI / 2;
    return {
      x: NET_CX + r * Math.cos(angle),
      y: NET_CY + r * Math.sin(angle),
    };
  }

  // エッジを描く
  edges.forEach(e => {
    const a = nodeXY(e.from.c, e.from.s);
    const b = nodeXY(e.to.c,   e.to.s);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', a.x.toFixed(1)); line.setAttribute('y1', a.y.toFixed(1));
    line.setAttribute('x2', b.x.toFixed(1)); line.setAttribute('y2', b.y.toFixed(1));
    line.setAttribute('stroke', '#3a3f60');
    line.setAttribute('stroke-width', '0.8');
    svg.appendChild(line);
  });

  // ノードを描く
  nodes.forEach(n => {
    const { x, y } = nodeXY(n.c, n.s);
    const isReward = rn && n.c === rn.c && n.s === rn.s;
    const isConn   = n.c === connCircle;

    let fill, stroke, sw, r;
    if (isReward) {
      fill = '#f7ca45'; stroke = '#f7ca45'; sw = 2; r = 7;
    } else if (isConn) {
      // 接続点の種別は位置で仮判定(偶数スロット=感覚、奇数=運動)
      fill = (n.s % 2 === 0) ? '#5b9bd5' : '#e06c6c';
      stroke = fill; sw = 1.5; r = 6;
    } else {
      // 値に応じた色: v=-1→青, v=0→灰, v=+1→赤
      fill = nodeColor(n.v ?? 0);
      stroke = '#555'; sw = 0.5; r = 5;
    }

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x.toFixed(1)); circle.setAttribute('cy', y.toFixed(1));
    circle.setAttribute('r', r);
    circle.setAttribute('fill', fill);
    circle.setAttribute('stroke', stroke);
    circle.setAttribute('stroke-width', sw);
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = `(circle=${n.c}, slot=${n.s}) v=${(n.v ?? 0).toFixed(3)}` + (isReward ? ' [reward]' : '') + (isConn ? ' [conn]' : '');
    circle.appendChild(title);
    svg.appendChild(circle);
  });

  if (!nodes.length) svgText(svg, NET_CX, NET_CY, 'ノードなし', '#555', 12);
}

function nodeColor(v) {
  // v ∈ [-1, +1] → 青(負)〜灰(0)〜赤(正)
  const c = Math.max(-1, Math.min(1, v));
  if (c >= 0) {
    const r = Math.round(130 + 125 * c);
    return `rgb(${r},${Math.round(80 - 30 * c)},${Math.round(80 - 30 * c)})`;
  } else {
    const b = Math.round(130 + 125 * (-c));
    return `rgb(${Math.round(80 + 30 * c)},${Math.round(80 + 30 * c)},${b})`;
  }
}

// ─── 系統樹 SVG ──────────────────────────────────────────────────────────────

function renderLineage(lineage) {
  const svg = document.getElementById('lineage-svg');
  svg.innerHTML = '';

  if (!lineage || !lineage.length) {
    svg.setAttribute('width', 300); svg.setAttribute('height', 60);
    svgText(svg, 150, 30, '系統データなし', '#555', 12);
    return;
  }

  // fitness をトライアルから引く
  const fitnessMap = {};
  (_sessionData?.trials || []).forEach(t => { fitnessMap[t.genome_id] = t.fitness; });

  // 世代別にグループ分け
  const byGen = {};
  lineage.forEach(n => {
    const g = n.generation;
    if (!byGen[g]) byGen[g] = [];
    byGen[g].push(n);
  });
  const maxGen = Math.max(...Object.keys(byGen).map(Number));
  const genCount = maxGen + 1;

  const NODE_W = 100, NODE_H = 36, H_GAP = 130, V_GAP = 52;
  const maxPerGen = Math.max(...Object.values(byGen).map(a => a.length));
  const totalW = genCount * H_GAP + 20;
  const totalH = maxPerGen * V_GAP + 20;
  svg.setAttribute('width', totalW);
  svg.setAttribute('height', totalH);

  // 位置を計算
  const pos = {}; // genome_id → {x, y}
  Object.entries(byGen).forEach(([gen, nodes]) => {
    const g = Number(gen);
    nodes.forEach((n, i) => {
      const x = g * H_GAP + 10;
      const y = (i - (nodes.length - 1) / 2) * V_GAP + totalH / 2;
      pos[n.genome_id] = { x, y };
    });
  });

  // エッジ(親 → 子)を描く
  lineage.forEach(n => {
    n.parent_ids.forEach(pid => {
      const a = pos[pid], b = pos[n.genome_id];
      if (!a || !b) return;
      const mx = (a.x + NODE_W + b.x) / 2;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', `M${a.x + NODE_W},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#3a3f60');
      path.setAttribute('stroke-width', '1.2');
      svg.appendChild(path);
    });
  });

  // ノード(rect + テキスト)を描く
  lineage.forEach(n => {
    const { x, y } = pos[n.genome_id];
    const fit = fitnessMap[n.genome_id];
    const alive = (_sessionData?.trials || []).find(t => t.genome_id === n.genome_id)?.alive;
    const boxColor = fit != null ? (alive ? '#1e3a1e' : '#3a1e1e') : '#1e2030';
    const borderColor = fit != null ? (alive ? '#5cb85c' : '#e06c6c') : '#2e3244';

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x); rect.setAttribute('y', y - NODE_H / 2);
    rect.setAttribute('width', NODE_W); rect.setAttribute('height', NODE_H);
    rect.setAttribute('rx', 4); rect.setAttribute('fill', boxColor);
    rect.setAttribute('stroke', borderColor); rect.setAttribute('stroke-width', '1');
    svg.appendChild(rect);

    svgText(svg, x + NODE_W / 2, y - 5, `#${n.genome_id}`, '#aaa', 9.5);
    const fitLabel = fit != null ? `f=${fit.toFixed(2)} gen${n.generation}` : `gen${n.generation}`;
    svgText(svg, x + NODE_W / 2, y + 9, fitLabel, fit != null ? '#7c8' : '#666', 9);
  });
}

// ─── 事象ログ ────────────────────────────────────────────────────────────────

function renderEvents(events) {
  const el = document.getElementById('event-log');
  if (!events || !events.length) {
    el.innerHTML = '<div class="empty">事象ログなし</div>';
    return;
  }
  el.innerHTML = events.map(ev => {
    const ts = (ev.timestamp || '').replace('T', ' ').slice(0, 19);
    const type = ev.event || '';
    const rest = Object.fromEntries(
      Object.entries(ev).filter(([k]) => k !== 'event' && k !== 'timestamp')
    );
    const body = JSON.stringify(rest, null, 0)
      .replace(/^{|}$/g, '').replace(/"/g, '');
    return `<div class="ev-row">
      <span class="ev-time">${ts}</span>
      <span class="ev-type">${type}</span>
      <span class="ev-body">${body}</span>
    </div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

// ─── ユーティリティ ───────────────────────────────────────────────────────────

function svgText(svg, x, y, text, color, size) {
  const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  t.setAttribute('x', x); t.setAttribute('y', y);
  t.setAttribute('fill', color); t.setAttribute('font-size', size);
  t.setAttribute('text-anchor', 'middle'); t.setAttribute('dominant-baseline', 'middle');
  t.textContent = text;
  svg.appendChild(t);
}

function setStatus(msg) {
  document.getElementById('status').textContent = msg;
}

// ─── 系統樹タブ切り替え時に再描画 ────────────────────────────────────────────

document.querySelector('[data-panel="lineage"]').addEventListener('click', () => {
  if (_sessionData) renderLineage(_sessionData.lineage);
});
