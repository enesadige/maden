from __future__ import annotations

import json

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.io_utils import read_json, write_json
from madenguard.las_utils import read_points_npz


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    sample_targets = [int(value) for value in config["runtime"].get("lidar_sample_targets", [50000])]
    point_limit = int(config["runtime"].get("dashboard_point_limit", 6000))
    sample_path = project_path("processed", "lidar_samples", f"mediumres_sample_{sample_targets[0]//1000}k.npz")
    points = read_points_npz(sample_path, limit=point_limit)
    segments = read_json(project_path("simulation_ready", "segments.json"))
    workers = read_json(project_path("simulation_ready", "workers_timeline.json"))
    gas = read_json(project_path("simulation_ready", "gas_sensors_timeline.json"))
    risk = read_json(project_path("simulation_ready", "final_segment_risk_timeline.json"))
    lidar_geometry = read_json(project_path("simulation_ready", "lidar_geometry_risk.json"))
    emergency = read_json(project_path("simulation_ready", "emergency_result.json"))

    xs = [p[0] for p in points] or [0.0]
    ys = [p[1] for p in points] or [0.0]
    zs = [p[2] for p in points] or [0.0]
    bounds = {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "min_z": min(zs),
        "max_z": max(zs),
    }
    point_payload = [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in points]
    top_risk = sorted(risk, key=lambda item: item["final_segment_risk"], reverse=True)[:15]
    segment_positions = {
        row["segment_id"]: [
            round(float(row.get("centroid_x", 0.0)), 2),
            round(float(row.get("centroid_y", 0.0)), 2),
            round(float(row.get("centroid_z", 0.0)), 2),
        ]
        for row in lidar_geometry
    }
    payload = {
        "points": point_payload,
        "bounds": bounds,
        "segments": segments,
        "segmentPositions": segment_positions,
        "workers": workers,
        "gas": gas,
        "riskTimeline": risk,
        "topRisk": top_risk,
        "emergency": emergency,
        "sampleTarget": sample_targets[0],
        "renderLimit": point_limit,
        "maxTime": max([int(row["time_step"]) for row in risk] or [0]),
    }

    html = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MadenGuard AI 3B Maden Simülasyonu</title>
  <style>
    :root { color-scheme: light; font-family: Arial, Helvetica, sans-serif; }
    body { margin: 0; background: #edf1ee; color: #17211b; }
    header { padding: 12px 22px; border-bottom: 1px solid #d6ded8; background: #ffffff; }
    h1 { margin: 0; font-size: 21px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 390px; min-height: calc(100vh - 59px); }
    .viewport { position: relative; min-width: 0; background: #07110e; }
    #scene { width: 100%; height: calc(100vh - 59px); display: block; background: radial-gradient(circle at 50% 42%, #13221c 0%, #07110e 72%); }
    .hud {
      position: absolute;
      left: 16px;
      top: 16px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      pointer-events: none;
    }
    .chip {
      background: rgba(238, 246, 241, 0.9);
      color: #142018;
      border: 1px solid rgba(255, 255, 255, 0.35);
      border-radius: 5px;
      padding: 6px 8px;
      font-size: 12px;
      font-weight: 700;
    }
    .timeline {
      position: absolute;
      left: 16px;
      top: 58px;
      width: min(640px, calc(100% - 32px));
      display: grid;
      grid-template-columns: 42px 1fr 72px;
      align-items: center;
      gap: 10px;
      background: rgba(238, 246, 241, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.4);
      border-radius: 7px;
      padding: 8px;
    }
    .timeline button {
      height: 34px;
      border: 0;
      border-radius: 5px;
      background: #17211b;
      color: #fff;
      font-size: 16px;
      cursor: pointer;
    }
    .timeline input { width: 100%; }
    .timeline output { text-align: right; font-size: 13px; font-weight: 700; }
    .legend {
      position: absolute;
      left: 16px;
      bottom: 16px;
      width: min(420px, calc(100% - 32px));
      display: grid;
      gap: 6px;
      background: rgba(238, 246, 241, 0.93);
      border: 1px solid rgba(255, 255, 255, 0.4);
      border-radius: 7px;
      padding: 10px;
      color: #142018;
      font-size: 12px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
    }
    .legend-title { font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .legend-row { display: grid; grid-template-columns: 14px 1fr; gap: 8px; align-items: center; }
    .dot { width: 10px; height: 10px; border-radius: 999px; border: 1px solid rgba(20, 32, 24, 0.25); }
    .dot.cloud { background: #dbe9e0; }
    .dot.worker { background: #3ad0ff; }
    .dot.normal { background: #4ed26c; }
    .dot.medium { background: #ffd547; }
    .dot.high { background: #ff7a1a; }
    .dot.critical { background: #ff3a28; }
    aside { padding: 18px; overflow: auto; border-left: 1px solid #d7ded8; background: #ffffff; }
    h2 { font-size: 16px; margin: 18px 0 8px; }
    .metric { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; padding: 8px 0; border-bottom: 1px solid #edf1ee; font-size: 14px; align-items: center; }
    .metric strong { min-width: 0; overflow-wrap: anywhere; text-align: right; }
    .risk { padding: 3px 8px; border-radius: 4px; font-weight: 700; }
    .LOW { background: #dff3e3; color: #135f2a; }
    .MEDIUM { background: #fff1bf; color: #795400; }
    .HIGH { background: #ffe0c7; color: #8a3a00; }
    .CRITICAL { background: #ffd1d1; color: #9c1111; }
    p, li { font-size: 14px; line-height: 1.4; }
    code { background: #edf1ee; padding: 2px 4px; border-radius: 4px; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid #d7ded8; } #scene { height: 58vh; } }
  </style>
</head>
<body>
  <header><h1>MadenGuard AI 3B Maden Simülasyonu</h1></header>
  <main>
    <section class="viewport">
      <canvas id="scene"></canvas>
      <div class="hud">
        <div class="chip">WebGL 3D</div>
        <div class="chip" id="pointCount"></div>
        <div class="chip">Z x18</div>
        <div class="chip" id="simState"></div>
      </div>
      <div class="timeline">
        <button id="playButton" type="button">▶</button>
        <input id="timeSlider" type="range" min="0" max="0" value="0" step="1">
        <output id="timeValue">t=0</output>
      </div>
      <div class="legend">
        <div class="legend-title">Renk Lejandı</div>
        <div class="legend-row"><span class="dot cloud"></span><span>Beyaz/gri noktalar: LiDAR nokta bulutu, yani tünelin 3B geometri örneği.</span></div>
        <div class="legend-row"><span class="dot worker"></span><span>Mavi: UWB ile haritalanan işçi konumu ve hareket izi.</span></div>
        <div class="legend-row"><span class="dot normal"></span><span>Yeşil: normal gaz sensörü veya düşük riskli segment.</span></div>
        <div class="legend-row"><span class="dot medium"></span><span>Sarı: orta riskli segment.</span></div>
        <div class="legend-row"><span class="dot high"></span><span>Turuncu: yüksek riskli segment.</span></div>
        <div class="legend-row"><span class="dot critical"></span><span>Kırmızı: yüksek/kritik risk veya olay sonrası kapanan segment.</span></div>
      </div>
    </section>
    <aside>
      <h2>Simülasyon Durumu</h2>
      <div id="status"></div>
      <h2>Risk Açıklaması</h2>
      <div id="breakdown"></div>
      <h2>Anlık Risk Sıralaması</h2>
      <div id="riskList"></div>
      <h2>Veri Notu</h2>
      <p>Ham LAS dosyası flash diskte kalır. Bu ekran 316 milyon noktanın tamamını tarayıcıya yüklemez; güvenli ve hızlı görüntü için örneklenmiş WebGL katmanı kullanır.</p>
    </aside>
  </main>
  <script>
    const DATA = __DATA_JSON__;
    const canvas = document.getElementById('scene');
    const gl = canvas.getContext('webgl', { antialias: true, alpha: false });
    if (!gl) {
      document.querySelector('.viewport').innerHTML = '<p style="color:#fff;padding:24px">WebGL is not available in this browser.</p>';
      throw new Error('WebGL unavailable');
    }

    const vertexShaderSource = `
      attribute vec3 aPosition;
      attribute vec3 aColor;
      uniform mat4 uMvp;
      uniform float uPointSize;
      varying vec3 vColor;
      void main() {
        gl_Position = uMvp * vec4(aPosition, 1.0);
        gl_PointSize = uPointSize;
        vColor = aColor;
      }
    `;
    const fragmentShaderSource = `
      precision mediump float;
      varying vec3 vColor;
      void main() {
        vec2 center = gl_PointCoord - vec2(0.5);
        if (dot(center, center) > 0.25) discard;
        gl_FragColor = vec4(vColor, 1.0);
      }
    `;

    function compileShader(type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(shader));
      }
      return shader;
    }

    const program = gl.createProgram();
    gl.attachShader(program, compileShader(gl.VERTEX_SHADER, vertexShaderSource));
    gl.attachShader(program, compileShader(gl.FRAGMENT_SHADER, fragmentShaderSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program));
    }
    gl.useProgram(program);

    const loc = {
      position: gl.getAttribLocation(program, 'aPosition'),
      color: gl.getAttribLocation(program, 'aColor'),
      mvp: gl.getUniformLocation(program, 'uMvp'),
      pointSize: gl.getUniformLocation(program, 'uPointSize')
    };

    const b = DATA.bounds;
    const center = [
      (b.min_x + b.max_x) / 2,
      (b.min_y + b.max_y) / 2,
      (b.min_z + b.max_z) / 2
    ];
    const xySpan = Math.max(b.max_x - b.min_x, b.max_y - b.min_y, 1);
    const scale = 2.25 / xySpan;
    const zBoost = 18;

    function scenePoint(p) {
      return [
        (p[0] - center[0]) * scale,
        (p[2] - center[2]) * scale * zBoost,
        (p[1] - center[1]) * scale
      ];
    }

    function colorForLevel(level) {
      if (level === 'CRITICAL') return [1.0, 0.12, 0.10];
      if (level === 'HIGH') return [1.0, 0.46, 0.05];
      if (level === 'MEDIUM') return [1.0, 0.82, 0.18];
      return [0.20, 0.78, 0.35];
    }

    function makeBuffer(items) {
      const positions = new Float32Array(items.flatMap(item => item.position));
      const colors = new Float32Array(items.flatMap(item => item.color));
      const posBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
      const colorBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, colors, gl.STATIC_DRAW);
      return { posBuffer, colorBuffer, count: items.length };
    }

    const cloudItems = DATA.points.map(p => {
      const z01 = (p[2] - b.min_z) / Math.max(1e-9, b.max_z - b.min_z);
      return {
        position: scenePoint(p),
        color: [0.58 + z01 * 0.30, 0.68 + z01 * 0.24, 0.62 + z01 * 0.22]
      };
    });

    function pointForSegment(segmentId, lift = 0) {
      const segmentPoint = DATA.segmentPositions[String(segmentId)];
      if (segmentPoint) {
        const pos = scenePoint(segmentPoint);
        pos[1] += lift;
        return pos;
      }
      const segNo = Number(String(segmentId).replace('SEG_', '')) || 1;
      const point = DATA.points[Math.min(DATA.points.length - 1, Math.floor((segNo / 50) * DATA.points.length))] || DATA.points[0];
      const pos = scenePoint(point);
      pos[1] += lift;
      return pos;
    }

    function riskRowsAt(timeStep) {
      return DATA.riskTimeline
        .filter(row => row.time_step === timeStep)
        .sort((a, b) => b.final_segment_risk - a.final_segment_risk);
    }

    function makeRiskItemsForTime(timeStep) {
      const items = riskRowsAt(timeStep).slice(0, 15).map((risk, idx) => ({
        position: pointForSegment(risk.segment_id, 0.18 + (idx % 4) * 0.045),
        color: colorForLevel(risk.risk_level)
      }));
      if (timeStep >= DATA.emergency.time_step) {
        items.push({
          position: pointForSegment(DATA.emergency.blocked_segment, 0.55),
          color: [1.0, 0.02, 0.01]
        });
      }
      return items;
    }

    function workerForTime(timeStep) {
      if (timeStep >= DATA.emergency.time_step && !DATA.emergency.exit_reachable_after_blockage) {
        return {
          time_step: timeStep,
          mapped_segment_id: DATA.emergency.worker_segment,
          motion_status: 'trapped'
        };
      }
      return DATA.workers.find(worker => worker.time_step === timeStep) || DATA.workers[0];
    }

    function makeWorkerItemsForTime(timeStep) {
      const worker = workerForTime(timeStep);
      const pos = pointForSegment(worker?.mapped_segment_id || DATA.emergency.worker_segment, 0.42);
      return [{ position: pos, color: [0.23, 0.82, 1.0] }];
    }

    function makeWorkerTrailItems(timeStep) {
      const path = [];
      for (let t = 0; t <= timeStep; t += 1) {
        const worker = workerForTime(t);
        if (worker?.mapped_segment_id) {
          path.push(pointForSegment(worker.mapped_segment_id, 0.34));
        }
      }
      const items = [];
      for (let i = 1; i < path.length; i += 1) {
        items.push({ position: path[i - 1], color: [0.12, 0.55, 0.95] });
        items.push({ position: path[i], color: [0.23, 0.82, 1.0] });
      }
      return items;
    }

    function makeGasItemsForTime(timeStep) {
      return DATA.gas
        .filter(row => row.time_step === timeStep)
        .slice(0, 8)
        .map(row => ({
          position: pointForSegment(row.segment_id, 0.28),
          color: row.methane_risk_score >= 60 ? [0.95, 0.20, 0.12] : [0.35, 0.95, 0.55]
        }));
    }

    const axesItems = [
      { position: [-1.3, -0.72, -1.15], color: [0.85, 0.25, 0.22] },
      { position: [1.3, -0.72, -1.15], color: [0.85, 0.25, 0.22] },
      { position: [-1.3, -0.72, -1.15], color: [0.25, 0.80, 0.35] },
      { position: [-1.3, 0.45, -1.15], color: [0.25, 0.80, 0.35] },
      { position: [-1.3, -0.72, -1.15], color: [0.30, 0.55, 1.0] },
      { position: [-1.3, -0.72, 1.15], color: [0.30, 0.55, 1.0] }
    ];

    const cloudBuffer = makeBuffer(cloudItems);
    let riskBuffer = makeBuffer(makeRiskItemsForTime(0));
    let workerBuffer = makeBuffer(makeWorkerItemsForTime(0));
    let workerTrailBuffer = makeBuffer(makeWorkerTrailItems(0));
    let gasBuffer = makeBuffer(makeGasItemsForTime(0));
    const axesBuffer = makeBuffer(axesItems);
    let currentTime = 0;
    let playing = false;
    let timer = null;

    let yaw = 0.72;
    let pitch = 0.48;
    let radius = 3.35;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    canvas.addEventListener('pointerdown', event => {
      dragging = true;
      canvas.setPointerCapture(event.pointerId);
      lastX = event.clientX;
      lastY = event.clientY;
    });
    canvas.addEventListener('pointermove', event => {
      if (!dragging) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      yaw += dx * 0.008;
      pitch = Math.max(-1.15, Math.min(1.15, pitch + dy * 0.006));
      lastX = event.clientX;
      lastY = event.clientY;
      draw();
    });
    canvas.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      radius = Math.max(1.4, Math.min(7.0, radius + event.deltaY * 0.0025));
      draw();
    }, { passive: false });

    function perspective(fovy, aspect, near, far) {
      const f = 1 / Math.tan(fovy / 2);
      const nf = 1 / (near - far);
      return [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) * nf, -1,
        0, 0, (2 * far * near) * nf, 0
      ];
    }

    function normalize(v) {
      const len = Math.hypot(v[0], v[1], v[2]) || 1;
      return [v[0] / len, v[1] / len, v[2] / len];
    }

    function cross(a, b) {
      return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0]
      ];
    }

    function dot(a, b) {
      return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    }

    function lookAt(eye, target, up) {
      const z = normalize([eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]]);
      const x = normalize(cross(up, z));
      const y = cross(z, x);
      return [
        x[0], y[0], z[0], 0,
        x[1], y[1], z[1], 0,
        x[2], y[2], z[2], 0,
        -dot(x, eye), -dot(y, eye), -dot(z, eye), 1
      ];
    }

    function multiply(a, b) {
      const out = new Array(16).fill(0);
      for (let row = 0; row < 4; row++) {
        for (let col = 0; col < 4; col++) {
          for (let i = 0; i < 4; i++) {
            out[col * 4 + row] += a[i * 4 + row] * b[col * 4 + i];
          }
        }
      }
      return out;
    }

    function bindAndDraw(buffer, mode, pointSize) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer.posBuffer);
      gl.enableVertexAttribArray(loc.position);
      gl.vertexAttribPointer(loc.position, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer.colorBuffer);
      gl.enableVertexAttribArray(loc.color);
      gl.vertexAttribPointer(loc.color, 3, gl.FLOAT, false, 0, 0);
      gl.uniform1f(loc.pointSize, pointSize * devicePixelRatio);
      gl.drawArrays(mode, 0, buffer.count);
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * devicePixelRatio);
      canvas.height = Math.floor(rect.height * devicePixelRatio);
      gl.viewport(0, 0, canvas.width, canvas.height);
      draw();
    }

    function draw() {
      const aspect = Math.max(1, canvas.width) / Math.max(1, canvas.height);
      const eye = [
        radius * Math.cos(pitch) * Math.sin(yaw),
        radius * Math.sin(pitch),
        radius * Math.cos(pitch) * Math.cos(yaw)
      ];
      const projection = perspective(Math.PI / 4, aspect, 0.05, 30);
      const view = lookAt(eye, [0, 0, 0], [0, 1, 0]);
      const mvp = multiply(projection, view);
      gl.uniformMatrix4fv(loc.mvp, false, new Float32Array(mvp));
      gl.enable(gl.DEPTH_TEST);
      gl.clearColor(0.027, 0.067, 0.055, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      bindAndDraw(axesBuffer, gl.LINES, 2.0);
      bindAndDraw(cloudBuffer, gl.POINTS, 2.1);
      bindAndDraw(gasBuffer, gl.POINTS, 10.0);
      bindAndDraw(riskBuffer, gl.POINTS, 13.0);
      bindAndDraw(workerTrailBuffer, gl.LINES, 2.0);
      bindAndDraw(workerBuffer, gl.POINTS, 17.0);
    }

    function scenarioCode(timeStep) {
      const e = DATA.emergency;
      if (timeStep < e.time_step) return 'NORMAL_TIMELINE';
      if (timeStep === e.time_step) return e.event.event_type;
      if (!e.exit_reachable_after_blockage) return 'WORKER_TRAPPED_AFTER_EVENT';
      return 'WORKER_FOLLOWING_ALTERNATIVE_ROUTE';
    }

    function scenarioLabel(timeStep) {
      const labels = {
        NORMAL_TIMELINE: 'Normal akış',
        HIGHEST_RISK_SEGMENT_ROUTE_STRESS_TEST: 'Risk anı / rota testi',
        WORKER_TRAPPED_AFTER_EVENT: 'İşçi olay sonrası mahsur',
        WORKER_FOLLOWING_ALTERNATIVE_ROUTE: 'İşçi alternatif rotada'
      };
      return labels[scenarioCode(timeStep)] || scenarioCode(timeStep);
    }

    function breakdownLabel(key) {
      const labels = {
        lidar: 'LiDAR',
        graph: 'Graf',
        gas: 'Gaz',
        worker: 'İşçi',
        methane: 'Metan riski',
        gas_risk: 'Gaz riski',
        worker_exposure: 'İşçi maruziyeti',
        lidar_geometry_risk: 'LiDAR geometri riski',
        graph_risk: 'Graf/kaçış yolu riski',
        sensor_reliability_penalty: 'Sensör güvenilirlik cezası'
      };
      return labels[key] || key.replaceAll('_', ' ');
    }

    function breakdownValue(value) {
      return String(value)
        .replace('LiDAR geometry risk', 'LiDAR geometri riski')
        .replace('Graph blocking risk', 'Graf/kaçış yolu kapanma riski')
        .replace('Methane risk', 'Metan riski')
        .replace('confidence-adjusted', 'güven düzeltmeli')
        .replace('worker is inside this segment', 'işçi bu segmentte')
        .replace('no active worker exposure', 'aktif işçi maruziyeti yok');
    }

    function renderPanel(timeStep = currentTime) {
      const e = DATA.emergency;
      const worker = workerForTime(timeStep);
      const currentRisks = riskRowsAt(timeStep).slice(0, 15);
      const top = currentRisks[0] || e.event;
      const rb = top.reason_breakdown || e.event.reason_breakdown || {};
      document.getElementById('status').innerHTML = `
        <div class="metric"><span>Zaman adımı</span><strong>${timeStep}</strong></div>
        <div class="metric"><span>İşçi segmenti</span><strong>${worker?.mapped_segment_id || e.worker_segment}</strong></div>
        <div class="metric"><span>En riskli segment</span><strong>${top.segment_id}</strong></div>
        <div class="metric"><span>Kapanan segment</span><strong>${timeStep >= e.time_step ? e.blocked_segment : 'yok'}</strong></div>
        <div class="metric"><span>Çıkış erişilebilir mi?</span><strong>${timeStep >= e.time_step ? (e.exit_reachable_after_blockage ? 'evet' : 'hayır') : 'henüz hesaplanmadı'}</strong></div>
        <div class="metric"><span>Durum</span><strong>${scenarioLabel(timeStep)}</strong></div>
        <div class="metric"><span>Alternatif rota</span><strong>${e.alternative_route_to_exit ? e.alternative_route_to_exit.join(' -> ') : 'yok'}</strong></div>
      `;
      document.getElementById('breakdown').innerHTML = Object.keys(rb).map(k => `<p><strong>${breakdownLabel(k)}</strong>: ${breakdownValue(rb[k])}</p>`).join('');
      document.getElementById('riskList').innerHTML = currentRisks.map(r => `
        <div class="metric">
          <span><code>${r.segment_id}</code> t=${r.time_step}</span>
          <span class="risk ${r.risk_level}">${r.final_segment_risk}</span>
        </div>
      `).join('');
      document.getElementById('pointCount').textContent = `${DATA.points.length} render / ${DATA.sampleTarget} sample`;
      document.getElementById('simState').textContent = scenarioLabel(timeStep);
    }

    function setTime(timeStep) {
      currentTime = Math.max(0, Math.min(DATA.maxTime, Number(timeStep) || 0));
      riskBuffer = makeBuffer(makeRiskItemsForTime(currentTime));
      workerBuffer = makeBuffer(makeWorkerItemsForTime(currentTime));
      workerTrailBuffer = makeBuffer(makeWorkerTrailItems(currentTime));
      gasBuffer = makeBuffer(makeGasItemsForTime(currentTime));
      document.getElementById('timeSlider').value = String(currentTime);
      document.getElementById('timeValue').textContent = `t=${currentTime}`;
      renderPanel(currentTime);
      draw();
    }

    function togglePlay() {
      playing = !playing;
      document.getElementById('playButton').textContent = playing ? 'Ⅱ' : '▶';
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (playing) {
        timer = setInterval(() => {
          const next = currentTime >= DATA.maxTime ? 0 : currentTime + 1;
          setTime(next);
        }, 450);
      }
    }

    document.getElementById('timeSlider').max = String(DATA.maxTime);
    document.getElementById('timeSlider').addEventListener('input', event => setTime(event.target.value));
    document.getElementById('playButton').addEventListener('click', togglePlay);
    addEventListener('resize', resize);
    setTime(0);
    resize();
  </script>
</body>
</html>
""".replace("__DATA_JSON__", json.dumps(payload))
    dashboard_path = project_path("dashboards", "madenguard_dashboard.html")
    dashboard_path.write_text(html, encoding="utf-8")
    summary = {
        "dashboard": str(dashboard_path),
        "embedded_points": len(points),
        "risk_records": len(risk),
        "emergency_status": emergency["emergency_status"],
        "raw_las_policy": "raw LAS was not embedded or copied",
    }
    write_json(project_path("dashboards", "madenguard_dashboard_summary.json"), summary)
    print(f"Wrote {dashboard_path}")


if __name__ == "__main__":
    main()
