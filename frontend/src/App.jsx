import { useEffect, useMemo, useState } from 'react'
import Layout from './components/Layout'
import AdminDashboard from './components/AdminDashboard'
import MinerDashboard from './components/MinerDashboard'
import {
  getSegments,
  getRiskSegments,
  getWorkers,
  getScenarios,
  getEmergencyRoute,
  getEnvironmentalRisk,
  getGeometryRisk,
  getGasSensors
} from './services/api'
import { applyScenario, getFocusSegmentId } from './utils/scenarioUtils'

export default function App() {
  const [baseData, setBaseData] = useState(null)
  const [environmentalRisk, setEnvironmentalRisk] = useState([])
  const [geometryRisk, setGeometryRisk] = useState([])
  const [scenarios, setScenarios] = useState([])
  const [emergencyRouteData, setEmergencyRouteData] = useState(null)
  const [activeScenarioId, setActiveScenarioId] = useState('normal')
  const [selectedSegmentId, setSelectedSegmentId] = useState(null)
  const [viewMode, setViewMode] = useState('admin')
  const [selectedWorkerId, setSelectedWorkerId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let isMounted = true

    async function loadData() {
      try {
        const [segments, risks, workers, gasSensors, scenarioList, envRisk, geoRisk, emergencyRoute] = await Promise.all([
          getSegments(),
          getRiskSegments(),
          getWorkers(),
          getGasSensors(),
          getScenarios(),
          getEnvironmentalRisk(),
          getGeometryRisk(),
          getEmergencyRoute('collapse_s004')
        ])

        if (!isMounted) return

        setBaseData({ segments, risks, workers, gasSensors })
        setEnvironmentalRisk(envRisk)
        setGeometryRisk(geoRisk)
        setScenarios(scenarioList)
        setEmergencyRouteData(emergencyRoute)
        setSelectedWorkerId(workers[0]?.worker_id || null)
      } catch (err) {
        if (isMounted) setError(err.message)
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    loadData()
    return () => { isMounted = false }
  }, [])

  const derived = useMemo(() => {
    if (!baseData) return null
    return applyScenario(activeScenarioId, baseData, emergencyRouteData)
  }, [baseData, activeScenarioId, emergencyRouteData])

  // Jump the Risk Panel to the segment that matters for the active scenario,
  // so it never lingers on a stale segment (e.g. S01 during a methane alarm).
  useEffect(() => {
    if (!derived) return
    const focusSegmentId = getFocusSegmentId(activeScenarioId, derived)
    if (focusSegmentId) setSelectedSegmentId(focusSegmentId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeScenarioId, baseData])

  const activeScenarioLabel = scenarios.find((s) => s.scenario_id === activeScenarioId)?.label || activeScenarioId

  if (loading) {
    return <div className="full-page-message">MadenGuard AI yükleniyor...</div>
  }

  if (error || !derived) {
    return (
      <div className="full-page-message full-page-message--error">
        Veri yüklenemedi: {error || 'Bilinmeyen hata'}
      </div>
    )
  }

  return (
    <Layout
      viewMode={viewMode}
      onChangeViewMode={setViewMode}
      activeScenarioLabel={activeScenarioLabel}
    >
      {viewMode === 'admin' ? (
        <AdminDashboard
          segments={derived.segments}
          risks={derived.risks}
          workers={derived.workers}
          gasSensors={derived.gasSensors}
          environmentalRisk={environmentalRisk}
          geometryRisk={geometryRisk}
          scenarios={scenarios}
          emergencyRoute={derived.emergencyRoute}
          selectedScenario={activeScenarioId}
          onScenarioChange={setActiveScenarioId}
          selectedSegmentId={selectedSegmentId}
          onSegmentSelect={setSelectedSegmentId}
          activeScenarioLabel={activeScenarioLabel}
        />
      ) : (
        <MinerDashboard
          workers={derived.workers}
          selectedWorkerId={selectedWorkerId}
          onSelectWorker={setSelectedWorkerId}
          segments={derived.segments}
          risks={derived.risks}
          gasSensors={derived.gasSensors}
          emergencyRoute={derived.emergencyRoute}
        />
      )}
    </Layout>
  )
}
