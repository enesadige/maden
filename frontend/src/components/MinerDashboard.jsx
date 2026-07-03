import { getRiskColor, getRiskLabel } from '../utils/riskColors'
import { formatWorkerName } from '../utils/idNormalize'

const ROUTE_MAP_W = 420
const ROUTE_MAP_H = 210
const ROUTE_MAP_PAD = 28

function buildActionMessage({ riskLevel, isBlocked, emergencyRoute, isAffectedWorker }) {
  if (isBlocked) {
    return 'Bulunduğun segment kapalı. Yerinde kal, kurtarma talimatı bekle.'
  }

  if (isAffectedWorker && emergencyRoute) {
    if (emergencyRoute.trapped === true) {
      return 'Çıkışa güvenli rota yok. Bulunduğun yerde kal, kurtarma talimatı bekle.'
    }
    // Show evacuation route only in non-normal emergency scenarios
    const scenarioId = emergencyRoute.scenario_id
    if (scenarioId && scenarioId !== 'normal') {
      const routeSegments = emergencyRoute.route_segments || emergencyRoute.route
      if (routeSegments?.length) {
        return `Tahliye rotasını takip et. Haritadaki sarı rota ${routeSegments[routeSegments.length - 1]} çıkışına götürür.`
      }
    }
  }

  if (riskLevel === 'critical' || riskLevel === 'high') {
    return 'Bulunduğun bölgede risk yüksek. Mümkünse güvenli segmente geç.'
  }

  return 'Durum normal. Standart rota geçerli.'
}

function buildAlarmState({ isBlocked, riskLevel, isAffectedWorker, emergencyRoute, hasGasAlarm }) {
  const isTrapped = isAffectedWorker && emergencyRoute?.trapped === true

  if (isBlocked || isTrapped) {
    return {
      level: 'critical',
      title: isBlocked ? 'BÖLGEN KAPALI' : 'MAHSUR KALDIN — ALTERNATİF ROTA YOK',
      subtitle: 'Yerinde kal. Kurtarma ekibi yönlendirilene kadar hareket etme.'
    }
  }

  if (hasGasAlarm) {
    return {
      level: 'critical',
      title: 'METAN ALARMI — YAKININDA',
      subtitle: 'Gaz alarmı aktif. Talimat bekle, gerekirse güvenli segmente geç.'
    }
  }

  if (riskLevel === 'critical' || riskLevel === 'high') {
    return {
      level: 'warning',
      title: 'YÜKSEK RİSK BÖLGESİ',
      subtitle: 'Dikkatli ol, durumu takip et.'
    }
  }

  return {
    level: 'safe',
    title: 'DURUM NORMAL',
    subtitle: 'Standart rota geçerli, aktif bir tehlike bildirilmedi.'
  }
}

function RouteMiniMap({ route, currentSegment, blockedSegment }) {
  if (!route?.length) return null

  return (
    <div className="mini-route-map">
      {route.map((segmentId, index) => {
        const isCurrent = segmentId === currentSegment
        const isBlocked = segmentId === blockedSegment
        const chipClass = [
          'mini-route-chip',
          isCurrent ? 'mini-route-chip--current' : '',
          isBlocked ? 'mini-route-chip--blocked' : ''
        ].filter(Boolean).join(' ')

        return (
          <span key={`${segmentId}-${index}`} style={{ display: 'inline-flex', alignItems: 'center' }}>
            <span className={chipClass}>{segmentId}</span>
            {index < route.length - 1 && <span className="mini-route-arrow">→</span>}
          </span>
        )
      })}
    </div>
  )
}

function buildMiniMapPositions(segments) {
  const points = segments
    .map((segment) => {
      const center = segment.center
      if (!center) return null
      return {
        segmentId: segment.segment_id,
        x: Number(center[0]) || 0,
        y: Number(center[1]) || 0,
        z: Number(center[2]) || 0
      }
    })
    .filter(Boolean)

  if (!points.length) return new Map()

  const ranges = [
    { axes: ['x', 'y'], area: 0 },
    { axes: ['x', 'z'], area: 0 },
    { axes: ['y', 'z'], area: 0 }
  ].map((candidate) => {
    const valuesA = points.map((point) => point[candidate.axes[0]])
    const valuesB = points.map((point) => point[candidate.axes[1]])
    return {
      ...candidate,
      minA: Math.min(...valuesA),
      maxA: Math.max(...valuesA),
      minB: Math.min(...valuesB),
      maxB: Math.max(...valuesB)
    }
  }).map((candidate) => ({
    ...candidate,
    spanA: candidate.maxA - candidate.minA || 1,
    spanB: candidate.maxB - candidate.minB || 1,
    area: (candidate.maxA - candidate.minA || 1) * (candidate.maxB - candidate.minB || 1)
  })).sort((a, b) => b.area - a.area)[0]

  return new Map(points.map((point) => {
    const normalizedA = (point[ranges.axes[0]] - ranges.minA) / ranges.spanA
    const normalizedB = (point[ranges.axes[1]] - ranges.minB) / ranges.spanB
    return [point.segmentId, {
      segmentId: point.segmentId,
      x: ROUTE_MAP_PAD + normalizedA * (ROUTE_MAP_W - ROUTE_MAP_PAD * 2),
      y: ROUTE_MAP_H - ROUTE_MAP_PAD - normalizedB * (ROUTE_MAP_H - ROUTE_MAP_PAD * 2)
    }]
  }))
}

function buildMiniMapEdges(segments, positionMap) {
  const seen = new Set()
  const edges = []
  for (const segment of segments) {
    for (const connectedId of segment.connected_segments || []) {
      const key = [segment.segment_id, connectedId].sort().join('|')
      if (seen.has(key)) continue
      seen.add(key)
      const from = positionMap.get(segment.segment_id)
      const to = positionMap.get(connectedId)
      if (from && to) edges.push({ key, from, to })
    }
  }
  return edges
}

function DynamicRouteMap({ route, segments, currentSegment, blockedSegment, exitSegment }) {
  const positionMap = buildMiniMapPositions(segments)
  const positions = route.map((segmentId) => positionMap.get(segmentId)).filter(Boolean)
  if (positionMap.size < 2 || positions.length < 2) return null

  const routeSet = new Set(route)
  const allEdges = buildMiniMapEdges(segments, positionMap)
  const currentIndex = route.indexOf(currentSegment)
  const currentPoint = positions.find((point) => point.segmentId === currentSegment) || positions[0]
  const exitPoint = positions.find((point) => point.segmentId === exitSegment) || positions[positions.length - 1]
  const completedPoints = currentIndex > 0 ? positions.slice(0, currentIndex + 1) : []
  const remainingPoints = currentIndex >= 0 ? positions.slice(currentIndex) : positions

  return (
    <div className="miner-route-visual">
      <svg viewBox={`0 0 ${ROUTE_MAP_W} ${ROUTE_MAP_H}`} className="miner-route-svg" role="img" aria-label="Dinamik çıkış rotası">
        <defs>
          <marker id="miner-route-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#ffe45e" />
          </marker>
        </defs>

        {allEdges.map((edge) => {
          const onRoute = routeSet.has(edge.from.segmentId) && routeSet.has(edge.to.segmentId)
          return (
            <line
              key={edge.key}
              x1={edge.from.x}
              y1={edge.from.y}
              x2={edge.to.x}
              y2={edge.to.y}
              className={onRoute ? 'miner-route-bg-edge miner-route-bg-edge--route' : 'miner-route-bg-edge'}
            />
          )
        })}

        {segments.map((segment) => {
          const point = positionMap.get(segment.segment_id)
          if (!point) return null
          const onRoute = routeSet.has(segment.segment_id)
          return (
            <circle
              key={`context-${segment.segment_id}`}
              cx={point.x}
              cy={point.y}
              r={onRoute ? 3.8 : 2.4}
              className={onRoute ? 'miner-route-context-node miner-route-context-node--route' : 'miner-route-context-node'}
            />
          )
        })}

        {completedPoints.length > 1 && (
          <polyline
            points={completedPoints.map((point) => `${point.x},${point.y}`).join(' ')}
            className="miner-route-line miner-route-line--completed"
          />
        )}
        <polyline
          points={remainingPoints.map((point) => `${point.x},${point.y}`).join(' ')}
          className="miner-route-line"
          markerEnd="url(#miner-route-arrow)"
        />

        {positions.map((point, index) => {
          const isCurrent = point.segmentId === currentSegment
          const isExit = point.segmentId === exitPoint.segmentId
          const isBlocked = point.segmentId === blockedSegment
          return (
            <g key={`${point.segmentId}-${index}`}>
              <circle
                cx={point.x}
                cy={point.y}
                r={isCurrent ? 9 : isExit ? 8 : isBlocked ? 8 : 4}
                className={[
                  'miner-route-node',
                  isCurrent ? 'miner-route-node--current' : '',
                  isExit ? 'miner-route-node--exit' : '',
                  isBlocked ? 'miner-route-node--blocked' : ''
                ].filter(Boolean).join(' ')}
              />
              {(isCurrent || isExit || isBlocked) && (
                <text x={point.x} y={point.y - 13} textAnchor="middle" className="miner-route-node-label">
                  {isCurrent ? 'Sen' : isExit ? 'Çıkış' : 'Kapalı'}
                </text>
              )}
            </g>
          )
        })}

        {currentPoint && (
          <text x={currentPoint.x} y={Math.min(currentPoint.y + 24, ROUTE_MAP_H - 8)} textAnchor="middle" className="miner-route-current-segment">
            {currentSegment}
          </text>
        )}
      </svg>

      <div className="miner-route-summary">
        <span><strong>Sen:</strong> {currentSegment}</span>
        <span><strong>Çıkış:</strong> {exitPoint.segmentId}</span>
        <span><strong>Kalan:</strong> {currentIndex >= 0 ? Math.max(route.length - currentIndex - 1, 0) : route.length - 1} segment</span>
      </div>
    </div>
  )
}

export default function MinerDashboard({
  workers,
  selectedWorkerId,
  onSelectWorker,
  segments,
  risks,
  gasSensors,
  emergencyRoute
}) {
  const selectedWorker = workers.find((w) => w.worker_id === selectedWorkerId) || workers[0]

  if (!selectedWorker) {
    return (
      <div className="miner-view">
        <p className="panel-empty">İşçi verisi bulunamadı.</p>
      </div>
    )
  }

  const segment = segments.find((s) => s.segment_id === selectedWorker.current_segment)
  const risk = risks.find((r) => r.segment_id === selectedWorker.current_segment)
  const nearbySensors = gasSensors.filter((s) => s.segment_id === selectedWorker.current_segment)
  const hasGasAlarm = nearbySensors.some((s) => s.status === 'alarm')
  const blockedSegments = segments.filter((s) => s.is_blocked).map((s) => s.segment_id)
  const routeBelongsToSelectedWorker = !emergencyRoute?.worker_id || emergencyRoute.worker_id === selectedWorker.worker_id
  const activeRoute = routeBelongsToSelectedWorker ? emergencyRoute : null
  const isAffectedWorker = Boolean(activeRoute?.affected_workers?.includes(selectedWorker.worker_id))
  const isTrapped = activeRoute?.trapped === true && isAffectedWorker
  const riskColor = getRiskColor(risk?.risk_level, segment?.is_blocked)

  const actionMessage = buildActionMessage({
    riskLevel: risk?.risk_level,
    isBlocked: segment?.is_blocked,
    emergencyRoute: activeRoute,
    isAffectedWorker
  })

  const alarmState = buildAlarmState({
    isBlocked: segment?.is_blocked,
    riskLevel: risk?.risk_level,
    isAffectedWorker,
    emergencyRoute: activeRoute,
    hasGasAlarm
  })

  const emergencyRouteSegments = activeRoute?.route_segments || activeRoute?.route
  const routeStart = emergencyRouteSegments?.[0]
  const routeExit = activeRoute?.exit_segment || emergencyRouteSegments?.[emergencyRouteSegments.length - 1]
  const currentRouteIndex = emergencyRouteSegments?.indexOf(selectedWorker.current_segment) ?? -1
  const remainingRouteCount = currentRouteIndex >= 0 && emergencyRouteSegments
    ? Math.max(emergencyRouteSegments.length - currentRouteIndex - 1, 0)
    : emergencyRouteSegments?.length ? emergencyRouteSegments.length - 1 : 0

  return (
    <div className="miner-view">
      <div className="miner-worker-select">
        <label htmlFor="miner-worker">Madenci</label>
        <select
          id="miner-worker"
          value={selectedWorker.worker_id}
          onChange={(e) => onSelectWorker(e.target.value)}
        >
          {workers.map((w) => (
            <option key={w.worker_id} value={w.worker_id}>{formatWorkerName(w.worker_id, w.name)}</option>
          ))}
        </select>
      </div>

      <div className={`miner-alarm-card miner-alarm-card--${alarmState.level}`}>
        <div className="miner-alarm-title">{alarmState.title}</div>
        <div className="miner-alarm-subtitle">{alarmState.subtitle}</div>
      </div>

      <div className="miner-card">
        <div className="miner-card-row">
          <span className="panel-label">Konum</span>
          <span className="miner-card-value">{selectedWorker.current_segment} — {segment?.name || 'Bilinmiyor'}</span>
        </div>

        <div className="miner-card-row">
          <span className="panel-label">Durum</span>
          <span
            className="risk-badge"
            style={{ backgroundColor: riskColor }}
          >
            {segment?.is_blocked ? 'Kapalı Bölge' : getRiskLabel(risk?.risk_level)}
          </span>
        </div>

        {hasGasAlarm && (
          <p className="panel-warning">Uyarı: Yakınındaki gaz sensöründe metan alarmı var.</p>
        )}

        {blockedSegments.length > 0 && (
          <div className="miner-card-row miner-card-row--block">
            <span className="panel-label">Kapalı Segmentler</span>
            <span className="text-danger">{blockedSegments.join(', ')}</span>
          </div>
        )}

        <div className="miner-card-row miner-card-row--block">
          <span className="panel-label">Çıkış Rotası</span>
          {activeRoute ? (
            <span className={activeRoute.trapped ? 'text-danger' : 'text-ok'}>
              {activeRoute.trapped
                ? 'Alternatif rota yok — mahsur kalındı.'
                : (emergencyRouteSegments?.length
                  ? `${selectedWorker.current_segment || routeStart} konumundan ${routeExit} çıkışına rota hazır.`
                  : 'Güvenli çıkış mevcut.')}
            </span>
          ) : (
            <span className="text-ok">Aktif acil durum yok, normal rota geçerli.</span>
          )}
        </div>

        {emergencyRouteSegments?.length > 0 && (
          <div className="miner-card-row miner-card-row--block">
            <span className="panel-label">Rota Özeti</span>
            <DynamicRouteMap
              route={emergencyRouteSegments}
              segments={segments}
              currentSegment={selectedWorker.current_segment}
              blockedSegment={activeRoute.blocked_segment}
              exitSegment={routeExit}
            />
            <div className="miner-route-text-summary">
              <span>Başlangıç: <strong>{routeStart}</strong></span>
              <span>Mevcut konum: <strong>{selectedWorker.current_segment}</strong></span>
              <span>Çıkış: <strong>{routeExit}</strong></span>
              <span>Kalan mesafe: <strong>{remainingRouteCount} segment</strong></span>
            </div>
            <details className="miner-route-details">
              <summary>Tüm segmentleri göster</summary>
              <RouteMiniMap
                route={emergencyRouteSegments}
                currentSegment={selectedWorker.current_segment}
                blockedSegment={activeRoute.blocked_segment}
              />
            </details>
          </div>
        )}

        <div className="miner-card-row miner-card-row--block miner-card-action">
          <span className="panel-label">Aksiyon</span>
          <span>{actionMessage}</span>
        </div>
      </div>
    </div>
  )
}
