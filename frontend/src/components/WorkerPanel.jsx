import { formatWorkerName } from '../utils/idNormalize'

function statusLabel(status) {
  if (status === 'at_risk') return 'Riskte'
  if (status === 'trapped') return 'Mahsur'
  if (status === 'tracking_lost') return 'Sinyal Yok'
  return 'Güvende'
}

function isAtRisk(status) {
  return status === 'at_risk' || status === 'trapped'
}

export default function WorkerPanel({ workers }) {
  if (!workers || workers.length === 0) {
    return (
      <div className="panel">
        <h2 className="panel-title">İşçi Paneli</h2>
        <p className="panel-empty">İşçi verisi bulunamadı.</p>
      </div>
    )
  }

  return (
    <div className="panel">
      <h2 className="panel-title">İşçi Paneli</h2>
      {workers.map((worker) => (
        <div className={`worker-card ${isAtRisk(worker.status) ? 'worker-card--risk' : ''}`} key={worker.worker_id}>
          <div className="worker-card-header">
            <strong>{formatWorkerName(worker.worker_id, worker.name)}</strong>
            <span className={`worker-status worker-status--${isAtRisk(worker.status) ? 'at_risk' : worker.status}`}>{statusLabel(worker.status)}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Segment</span>
            <span>{worker.current_segment}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Hareket</span>
            <span>{worker.motion_status === 'moving' ? 'Hareketli' : 'Sabit'}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Konum Güvenilirliği</span>
            <span>{Math.round(worker.position_reliability * 100)}%</span>
          </div>
          {worker.last_seen && (
            <div className="panel-row">
              <span className="panel-label">Son Görülme</span>
              <span>{worker.last_seen}</span>
            </div>
          )}
          {worker.position_reliability < 0.5 && (
            <p className="panel-warning">Konum güvenilirliği düşük, veri doğrulanmalı.</p>
          )}
        </div>
      ))}
    </div>
  )
}
