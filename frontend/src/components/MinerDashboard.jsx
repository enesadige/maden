import { getRiskColor, getRiskLabel } from '../utils/riskColors'
import { formatWorkerName } from '../utils/idNormalize'

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
        return `Tahliye rotasını takip et: ${routeSegments.join(' → ')}`
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
  const isAffectedWorker = Boolean(emergencyRoute?.affected_workers?.includes(selectedWorker.worker_id))
  const isTrapped = emergencyRoute?.trapped === true && isAffectedWorker
  const riskColor = getRiskColor(risk?.risk_level, segment?.is_blocked)

  const actionMessage = buildActionMessage({
    riskLevel: risk?.risk_level,
    isBlocked: segment?.is_blocked,
    emergencyRoute,
    isAffectedWorker
  })

  const alarmState = buildAlarmState({
    isBlocked: segment?.is_blocked,
    riskLevel: risk?.risk_level,
    isAffectedWorker,
    emergencyRoute,
    hasGasAlarm
  })

  const emergencyRouteSegments = emergencyRoute?.route_segments || emergencyRoute?.route

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
          {emergencyRoute ? (
            <span className={emergencyRoute.trapped ? 'text-danger' : 'text-ok'}>
              {emergencyRoute.trapped
                ? 'Alternatif rota yok — mahsur kalındı.'
                : (emergencyRouteSegments?.length
                  ? emergencyRouteSegments.join(' → ')
                  : 'Güvenli çıkış mevcut.')}
            </span>
          ) : (
            <span className="text-ok">Aktif acil durum yok, normal rota geçerli.</span>
          )}
        </div>

        {emergencyRouteSegments?.length > 0 && (
          <div className="miner-card-row miner-card-row--block">
            <span className="panel-label">Rota Özeti</span>
            <RouteMiniMap
              route={emergencyRouteSegments}
              currentSegment={selectedWorker.current_segment}
              blockedSegment={emergencyRoute.blocked_segment}
            />
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
