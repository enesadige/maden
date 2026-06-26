import { isApiMode } from '../services/api'

export default function StatusBar({ activeScenarioLabel, segmentCount, workerCount, criticalCount }) {
  return (
    <div className="status-bar">
      <span className={`status-pill ${isApiMode() ? 'status-pill--api' : 'status-pill--mock'}`}>
        {isApiMode() ? 'API mode' : 'Mock mode'}
      </span>
      <span className="status-item">Senaryo: <strong>{activeScenarioLabel}</strong></span>
      <span className="status-item">Segment: <strong>{segmentCount}</strong></span>
      <span className="status-item">İşçi: <strong>{workerCount}</strong></span>
      <span className="status-item status-item--critical">Kritik Risk: <strong>{criticalCount}</strong></span>
    </div>
  )
}
