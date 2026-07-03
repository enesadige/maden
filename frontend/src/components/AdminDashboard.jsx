import { useState } from 'react'
import DigitalTwinViewer from './DigitalTwinViewer'
import MineMapView from './MineMapView'
import RiskPanel from './RiskPanel'
import WorkerPanel from './WorkerPanel'
import GasSensorPanel from './GasSensorPanel'
import WorkerAnomalyPanel from './WorkerAnomalyPanel'
import ScenarioControls from './ScenarioControls'
import RouteOverlay from './RouteOverlay'
import SegmentLegend from './SegmentLegend'
import StatusBar from './StatusBar'

export default function AdminDashboard({
  segments,
  risks,
  workers,
  gasSensors,
  environmentalRisk,
  geometryRisk,
  workerAnomalies,
  workerAnomalySummary,
  scenarios,
  emergencyRoute,
  selectedScenario,
  onScenarioChange,
  selectedSegmentId,
  onSegmentSelect,
  activeScenarioLabel,
  // Time Step & Worker Selection Props
  selectedTimeStep,
  onTimeStepChange,
  availableTimeSteps,
  selectedWorkerId,
  onSelectWorker
}) {
  const [viewTab, setViewTab] = useState('map')
  const [has3dOpened, setHas3dOpened] = useState(false)

  function handleTabChange(tab) {
    setViewTab(tab)
    if (tab === '3d') setHas3dOpened(true)
  }
  const criticalCount = risks.filter((r) => r.risk_level === 'critical').length

  const minStep = availableTimeSteps?.min !== undefined ? availableTimeSteps.min : 0
  const maxStep = availableTimeSteps?.max !== undefined ? availableTimeSteps.max : 30

  return (
    <>
      <div className="layout-main">
        <section className="layout-viewer">
          <div className="viewer-tabs">
            <button
              type="button"
              className={`viewer-tab${viewTab === 'map' ? ' viewer-tab--active' : ''}`}
              onClick={() => handleTabChange('map')}
            >
              Harita Görünümü
            </button>
            <button
              type="button"
              className={`viewer-tab${viewTab === '3d' ? ' viewer-tab--active' : ''}`}
              onClick={() => handleTabChange('3d')}
            >
              3B LiDAR Görünümü
            </button>
          </div>

          <div className="viewer-stage" style={{ position: 'relative', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: viewTab === 'map' ? 'block' : 'none', flex: 1, position: 'relative' }}>
              <MineMapView
                segments={segments}
                risks={risks}
                workers={workers}
                gasSensors={gasSensors}
                emergencyRoute={emergencyRoute}
                selectedSegmentId={selectedSegmentId}
                onSegmentSelect={onSegmentSelect}
              />
            </div>
            <div style={{ display: viewTab === '3d' ? 'block' : 'none', flex: 1, position: 'relative' }}>
              {has3dOpened && (
                <DigitalTwinViewer
                  segments={segments}
                  risks={risks}
                  workers={workers}
                  gasSensors={gasSensors}
                  emergencyRoute={emergencyRoute}
                  selectedSegmentId={selectedSegmentId}
                  onSegmentSelect={onSegmentSelect}
                />
              )}
            </div>
          </div>
        </section>

        <aside className="layout-side">
          <RiskPanel
            segments={segments}
            risks={risks}
            workers={workers}
            gasSensors={gasSensors}
            environmentalRisk={environmentalRisk}
            geometryRisk={geometryRisk}
            selectedSegmentId={selectedSegmentId}
          />
          <WorkerPanel workers={workers} anomalies={workerAnomalies} />
          <WorkerAnomalyPanel
            anomalies={workerAnomalies}
            summary={workerAnomalySummary}
            selectedWorkerId={selectedWorkerId}
          />
          <GasSensorPanel gasSensors={gasSensors} />
          <RouteOverlay
            emergencyRoute={emergencyRoute}
            workers={workers}
            selectedWorkerId={selectedWorkerId}
            onSelectWorker={onSelectWorker}
          />
        </aside>
      </div>

      <footer className="layout-bottom">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <ScenarioControls
            scenarios={scenarios}
            activeScenarioId={selectedScenario}
            onSelectScenario={onScenarioChange}
          />
          
          {/* Time Step Slider */}
          <div className="time-step-controls" style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '6px 12px', background: '#1e2530', borderRadius: '6px', border: '1px solid #2d3748', flex: 1, minWidth: '280px' }}>
            <span style={{ fontSize: '12px', fontWeight: '600', color: '#a0aec0', whiteSpace: 'nowrap' }}>
              Zaman Adımı: <strong>{selectedTimeStep}</strong>
            </span>
            <input
              type="range"
              min={minStep}
              max={maxStep}
              value={selectedTimeStep}
              onChange={(e) => onTimeStepChange(Number(e.target.value))}
              style={{ flex: 1, cursor: 'pointer', accentColor: '#34f5c5' }}
            />
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                type="button"
                className="scenario-button"
                onClick={() => onTimeStepChange(Math.max(minStep, selectedTimeStep - 1))}
                disabled={selectedTimeStep <= minStep}
                style={{ padding: '4px 10px', fontSize: '11px', minWidth: 'unset', margin: 0 }}
              >
                ◀
              </button>
              <button
                type="button"
                className="scenario-button"
                onClick={() => onTimeStepChange(Math.min(maxStep, selectedTimeStep + 1))}
                disabled={selectedTimeStep >= maxStep}
                style={{ padding: '4px 10px', fontSize: '11px', minWidth: 'unset', margin: 0 }}
              >
                ▶
              </button>
            </div>
          </div>
        </div>

        <SegmentLegend />
        <StatusBar
          activeScenarioLabel={activeScenarioLabel}
          segmentCount={segments.length}
          workerCount={workers.length}
          criticalCount={criticalCount}
        />
        <p className="demo-note">
          Demo verisi: Gerçek LiDAR ve backend çıktıları geldiğinde bu katman API üzerinden beslenecektir.
        </p>
      </footer>
    </>
  )
}
