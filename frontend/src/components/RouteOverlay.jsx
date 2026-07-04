import { formatWorkerName } from '../utils/idNormalize'

export default function RouteOverlay({
  emergencyRoute,
  workers,
  selectedWorkerId,
  onSelectWorker
}) {
  if (!emergencyRoute) {
    return (
      <div className="panel">
        <h2 className="panel-title">Acil Rota</h2>
        {workers && workers.length > 0 && selectedWorkerId && onSelectWorker && (
          <div className="miner-worker-select" style={{ marginBottom: '12px' }}>
            <label htmlFor="admin-worker-select" style={{ fontSize: '11px', fontWeight: '600', color: '#a0aec0', display: 'block', marginBottom: '4px' }}>
              İşçi Seçimi
            </label>
            <select
              id="admin-worker-select"
              value={selectedWorkerId}
              onChange={(e) => onSelectWorker(e.target.value)}
              style={{ width: '100%', padding: '6px', background: '#2d3748', border: '1px solid #4a5568', borderRadius: '4px', color: '#fff', fontSize: '12px', cursor: 'pointer' }}
            >
              {workers.map((w) => (
                <option key={w.worker_id} value={w.worker_id}>
                  {formatWorkerName(w.worker_id, w.name)}
                </option>
              ))}
            </select>
          </div>
        )}
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

  const isTrapped = emergencyRoute?.trapped === true
  const isNormalRoute = !isTrapped && exit_reachable !== false

  return (
    <div className="panel panel--emergency">
      <h2 className="panel-title">Acil Rota</h2>

      {workers && workers.length > 0 && selectedWorkerId && onSelectWorker && (
        <div className="miner-worker-select" style={{ marginBottom: '12px' }}>
          <label htmlFor="admin-worker-select" style={{ fontSize: '11px', fontWeight: '600', color: '#a0aec0', display: 'block', marginBottom: '4px' }}>
            Rota Gösterilen İşçi
          </label>
          <select
            id="admin-worker-select"
            value={selectedWorkerId}
            onChange={(e) => onSelectWorker(e.target.value)}
            style={{ width: '100%', padding: '6px', background: '#2d3748', border: '1px solid #4a5568', borderRadius: '4px', color: '#fff', fontSize: '12px', cursor: 'pointer' }}
          >
            {workers.map((w) => (
              <option key={w.worker_id} value={w.worker_id}>
                {formatWorkerName(w.worker_id, w.name)}
              </option>
            ))}
          </select>
        </div>
      )}

      {isTrapped ? (
        <div className="route-alert-banner route-alert-banner--danger">
          Alternatif rota yok — işçi mahsur kalabilir.
        </div>
      ) : isNormalRoute ? (
        <div className="route-alert-banner route-alert-banner--ok" style={{ background: '#1c2d24', border: '1px solid #2f855a', color: '#48bb78' }}>
          Aktif acil durum yok. Standart rota geçerli.
        </div>
      ) : (
        <div className="route-alert-banner route-alert-banner--ok">
          Güvenli acil çıkış rotası mevcut.
        </div>
      )}

      {!isNormalRoute && (
        <div className="panel-row">
          <span className="panel-label">Kapalı Segment</span>
          <span>{blocked_segment || '—'}</span>
        </div>
      )}

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

      {emergencyRoute.route_edge_valid !== undefined && (
        <div className="panel-row">
          <span className="panel-label">Graph Doğrulaması</span>
          <span className={emergencyRoute.route_edge_valid ? 'text-ok' : 'text-danger'}>
            {emergencyRoute.route_edge_valid ? 'Geçerli' : 'Geçersiz'}
          </span>
        </div>
      )}

      {emergencyRoute.invalid_route_edges?.length > 0 && (
        <div className="panel-row panel-row--block">
          <span className="panel-label">Geçersiz Bağlantılar</span>
          <span>{emergencyRoute.invalid_route_edges.map((edge) => `${edge.source} → ${edge.target}`).join(', ')}</span>
        </div>
      )}

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
