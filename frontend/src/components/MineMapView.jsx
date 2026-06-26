import { useMemo } from 'react'
import { getRiskColor, RISK_COLORS, WORKER_COLOR, WORKER_AT_RISK_COLOR, ROUTE_COLOR } from '../utils/riskColors'

const SHORT_LABELS = {
  S001: 'Giriş',
  S002: 'Ana Yol',
  S003: 'Dar Galeri',
  S004: 'Riskli Bölge',
  S005: 'Derin Tünel'
}

const VIEW_W = 820
const VIEW_H = 300
const PAD = 70

// Returns true when the segment layout is too flat to be visually useful.
// Triggers whenever the X spread is more than 4× the Y spread.
function needsPresentationLayout(segments) {
  if (segments.length < 2) return false
  const xs = segments.map(s => s.center[0])
  const ys = segments.map(s => s.center[1])
  const spanX = Math.max(...xs) - Math.min(...xs) || 1
  const spanY = Math.max(...ys) - Math.min(...ys) || 0.001
  return spanX / spanY > 4
}

// BFS-based layout that positions segments in a staggered zigzag,
// starting from the exit node. Gives a mine-plan-style appearance
// without modifying any underlying data.
function buildPresentationLayout(segments) {
  const exitSeg = segments.find(s => s.is_exit) || segments[0]
  const depths = {}
  const queue = [exitSeg.segment_id]
  depths[exitSeg.segment_id] = 0

  while (queue.length) {
    const curr = queue.shift()
    const seg = segments.find(s => s.segment_id === curr)
    for (const next of seg?.connected_segments || []) {
      if (depths[next] === undefined) {
        depths[next] = depths[curr] + 1
        queue.push(next)
      }
    }
  }
  // Any segment unreachable from exit gets depth 0
  segments.forEach(s => { if (depths[s.segment_id] === undefined) depths[s.segment_id] = 0 })

  const maxDepth = Math.max(...Object.values(depths))
  const byDepth = {}
  segments.forEach(s => {
    const d = depths[s.segment_id]
    if (!byDepth[d]) byDepth[d] = []
    byDepth[d].push(s.segment_id)
  })

  const xStep = maxDepth > 0 ? (VIEW_W - PAD * 2) / maxDepth : 0
  const yCenter = VIEW_H / 2
  const yStagger = 58

  const positions = {}
  for (let d = 0; d <= maxDepth; d++) {
    const ids = byDepth[d] || []
    ids.forEach((id, i) => {
      const x = PAD + d * xStep
      let y
      if (ids.length === 1) {
        // Zigzag phase: 0→center, 1→up, 2→center, 3→down, repeating
        const phase = d % 4
        y = yCenter + (phase === 1 ? -yStagger : phase === 3 ? yStagger : 0)
      } else {
        y = yCenter + (i - (ids.length - 1) / 2) * yStagger * 1.5
      }
      // Clamp inside usable area
      positions[id] = { x, y: Math.max(PAD + 10, Math.min(VIEW_H - PAD - 10, y)) }
    })
  }
  return positions
}

function buildNaturalLayout(segments) {
  const xs = segments.map(s => s.center[0])
  const ys = segments.map(s => s.center[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1

  const positions = {}
  segments.forEach(s => {
    const nx = (s.center[0] - minX) / spanX
    const ny = (s.center[1] - minY) / spanY
    positions[s.segment_id] = {
      x: PAD + nx * (VIEW_W - PAD * 2),
      y: VIEW_H - PAD - ny * (VIEW_H - PAD * 2)
    }
  })
  return positions
}

function buildEdges(segments) {
  const seen = new Set()
  const edges = []
  segments.forEach(segment => {
    ;(segment.connected_segments || []).forEach(otherId => {
      const key = [segment.segment_id, otherId].sort().join('-')
      if (seen.has(key)) return
      seen.add(key)
      const other = segments.find(s => s.segment_id === otherId)
      if (other) edges.push({ key, from: segment, to: other })
    })
  })
  return edges
}

export default function MineMapView({
  segments,
  risks,
  workers,
  gasSensors,
  emergencyRoute,
  selectedSegmentId,
  onSegmentSelect
}) {
  const positions = useMemo(
    () => needsPresentationLayout(segments)
      ? buildPresentationLayout(segments)
      : buildNaturalLayout(segments),
    [segments]
  )
  const edges = useMemo(() => buildEdges(segments), [segments])
  const riskBySegment = useMemo(() => {
    const map = {}
    for (const risk of risks) map[risk.segment_id] = risk
    return map
  }, [risks])

  const route = emergencyRoute?.route_segments || emergencyRoute?.route || []
  const isRouteSafe = Boolean(emergencyRoute?.exit_reachable && emergencyRoute?.alternative_route_available)
  const routePoints = route.map(id => positions[id]).filter(Boolean)

  return (
    <div className="mine-map-wrapper">
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="mine-map-svg" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="mine-map-route-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={ROUTE_COLOR} />
          </marker>
        </defs>

        {/* Tunnel corridor edges */}
        {edges.map(edge => {
          const a = positions[edge.from.segment_id]
          const b = positions[edge.to.segment_id]
          if (!a || !b) return null
          const blocked = edge.from.is_blocked || edge.to.is_blocked
          return (
            <g key={edge.key}>
              {/* Wide corridor fill */}
              {!blocked && (
                <line
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke="rgba(255,255,255,0.12)" strokeWidth={22}
                  strokeLinecap="round"
                />
              )}
              {/* Corridor center line */}
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={blocked ? RISK_COLORS.critical : 'rgba(52,245,197,0.18)'}
                strokeWidth={blocked ? 10 : 2}
                strokeLinecap="round"
                strokeDasharray={blocked ? '10 8' : undefined}
                opacity={blocked ? 0.85 : 1}
              />
              {/* Dark fill to give depth */}
              {!blocked && (
                <line
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke="#0b0d14" strokeWidth={16}
                  strokeLinecap="round"
                />
              )}
              {/* Faint center guide */}
              {!blocked && (
                <line
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke="rgba(52,245,197,0.08)" strokeWidth={1}
                  strokeDasharray="6 8"
                />
              )}
            </g>
          )
        })}

        {/* Emergency route */}
        {routePoints.length > 1 && (
          <polyline
            points={routePoints.map(p => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke={isRouteSafe ? ROUTE_COLOR : RISK_COLORS.critical}
            strokeWidth={6}
            strokeLinecap="round"
            strokeDasharray={isRouteSafe ? undefined : '12 8'}
            markerEnd={isRouteSafe ? 'url(#mine-map-route-arrow)' : undefined}
            opacity={0.85}
          />
        )}

        {/* Gas sensor icons */}
        {(gasSensors || []).map(sensor => {
          const pos = positions[sensor.segment_id]
          if (!pos) return null
          const isAlarm = sensor.status === 'alarm'
          const color = isAlarm ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
          const sx = pos.x + 26
          const sy = pos.y - 26
          return (
            <g key={sensor.sensor_id}>
              {isAlarm && (
                <g className="map-pulse" style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
                  <circle cx={sx} cy={sy} r={14} fill={color} opacity={0.35} />
                </g>
              )}
              <line x1={sx} y1={sy + 10} x2={sx} y2={sy - 4} stroke="#7a8290" strokeWidth={2} />
              <polygon
                points={`${sx},${sy - 12} ${sx - 7},${sy - 2} ${sx + 7},${sy - 2}`}
                fill={color} stroke="#0c0e13" strokeWidth={1}
              />
            </g>
          )
        })}

        {/* Worker icons */}
        {workers.map((worker, idx) => {
          const pos = positions[worker.current_segment]
          if (!pos) return null
          const atRisk = worker.status === 'at_risk'
          const color = atRisk ? WORKER_AT_RISK_COLOR : WORKER_COLOR
          const wx = pos.x - 24 + (idx % 2) * 14
          const wy = pos.y + 26
          return (
            <g key={worker.worker_id}>
              {atRisk && (
                <g className="map-pulse" style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
                  <circle cx={wx} cy={wy} r={14} fill="none" stroke={RISK_COLORS.critical} strokeWidth={2} opacity={0.8} />
                </g>
              )}
              <path
                d={`M${wx - 6},${wy + 6} C${wx - 6},${wy - 2} ${wx - 4},${wy - 6} ${wx},${wy - 6} C${wx + 4},${wy - 6} ${wx + 6},${wy - 2} ${wx + 6},${wy + 6} Z`}
                fill={color} stroke="#0b0d14" strokeWidth={1.5}
              />
              <circle cx={wx} cy={wy - 6} r={3.5} fill="#ffd23a" />
            </g>
          )
        })}

        {/* Segment nodes */}
        {segments.map(segment => {
          const pos = positions[segment.segment_id]
          if (!pos) return null
          const risk = riskBySegment[segment.segment_id]
          const blocked = segment.is_blocked
          const color = getRiskColor(risk?.risk_level, segment.is_blocked)
          const isSelected = selectedSegmentId === segment.segment_id
          const isCritical = !blocked && risk?.risk_level === 'critical'
          const isExit = segment.is_exit

          return (
            <g
              key={segment.segment_id}
              className="mine-map-node"
              onClick={() => onSegmentSelect?.(segment.segment_id)}
            >
              {isCritical && (
                <g className="map-pulse" style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
                  <circle cx={pos.x} cy={pos.y} r={28} fill={RISK_COLORS.critical} opacity={0.18} />
                </g>
              )}

              {/* Exit marker ring */}
              {isExit && (
                <circle
                  cx={pos.x} cy={pos.y} r={26}
                  fill="none"
                  stroke="rgba(52,245,197,0.35)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                />
              )}

              {/* Main node circle */}
              <circle
                cx={pos.x} cy={pos.y}
                r={isSelected ? 22 : 18}
                fill={color}
                stroke={isSelected ? '#34f5c5' : isExit ? 'rgba(52,245,197,0.5)' : 'rgba(255,255,255,0.1)'}
                strokeWidth={isSelected ? 3 : isExit ? 2 : 1.5}
              />

              {/* Inner depth shadow */}
              <circle cx={pos.x} cy={pos.y} r={10} fill="#0b0d14" opacity={0.3} />

              {/* Blocked X */}
              {blocked && (
                <g stroke={RISK_COLORS.critical} strokeWidth={3} strokeLinecap="round">
                  <line x1={pos.x - 9} y1={pos.y - 9} x2={pos.x + 9} y2={pos.y + 9} />
                  <line x1={pos.x - 9} y1={pos.y + 9} x2={pos.x + 9} y2={pos.y - 9} />
                </g>
              )}

              {/* Label */}
              <text x={pos.x} y={pos.y - 28} textAnchor="middle" className="mine-map-label">
                {segment.segment_id}
                {SHORT_LABELS[segment.segment_id] ? ` · ${SHORT_LABELS[segment.segment_id]}` : ''}
              </text>
            </g>
          )
        })}
      </svg>

      {emergencyRoute && !isRouteSafe && (
        <div className="mine-map-route-warning">Alternatif rota yok — işçi mahsur kalabilir.</div>
      )}
    </div>
  )
}
