import { useState } from 'react'
import DigitalTwinViewer from './DigitalTwinViewer'
import MineMapView from './MineMapView'
import RiskPanel from './RiskPanel'
import WorkerPanel from './WorkerPanel'
import GasSensorPanel from './GasSensorPanel'
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
  scenarios,
  emergencyRoute,
  selectedScenario,
  onScenarioChange,
  selectedSegmentId,
  onSegmentSelect,
  activeScenarioLabel
}) {
  const [viewTab, setViewTab] = useState('map')
  const criticalCount = risks.filter((r) => r.risk_level === 'critical').length

  return (
    <>
      <div className="layout-main">
        <section className="layout-viewer">
          <div className="viewer-tabs">
            <button
              type="button"
              className={`viewer-tab${viewTab === 'map' ? ' viewer-tab--active' : ''}`}
              onClick={() => setViewTab('map')}
            >
              Harita Görünümü
            </button>
            <button
              type="button"
              className={`viewer-tab${viewTab === '3d' ? ' viewer-tab--active' : ''}`}
              onClick={() => setViewTab('3d')}
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
              <DigitalTwinViewer
                segments={segments}
                risks={risks}
                workers={workers}
                gasSensors={gasSensors}
                emergencyRoute={emergencyRoute}
                selectedSegmentId={selectedSegmentId}
                onSegmentSelect={onSegmentSelect}
              />

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
          <WorkerPanel workers={workers} />
          <GasSensorPanel gasSensors={gasSensors} />
          <RouteOverlay emergencyRoute={emergencyRoute} />
        </aside>
      </div>

      <footer className="layout-bottom">
        <ScenarioControls
          scenarios={scenarios}
          activeScenarioId={selectedScenario}
          onSelectScenario={onScenarioChange}
        />
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
