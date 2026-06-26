export default function RouteOverlay({ emergencyRoute }) {
  if (!emergencyRoute) {
    return (
      <div className="panel">
        <h2 className="panel-title">Acil Rota</h2>
        <p className="panel-empty">Aktif bir acil durum senaryosu yok.</p>
      </div>
    )
  }

  const {
    blocked_segment,
    affected_workers,
    exit_segment,
    exit_reachable,
    route,
    route_segments,
    alternative_route_available,
    emergency_status,
    message
  } = emergencyRoute

  const routeSegments = route_segments || route
  const isTrapped = !exit_reachable || !alternative_route_available

  return (
    <div className="panel panel--emergency">
      <h2 className="panel-title">Acil Rota</h2>

      {isTrapped ? (
        <div className="route-alert-banner route-alert-banner--danger">
          Alternatif rota yok — işçi mahsur kalabilir.
        </div>
      ) : (
        <div className="route-alert-banner route-alert-banner--ok">
          Güvenli çıkış rotası mevcut.
        </div>
      )}

      <div className="panel-row">
        <span className="panel-label">Kapalı Segment</span>
        <span>{blocked_segment}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Etkilenen İşçi</span>
        <span>{affected_workers?.join(', ') || 'Yok'}</span>
      </div>

      {exit_segment && (
        <div className="panel-row">
          <span className="panel-label">Çıkış Segmenti</span>
          <span>{exit_segment}</span>
        </div>
      )}

      <div className="panel-row">
        <span className="panel-label">Çıkışa Erişim</span>
        <span className={exit_reachable ? 'text-ok' : 'text-danger'}>
          {exit_reachable ? 'Evet' : 'Hayır'}
        </span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Alternatif Rota</span>
        <span>{alternative_route_available ? 'Var' : 'Yok'}</span>
      </div>

      <div className="panel-row panel-row--block">
        <span className="panel-label">Rota Segmentleri</span>
        <span>{routeSegments?.join(' → ') || '-'}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Durum</span>
        <span className="text-danger">{emergency_status}</span>
      </div>

      <p className="panel-warning">{message}</p>
    </div>
  )
}
