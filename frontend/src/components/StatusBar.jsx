import { isApiMode } from '../services/api'

export default function StatusBar({ activeScenarioLabel, segmentCount, workerCount, criticalCount, apiModeActive = isApiMode() }) {
  return (
    <div className="status-bar">
      <span className={`status-pill ${apiModeActive ? 'status-pill--api' : 'status-pill--mock'}`}>
        {apiModeActive ? 'API mode' : 'Mock mode'}
      </span>
      <span className="status-item">Senaryo: <strong>{activeScenarioLabel}</strong></span>
      <span className="status-item">Segment: <strong>{segmentCount}</strong></span>
      <span className="status-item">İşçi: <strong>{workerCount}</strong></span>
      <span className="status-item status-item--critical">Kritik Risk: <strong>{criticalCount}</strong></span>
    </div>
  )
}
