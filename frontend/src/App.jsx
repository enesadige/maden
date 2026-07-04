import { useEffect, useMemo, useRef, useState } from 'react'
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
  getGasSensors,
  getSimulationScenario,
  getSimulationState,
  getWorkerAnomalies,
  getWorkerAnomalySummary,
  isApiMode
} from './services/api'
import { applyScenario, getFocusSegmentId } from './utils/scenarioUtils'

const SCENARIO_CONFIG = {
  normal:        { timeStep: 0 },
  methane_spike: { timeStep: 21 },
  collapse_s004: { timeStep: 27 },
  worker_at_risk:{ timeStep: 23 },
  show_route:    { timeStep: 27 }
}

const ROUTE_SCENARIOS = new Set(['collapse', 'collapse_s004', 'show_route'])

export default function App() {
  const [baseData, setBaseData] = useState(null)
  const [environmentalRisk, setEnvironmentalRisk] = useState([])
  const [geometryRisk, setGeometryRisk] = useState([])
  const [workerAnomalies, setWorkerAnomalies] = useState([])
  const [workerAnomalySummary, setWorkerAnomalySummary] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [emergencyRouteData, setEmergencyRouteData] = useState(null)
  const [minerRouteData, setMinerRouteData] = useState(null)
  const [selectedScenario, setSelectedScenario] = useState('normal')
  const [selectedSegmentId, setSelectedSegmentId] = useState(null)
  const [viewMode, setViewMode] = useState('admin')
  const [adminViewTab, setAdminViewTab] = useState('map')
  const [selectedWorkerId, setSelectedWorkerId] = useState(null)
  const [scenarioTargetWorkerId, setScenarioTargetWorkerId] = useState(null)
  const [selectedTimeStep, setSelectedTimeStep] = useState(0)
  const [committedTimeStep, setCommittedTimeStep] = useState(0)
  const [isTimePlaying, setIsTimePlaying] = useState(false)
  const timeStepDebounceRef = useRef(null)
  const timeStepPlaybackRef = useRef(null)
  const isStateLoadingRef = useRef(false)
  const stateLoadIdRef = useRef(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [forceMockMode, setForceMockMode] = useState(false)

  const apiModeActive = isApiMode() && !forceMockMode

  // 1. Fetch simulation scenario state when scenario or timeStep changes
  useEffect(() => {
    let isMounted = true

    async function loadState() {
      const loadId = stateLoadIdRef.current + 1
      stateLoadIdRef.current = loadId
      isStateLoadingRef.current = true
      try {
        setLoading(true)
        setError(null)
        
        let scenarioState = null
        let scenarioList = []
        let envRisk = []
        let geoRisk = []
        let anomalyEvents = []
        let anomalySummary = null
        let useMock = !apiModeActive
        const requestTimeStep = committedTimeStep
        const scenarioWorkerId = selectedScenario === 'worker_at_risk'
          ? (scenarioTargetWorkerId || selectedWorkerId)
          : selectedWorkerId

        if (apiModeActive) {
          try {
            const [statePayload, list, env, geo, anomalies, anomalySummaryPayload] = await Promise.all([
              getSimulationScenario({ scenarioId: selectedScenario, timeStep: requestTimeStep, workerId: scenarioWorkerId }),
              getScenarios(),
              getEnvironmentalRisk({ timeStep: requestTimeStep }),
              getGeometryRisk(),
              getWorkerAnomalies({ timeStep: requestTimeStep, workerId: selectedWorkerId }),
              getWorkerAnomalySummary()
            ])

            if (!statePayload || !statePayload.segments || !statePayload.workers) {
              throw new Error("Backend response schema is missing segments or workers arrays.")
            }

            scenarioState = statePayload
            scenarioList = list
            envRisk = env
            geoRisk = geo
            anomalyEvents = anomalies
            anomalySummary = anomalySummaryPayload
          } catch (apiErr) {
            console.warn("Backend API request failed. Switching to local Mock Mode for this session.", apiErr)
            useMock = true
            if (!forceMockMode) setForceMockMode(true)
          }
        }

        if (useMock) {
          const [segments, risks, workers, gasSensors, list, env, geo] = await Promise.all([
            getSegments({ forceMock: true }),
            getRiskSegments({ forceMock: true }),
            getWorkers({ forceMock: true }),
            getGasSensors({ forceMock: true }),
            getScenarios(),
            getEnvironmentalRisk({ forceMock: true }),
            getGeometryRisk({ forceMock: true })
          ])

          scenarioState = {
            segments,
            risks,
            workers,
            gas_sensors: gasSensors,
            trapped: { summary: { trapped_count: 0, safe_count: workers.length }, workers: [] },
            available_time_steps: { min: 0, max: 30 }
          }
          scenarioList = list
          envRisk = env
          geoRisk = geo
          anomalyEvents = []
          anomalySummary = { source: 'uwb_behavior_anomaly', summary: { event_count: 0 }, warnings: [] }
        }

        if (!isMounted) return

        setScenarios(scenarioList)
        setEnvironmentalRisk(envRisk)
        setGeometryRisk(geoRisk)
        setWorkerAnomalies(anomalyEvents)
        setWorkerAnomalySummary(anomalySummary)

        const mappedData = {
          segments: scenarioState.segments || [],
          risks: scenarioState.risks || [],
          workers: scenarioState.workers || [],
          gasSensors: scenarioState.gas_sensors || scenarioState.gasSensors || [],
          trapped: scenarioState.trapped || { summary: { trapped_count: 0, safe_count: 0 }, workers: [] },
          scenario: scenarioState.scenario || null,
          availableTimeSteps: scenarioState.available_time_steps || { min: 0, max: 30 }
        }
        setBaseData(mappedData)

        // Auto-select first worker if none or invalid
        const workerList = scenarioState.workers || []
        if (workerList.length > 0) {
          const exists = workerList.some(w => w.worker_id === selectedWorkerId)
          if (!exists) {
            setSelectedWorkerId(workerList[0].worker_id)
          }
        }
      } catch (err) {
        console.error("Dashboard critical load error:", err)
        if (isMounted) setError(err.message)
      } finally {
        if (loadId === stateLoadIdRef.current) {
          isStateLoadingRef.current = false
        }
        if (isMounted) setLoading(false)
      }
    }

    loadState()
    return () => { isMounted = false }
  }, [selectedScenario, committedTimeStep, selectedWorkerId, scenarioTargetWorkerId, apiModeActive])

  // 3. Keep a worker-specific exit route for the miner view even when admin map route overlay is hidden.
  useEffect(() => {
    let isMounted = true

    async function loadMinerRoute() {
      if (!selectedWorkerId) {
        if (isMounted) setMinerRouteData(null)
        return
      }

      try {
        if (isMounted) setMinerRouteData(null)
        const routeParams = {
          workerId: selectedWorkerId,
          timeStep: committedTimeStep,
          scenarioId: ROUTE_SCENARIOS.has(selectedScenario) ? selectedScenario : undefined,
          forceMock: !apiModeActive
        }
        const route = await getEmergencyRoute(routeParams)
        if (isMounted) setMinerRouteData(route)
      } catch (err) {
        console.warn('Failed to load miner route', err)
        if (isMounted) setMinerRouteData(null)
      }
    }

    loadMinerRoute()
    return () => { isMounted = false }
  }, [selectedScenario, committedTimeStep, selectedWorkerId, apiModeActive])

  // 2. Fetch emergency route when scenario, timeStep, or selectedWorkerId changes
  useEffect(() => {
    let isMounted = true

    async function loadRoute() {
      if (!ROUTE_SCENARIOS.has(selectedScenario)) {
        if (isMounted) setEmergencyRouteData(null)
        return
      }
      if (!selectedWorkerId) return
      try {
        if (apiModeActive) {
          const route = await getEmergencyRoute({
            workerId: selectedWorkerId,
            timeStep: committedTimeStep,
            scenarioId: selectedScenario
          })
          if (isMounted) {
            setEmergencyRouteData(route)
          }
        } else {
          // In mock mode, fetch fallback or let scenarioUtils calculate it
          const route = await getEmergencyRoute({ scenarioId: selectedScenario })
          if (isMounted) {
            setEmergencyRouteData(route)
          }
        }
      } catch (err) {
        console.warn('Failed to load emergency route', err)
        if (isMounted) setEmergencyRouteData(null)
      }
    }

    loadRoute()
    return () => { isMounted = false }
  }, [selectedScenario, committedTimeStep, selectedWorkerId, apiModeActive])

  useEffect(() => {
    if (!isTimePlaying) {
      clearInterval(timeStepPlaybackRef.current)
      timeStepPlaybackRef.current = null
      return
    }

    const minStep = baseData?.availableTimeSteps?.min ?? 0
    const maxStep = baseData?.availableTimeSteps?.max ?? 30
    if (maxStep <= minStep) {
      setIsTimePlaying(false)
      return
    }

    clearTimeout(timeStepDebounceRef.current)
    timeStepPlaybackRef.current = setInterval(() => {
      if (isStateLoadingRef.current) return
      setSelectedTimeStep((current) => {
        const next = current >= maxStep ? minStep : current + 1
        isStateLoadingRef.current = true
        setCommittedTimeStep(next)
        return next
      })
    }, 900)

    return () => {
      clearInterval(timeStepPlaybackRef.current)
      timeStepPlaybackRef.current = null
    }
  }, [isTimePlaying, baseData?.availableTimeSteps?.min, baseData?.availableTimeSteps?.max])

  const derived = useMemo(() => {
    if (!baseData) return null
    if (apiModeActive) {
      return {
        ...baseData,
        emergencyRoute: emergencyRouteData
      }
    }
    return applyScenario(selectedScenario, baseData, emergencyRouteData)
  }, [baseData, selectedScenario, emergencyRouteData, apiModeActive])

  // Jump the Risk Panel to the segment that matters for the active scenario.
  // Depends on emergencyRouteData too so collapse focus updates when route loads.
  useEffect(() => {
    if (!derived) return
    const focusSegmentId = getFocusSegmentId(selectedScenario, derived)
    if (focusSegmentId) setSelectedSegmentId(focusSegmentId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScenario, baseData, emergencyRouteData])

  function handleTimeStepChange(value) {
    setIsTimePlaying(false)
    clearInterval(timeStepPlaybackRef.current)
    timeStepPlaybackRef.current = null
    setSelectedTimeStep(value)
    clearTimeout(timeStepDebounceRef.current)
    setCommittedTimeStep(value)
  }

  function handleToggleTimePlayback() {
    clearTimeout(timeStepDebounceRef.current)
    setIsTimePlaying((playing) => {
      if (playing) {
        clearInterval(timeStepPlaybackRef.current)
        timeStepPlaybackRef.current = null
      }
      return !playing
    })
  }

  function handleScenarioChange(scenarioId) {
    setIsTimePlaying(false)
    setSelectedScenario(scenarioId)
    setEmergencyRouteData(null)
    if (scenarioId === 'worker_at_risk') {
      setScenarioTargetWorkerId(selectedWorkerId || baseData?.workers?.[0]?.worker_id || null)
    } else {
      setScenarioTargetWorkerId(null)
    }
    const cfg = SCENARIO_CONFIG[scenarioId]
    if (cfg?.timeStep !== undefined) {
      const ts = cfg.timeStep
      setSelectedTimeStep(ts)
      setCommittedTimeStep(ts)
      clearTimeout(timeStepDebounceRef.current)
    }
  }

  const activeScenarioLabel = scenarios.find((s) => s.scenario_id === selectedScenario)?.label || selectedScenario

  if (loading && !baseData) {
    return (
      <div className="full-page-message" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0b0d14', color: '#fff', height: '100vh', fontFamily: 'sans-serif' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', border: '4px solid #1a1e29', borderTopColor: '#34f5c5', borderRadius: '50%', animation: 'spin 1s linear infinite', marginBottom: '16px' }}></div>
        <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
        <div style={{ fontSize: '18px', fontWeight: 'bold' }}>MadenGuard AI Yükleniyor...</div>
        <div style={{ fontSize: '12px', color: '#a0aec0', marginTop: '8px' }}>API bağlantısı kuruluyor ve dijital ikiz simülasyonu yükleniyor.</div>
      </div>
    )
  }

  if (error || !derived) {
    return (
      <div className="full-page-message full-page-message--error" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0b0d14', color: '#fff', height: '100vh', fontFamily: 'sans-serif', padding: '24px' }}>
        <div style={{ maxWidth: '500px', background: '#1a1315', border: '1px solid #e53e3e', padding: '24px', borderRadius: '8px', textAlign: 'center', boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }}>
          <h2 style={{ color: '#e53e3e', marginTop: 0 }}>MadenGuard AI — Yükleme Hatası</h2>
          <p style={{ fontSize: '14px', lineHeight: '1.6' }}>Veriler yüklenirken veya backend API'sine bağlanırken bir sorun oluştu: <br/><strong>{error || 'Bilinmeyen Hata'}</strong></p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginTop: '20px' }}>
            <button 
              onClick={() => window.location.reload()} 
              style={{ padding: '8px 16px', background: '#e53e3e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', fontSize: '13px' }}
            >
              Yeniden Dene
            </button>
            <button 
              onClick={() => setForceMockMode(true)} 
              style={{ padding: '8px 16px', background: '#2d3748', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', fontSize: '13px' }}
            >
              Mock Mode ile Başlat
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <Layout
      viewMode={viewMode}
      onChangeViewMode={setViewMode}
      activeScenarioLabel={activeScenarioLabel}
      apiModeActive={apiModeActive}
    >
      {viewMode === 'admin' ? (
        <AdminDashboard
          segments={derived.segments}
          risks={derived.risks}
          workers={derived.workers}
          gasSensors={derived.gasSensors}
          environmentalRisk={environmentalRisk}
          geometryRisk={geometryRisk}
          workerAnomalies={workerAnomalies}
          workerAnomalySummary={workerAnomalySummary}
          scenarios={scenarios}
          emergencyRoute={derived.emergencyRoute}
          selectedScenario={selectedScenario}
          onScenarioChange={handleScenarioChange}
          selectedSegmentId={selectedSegmentId}
          onSegmentSelect={setSelectedSegmentId}
          activeScenarioLabel={activeScenarioLabel}
          selectedTimeStep={selectedTimeStep}
          onTimeStepChange={handleTimeStepChange}
          isTimePlaying={isTimePlaying}
          onToggleTimePlayback={handleToggleTimePlayback}
          availableTimeSteps={baseData?.availableTimeSteps}
          selectedWorkerId={selectedWorkerId}
          onSelectWorker={setSelectedWorkerId}
          viewTab={adminViewTab}
          onViewTabChange={setAdminViewTab}
          apiModeActive={apiModeActive}
        />
      ) : (
        <MinerDashboard
          workers={derived.workers}
          selectedWorkerId={selectedWorkerId}
          onSelectWorker={setSelectedWorkerId}
          segments={derived.segments}
          risks={derived.risks}
          gasSensors={derived.gasSensors}
          emergencyRoute={minerRouteData || derived.emergencyRoute}
          selectedScenario={selectedScenario}
          activeScenarioLabel={activeScenarioLabel}
          scenario={baseData?.scenario}
        />
      )}
    </Layout>
  )
}
