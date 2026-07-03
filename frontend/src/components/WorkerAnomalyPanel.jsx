function eventTypeLabel(type) {
  const labels = {
    stationary_too_long: 'Uzun süre hareketsiz',
    low_position_reliability: 'Konum güveni düşük',
    tracking_lost_in_risky_segment: 'Riskli segmentte takip kaybı',
    entered_high_risk_segment: 'Riskli segmente giriş',
    near_blocked_segment: 'Kapalı segmente yakın',
    route_deviation: 'Rota sapması'
  }
  return labels[type] || type || 'Bilinmeyen uyarı'
}

function severityLabel(severity) {
  const labels = {
    critical: 'Kritik',
    high: 'Yüksek',
    medium: 'Orta',
    low: 'Düşük'
  }
  return labels[severity] || severity || 'Bilinmiyor'
}

function severityClass(severity) {
  if (severity === 'critical' || severity === 'high') return 'text-danger'
  if (severity === 'medium') return 'panel-warning-text'
  return 'text-ok'
}

export default function WorkerAnomalyPanel({ anomalies = [], summary, selectedWorkerId }) {
  const events = Array.isArray(anomalies) ? anomalies : []
  const totalEventCount = summary?.summary?.event_count ?? events.length
  const criticalCount = events.filter((event) => event.severity === 'critical').length
  const visibleEvents = events.slice(0, 6)

  return (
    <div className="panel">
      <h2 className="panel-title">UWB Davranış Uyarıları</h2>

      <div className="panel-row">
        <span className="panel-label">Toplam Event</span>
        <span>{totalEventCount}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Bu Adımda</span>
        <span>{events.length}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Kritik</span>
        <span className={criticalCount > 0 ? 'text-danger' : 'text-ok'}>{criticalCount}</span>
      </div>

      {selectedWorkerId && (
        <div className="panel-row">
          <span className="panel-label">Seçili İşçi</span>
          <span>{selectedWorkerId}</span>
        </div>
      )}

      {visibleEvents.length === 0 ? (
        <p className="panel-empty">Seçili zaman/işçi için davranış uyarısı yok.</p>
      ) : (
        <div className="panel-row panel-row--block">
          <span className="panel-label">Son Uyarılar</span>
          <div className="anomaly-list">
            {visibleEvents.map((event) => (
              <div className="anomaly-card" key={event.event_id}>
                <div className="anomaly-card-header">
                  <strong>{eventTypeLabel(event.event_type)}</strong>
                  <span className={severityClass(event.severity)}>{severityLabel(event.severity)}</span>
                </div>
                <div className="anomaly-card-meta">
                  {event.worker_id} · {event.segment_id} · t={event.time_step}
                </div>
                <div className="anomaly-card-reason">{event.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="panel-hint">
        Bu uyarılar analitik sinyaldir; mahsur kalma kararı acil rota motorundan gelir.
      </p>
    </div>
  )
}
