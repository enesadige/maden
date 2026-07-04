import { useEffect, useMemo, useState } from 'react'
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
  isTimePlaying,
  onToggleTimePlayback,
  availableTimeSteps,
  selectedWorkerId,
  onSelectWorker,
  viewTab,
  onViewTabChange,
  apiModeActive
}) {
  const activeViewTab = viewTab || 'map'
  const [has3dOpened, setHas3dOpened] = useState(activeViewTab === '3d')
  const [sidePanelTab, setSidePanelTab] = useState('risk')

  useEffect(() => {
    if (activeViewTab === '3d') setHas3dOpened(true)
  }, [activeViewTab])

  function handleTabChange(tab) {
    onViewTabChange?.(tab)
    if (tab === '3d') setHas3dOpened(true)
  }
  const criticalCount = risks.filter((r) => r.risk_level === 'critical').length
  const highRiskCount = risks.filter((r) => r.risk_level === 'critical' || r.risk_level === 'high').length
  const gasAlarmCount = gasSensors.filter((sensor) => {
    const status = String(sensor.status || sensor.risk_level || '').toLowerCase()
    return status === 'alarm' || status === 'critical' || status === 'high'
  }).length
  const routeBadge = emergencyRoute?.trapped ? '!' : (emergencyRoute?.route_segments?.length || emergencyRoute?.route?.length ? 'OK' : null)

  const sideTabs = useMemo(() => ([
    {
      id: 'risk',
      label: 'Risk',
      helper: `${highRiskCount} yüksek`,
      badge: criticalCount > 0 ? criticalCount : null,
      tone: criticalCount > 0 ? 'danger' : (highRiskCount > 0 ? 'warning' : 'ok')
    },
    {
      id: 'workers',
      label: 'İşçi',
      helper: `${workers.length} kayıt`,
      badge: workers.length || null,
      tone: 'neutral'
    },
    {
      id: 'anomalies',
      label: 'UWB',
      helper: `${workerAnomalies.length} uyarı`,
      badge: workerAnomalies.length || null,
      tone: workerAnomalies.length > 0 ? 'warning' : 'ok'
    },
    {
      id: 'gas',
      label: 'Gaz',
      helper: `${gasSensors.length} sensör`,
      badge: gasAlarmCount > 0 ? gasAlarmCount : null,
      tone: gasAlarmCount > 0 ? 'danger' : 'ok'
    },
    {
      id: 'route',
      label: 'Rota',
      helper: emergencyRoute?.trapped ? 'mahsur' : (routeBadge ? 'hazır' : 'normal'),
      badge: routeBadge,
      tone: emergencyRoute?.trapped ? 'danger' : 'ok'
    }
  ]), [criticalCount, emergencyRoute, gasAlarmCount, gasSensors.length, highRiskCount, workerAnomalies.length, workers.length])

  const minStep = availableTimeSteps?.min !== undefined ? availableTimeSteps.min : 0
  const maxStep = availableTimeSteps?.max !== undefined ? availableTimeSteps.max : 30

  return (
    <>
      <div className="layout-main">
        <section className="layout-viewer">
          <div className="viewer-tabs">
            <button
              type="button"
              className={`viewer-tab${activeViewTab === 'map' ? ' viewer-tab--active' : ''}`}
              onClick={() => handleTabChange('map')}
            >
              Harita Görünümü
            </button>
            <button
              type="button"
              className={`viewer-tab${activeViewTab === '3d' ? ' viewer-tab--active' : ''}`}
              onClick={() => handleTabChange('3d')}
            >
              3B LiDAR Görünümü
            </button>
          </div>

          <div className="viewer-stage" style={{ position: 'relative', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: activeViewTab === 'map' ? 'block' : 'none', flex: 1, position: 'relative' }}>
              <MineMapView
                segments={segments}
                risks={risks}
                workers={workers}
                gasSensors={gasSensors}
                emergencyRoute={emergencyRoute}
                selectedSegmentId={selectedSegmentId}
                selectedWorkerId={selectedWorkerId}
                onSegmentSelect={onSegmentSelect}
              />
            </div>
            <div style={{ display: activeViewTab === '3d' ? 'block' : 'none', flex: 1, position: 'relative' }}>
              {has3dOpened && (
                <DigitalTwinViewer
                  segments={segments}
                  risks={risks}
                  workers={workers}
                  gasSensors={gasSensors}
                  emergencyRoute={emergencyRoute}
                  selectedSegmentId={selectedSegmentId}
                  selectedWorkerId={selectedWorkerId}
                  onSegmentSelect={onSegmentSelect}
                />
              )}
            </div>
          </div>
        </section>

        <aside className="layout-side">
          <div className="side-panel-tabs" role="tablist" aria-label="Yönetim paneli sekmeleri">
            {sideTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={sidePanelTab === tab.id}
                className={`side-panel-tab side-panel-tab--${tab.tone}${sidePanelTab === tab.id ? ' side-panel-tab--active' : ''}`}
                onClick={() => setSidePanelTab(tab.id)}
              >
                <span className="side-panel-tab-label">{tab.label}</span>
                <span className="side-panel-tab-helper">{tab.helper}</span>
                {tab.badge !== null && <span className="side-panel-tab-badge">{tab.badge}</span>}
              </button>
            ))}
          </div>

          <div className="side-panel-content">
            {sidePanelTab === 'risk' && (
              <RiskPanel
                segments={segments}
                risks={risks}
                workers={workers}
                gasSensors={gasSensors}
                environmentalRisk={environmentalRisk}
                geometryRisk={geometryRisk}
                selectedSegmentId={selectedSegmentId}
              />
            )}
            {sidePanelTab === 'workers' && <WorkerPanel workers={workers} anomalies={workerAnomalies} />}
            {sidePanelTab === 'anomalies' && (
              <WorkerAnomalyPanel
                anomalies={workerAnomalies}
                summary={workerAnomalySummary}
                selectedWorkerId={selectedWorkerId}
              />
            )}
            {sidePanelTab === 'gas' && <GasSensorPanel gasSensors={gasSensors} />}
            {sidePanelTab === 'route' && (
              <RouteOverlay
                emergencyRoute={emergencyRoute}
                workers={workers}
                selectedWorkerId={selectedWorkerId}
                onSelectWorker={onSelectWorker}
              />
            )}
          </div>
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
            <button
              type="button"
              className={`scenario-button${isTimePlaying ? ' scenario-button--active' : ''}`}
              onClick={onToggleTimePlayback}
              disabled={maxStep <= minStep}
              title={isTimePlaying ? 'Zaman akışını durdur' : 'Zaman akışını başlat'}
              aria-label={isTimePlaying ? 'Zaman akışını durdur' : 'Zaman akışını başlat'}
              style={{ padding: '4px 10px', fontSize: '11px', minWidth: '48px', margin: 0 }}
            >
              {isTimePlaying ? '⏸' : '▶'}
            </button>
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
                title="Bir zaman adımı geri"
              >
                ‹
              </button>
              <button
                type="button"
                className="scenario-button"
                onClick={() => onTimeStepChange(Math.min(maxStep, selectedTimeStep + 1))}
                disabled={selectedTimeStep >= maxStep}
                style={{ padding: '4px 10px', fontSize: '11px', minWidth: 'unset', margin: 0 }}
                title="Bir zaman adımı ileri"
              >
                ›
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
          apiModeActive={apiModeActive}
        />
        <p className="demo-note">
          Demo verisi: Gerçek LiDAR ve backend çıktıları geldiğinde bu katman API üzerinden beslenecektir.
        </p>
      </footer>
    </>
  )
}
