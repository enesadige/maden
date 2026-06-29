import { useMemo, useState } from 'react'
import { getRiskColor, RISK_COLORS, WORKER_COLOR, WORKER_AT_RISK_COLOR, ROUTE_COLOR } from '../utils/riskColors'

const VIEW_W = 920
const VIEW_H = 580
const PAD = 36

function getCoord(seg, axis) {
  if (!seg.center) return 0
  return seg.center[axis] ?? 0
}

function buildProjection(segments, axisX, axisY) {
  const xs = segments.map(s => getCoord(s, axisX))
  const ys = segments.map(s => getCoord(s, axisY))
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  const positions = {}
  segments.forEach(s => {
    const nx = (getCoord(s, axisX) - minX) / spanX
    const ny = (getCoord(s, axisY) - minY) / spanY
    positions[s.segment_id] = {
      x: PAD + nx * (VIEW_W - PAD * 2),
      y: VIEW_H - PAD - ny * (VIEW_H - PAD * 2),
    }
  })
  return { positions, spreadArea: spanX * spanY }
}

function countOverlaps(positions, minDist = 18) {
  const pts = Object.values(positions)
  const md2 = minDist * minDist
  let count = 0
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y
      if (dx * dx + dy * dy < md2) count++
    }
  }
  return count
}

function buildGraphLayout(segments) {
  const root = segments.find(s => s.is_exit) || segments[0]
  const depths = { [root.segment_id]: 0 }
  const q = [root.segment_id]
  while (q.length) {
    const cur = q.shift()
    const seg = segments.find(s => s.segment_id === cur)
    for (const next of seg?.connected_segments || []) {
      if (!(next in depths)) { depths[next] = depths[cur] + 1; q.push(next) }
    }
  }
  segments.forEach(s => { if (!(s.segment_id in depths)) depths[s.segment_id] = 0 })
  const maxD = Math.max(...Object.values(depths)) || 1
  const byD = {}
  segments.forEach(s => { const d = depths[s.segment_id]; (byD[d] = byD[d] || []).push(s.segment_id) })
  const xStep = (VIEW_W - PAD * 2) / maxD
  const cy = VIEW_H / 2
  const positions = {}
  for (let d = 0; d <= maxD; d++) {
    const ids = byD[d] || []
    ids.forEach((id, i) => {
      const x = PAD + d * xStep
      const y = ids.length === 1
        ? cy + (d % 4 === 1 ? -50 : d % 4 === 3 ? 50 : 0)
        : cy + (i - (ids.length - 1) / 2) * 50
      positions[id] = { x, y: Math.max(PAD + 8, Math.min(VIEW_H - PAD - 8, y)) }
    })
  }
  return positions
}

function buildBestLayout(segments) {
  if (!segments.length) return {}
  if (!segments.some(s => s.center?.length >= 2)) return buildGraphLayout(segments)
  const candidates = [
    { axes: 'xy', ...buildProjection(segments, 0, 1) },
    { axes: 'xz', ...buildProjection(segments, 0, 2) },
    { axes: 'yz', ...buildProjection(segments, 1, 2) },
  ]
  const scored = candidates.map(c => ({ ...c, overlaps: countOverlaps(c.positions) }))
  scored.sort((a, b) => a.overlaps - b.overlaps || b.spreadArea - a.spreadArea)
  return scored[0].positions
}

function buildEdges(segments) {
  const seen = new Set()
  const edges = []
  segments.forEach(seg => {
    for (const otherId of seg.connected_segments || []) {
      const key = [seg.segment_id, otherId].sort().join('|')
      if (seen.has(key)) continue
      seen.add(key)
      const other = segments.find(s => s.segment_id === otherId)
      if (other) edges.push({ key, from: seg, to: other })
    }
  })
  return edges
}

export default function MineMapView({ segments, risks, workers, gasSensors, emergencyRoute, selectedSegmentId, onSegmentSelect }) {
  const [hovered, setHovered] = useState(null)

  const positions = useMemo(() => buildBestLayout(segments), [segments])
  const edges = useMemo(() => buildEdges(segments), [segments])

  const riskMap = useMemo(() => {
    const m = new Map(); risks.forEach(r => m.set(r.segment_id, r)); return m
  }, [risks])

  const workerSegs = useMemo(() => new Set(workers.map(w => w.current_segment)), [workers])
  const alarmSegs = useMemo(() => new Set((gasSensors || []).filter(s => s.status === 'alarm').map(s => s.segment_id)), [gasSensors])

  const route = emergencyRoute?.route_segments || emergencyRoute?.route || []
  const routeSet = useMemo(() => new Set(route), [route])
  const isTrapped = emergencyRoute?.trapped === true
  const isRouteSafe = !isTrapped && emergencyRoute?.exit_reachable !== false
  const blockedSeg = emergencyRoute?.blocked_segment
  const routePts = useMemo(() => route.map(id => positions[id]).filter(Boolean), [route, positions])

  function isImportant(seg) {
    const risk = riskMap.get(seg.segment_id)
    return seg.segment_id === selectedSegmentId
      || seg.segment_id === hovered
      || seg.is_blocked
      || seg.is_exit
      || seg.segment_id === blockedSeg
      || workerSegs.has(seg.segment_id)
      || alarmSegs.has(seg.segment_id)
      || routeSet.has(seg.segment_id)
      || risk?.risk_level === 'critical'
      || risk?.risk_level === 'high'
  }

  return (
    <div className="mine-map-wrapper">
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="mine-map-svg" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="mine-map-route-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={ROUTE_COLOR} />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map(edge => {
          const a = positions[edge.from.segment_id], b = positions[edge.to.segment_id]
          if (!a || !b) return null
          const blocked = edge.from.is_blocked || edge.to.is_blocked
          const onRoute = routeSet.has(edge.from.segment_id) && routeSet.has(edge.to.segment_id)
          return (
            <line
              key={edge.key}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={blocked ? RISK_COLORS.critical : onRoute ? 'rgba(52,245,197,0.35)' : 'rgba(255,255,255,0.07)'}
              strokeWidth={blocked ? 3 : onRoute ? 2 : 1}
              strokeDasharray={blocked ? '6 5' : undefined}
            />
          )
        })}

        {/* Route overlay line */}
        {routePts.length > 1 && (
          <polyline
            points={routePts.map(p => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke={isRouteSafe ? ROUTE_COLOR : RISK_COLORS.critical}
            strokeWidth={3}
            strokeDasharray={isRouteSafe ? undefined : '10 6'}
            markerEnd={isRouteSafe ? 'url(#mine-map-route-arrow)' : undefined}
            opacity={0.85}
          />
        )}

        {/* Gas sensors */}
        {(gasSensors || []).map(sensor => {
          const pos = positions[sensor.segment_id]
          if (!pos) return null
          const alarm = sensor.status === 'alarm'
          const color = alarm ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
          const sx = pos.x + 15, sy = pos.y - 17
          return (
            <g key={sensor.sensor_id}>
              {alarm && <circle cx={sx} cy={sy} r={10} fill={color} opacity={0.3} className="map-pulse" />}
              <line x1={sx} y1={sy + 7} x2={sx} y2={sy - 2} stroke="#7a8290" strokeWidth={1.5} />
              <polygon points={`${sx},${sy - 9} ${sx - 5},${sy + 1} ${sx + 5},${sy + 1}`} fill={color} />
            </g>
          )
        })}

        {/* Workers */}
        {workers.map((w, i) => {
          const pos = positions[w.current_segment]
          if (!pos) return null
          const atRisk = w.status === 'at_risk' || w.status === 'trapped'
          const color = atRisk ? WORKER_AT_RISK_COLOR : WORKER_COLOR
          const wx = pos.x - 14 + (i % 3) * 9, wy = pos.y + 17
          return (
            <g key={w.worker_id}>
              {atRisk && <circle cx={wx} cy={wy} r={9} fill="none" stroke={RISK_COLORS.critical} strokeWidth={1.5} opacity={0.85} className="map-pulse" />}
              <circle cx={wx} cy={wy} r={5} fill={color} />
              <circle cx={wx} cy={wy - 5} r={2.5} fill="#ffd23a" />
            </g>
          )
        })}

        {/* Segment nodes */}
        {segments.map(seg => {
          const pos = positions[seg.segment_id]
          if (!pos) return null
          const risk = riskMap.get(seg.segment_id)
          const color = getRiskColor(risk?.risk_level, seg.is_blocked)
          const sel = selectedSegmentId === seg.segment_id
          const imp = isImportant(seg)
          const r = sel ? 15 : imp ? 11 : 8
          const isCrit = !seg.is_blocked && risk?.risk_level === 'critical'

          return (
            <g
              key={seg.segment_id}
              className="mine-map-node"
              style={{ cursor: 'pointer' }}
              onClick={() => onSegmentSelect?.(seg.segment_id)}
              onMouseEnter={() => setHovered(seg.segment_id)}
              onMouseLeave={() => setHovered(null)}
            >
              <title>{seg.segment_id}{seg.name ? ` — ${seg.name}` : ''}{risk ? ` [${risk.risk_level}]` : ''}</title>
              {isCrit && <circle cx={pos.x} cy={pos.y} r={r + 10} fill={RISK_COLORS.critical} opacity={0.15} className="map-pulse" />}
              {seg.is_exit && <circle cx={pos.x} cy={pos.y} r={r + 7} fill="none" stroke="rgba(52,245,197,0.4)" strokeWidth={1.5} strokeDasharray="4 3" />}
              <circle
                cx={pos.x} cy={pos.y} r={r}
                fill={color}
                stroke={sel ? '#34f5c5' : seg.is_exit ? 'rgba(52,245,197,0.5)' : 'rgba(255,255,255,0.07)'}
                strokeWidth={sel ? 2.5 : 1}
                opacity={imp ? 1 : 0.65}
              />
              {seg.is_blocked && (
                <g stroke={RISK_COLORS.critical} strokeWidth={2} strokeLinecap="round">
                  <line x1={pos.x - 5} y1={pos.y - 5} x2={pos.x + 5} y2={pos.y + 5} />
                  <line x1={pos.x - 5} y1={pos.y + 5} x2={pos.x + 5} y2={pos.y - 5} />
                </g>
              )}
              {imp && (
                <text
                  x={pos.x} y={pos.y - r - 3}
                  textAnchor="middle"
                  className="mine-map-label"
                  fontSize="9"
                  opacity={sel || hovered === seg.segment_id ? 1 : 0.8}
                >
                  {seg.segment_id}
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {isTrapped && (
        <div className="mine-map-route-warning">Alternatif rota yok — işçi mahsur kalabilir.</div>
      )}
    </div>
  )
}
