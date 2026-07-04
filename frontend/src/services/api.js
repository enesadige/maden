import { normalizeApiPayload } from '../utils/idNormalize'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '')
export const USE_API = API_BASE_URL.length > 0

async function fetchWithTimeout(url, options = {}, timeout = 4000) {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    })
    clearTimeout(id)
    return response
  } catch (err) {
    clearTimeout(id)
    throw err
  }
}

async function fetchJson(url, timeout = 4000) {
  const response = await fetchWithTimeout(url, {}, timeout)
  if (!response.ok) {
    throw new Error(`Request failed: ${url} (${response.status})`)
  }
  return response.json()
}

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`
}

function mockUrl(file) {
  return `/mock/${file}`
}

// In API mode, a failed backend call falls back to the matching mock file
// instead of crashing the dashboard.
async function fetchApiOrMock(path, mockFile, forceMock = false) {
  if (!USE_API || forceMock) {
    const data = await fetchJson(mockUrl(mockFile), 2000)
    return normalizeApiPayload(data)
  }

  try {
    const data = await fetchJson(apiUrl(path), 4000)
    return normalizeApiPayload(data)
  } catch (err) {
    console.warn(`API request failed for ${path}, falling back to mock data.`, err)
    const data = await fetchJson(mockUrl(mockFile), 2000)
    return normalizeApiPayload(data)
  }
}

export function isApiMode() {
  return USE_API
}

export async function getHealth() {
  if (!USE_API) return { status: 'ok', mode: 'mock' }
  try {
    return await fetchJson(apiUrl('/api/health'), 2000)
  } catch (err) {
    console.warn('API health check failed, reporting degraded status.', err)
    return { status: 'unreachable', mode: 'api' }
  }
}

export async function getSegments(params = {}) {
  return fetchApiOrMock('/api/digital-twin/segments', 'segments.json', params.forceMock)
}

export async function getSegmentMetadata() {
  return fetchJson(mockUrl('segment_metadata.json'))
}

export async function getGraph(params = {}) {
  return fetchApiOrMock('/api/digital-twin/graph', 'mine_graph.json', params.forceMock)
}

export async function getWorkers(params = {}) {
  const { timeStep, forceMock } = params
  const query = timeStep !== undefined && timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/workers${query}`, 'workers.json', forceMock)
}

export async function getRiskSegments(params = {}) {
  const { timeStep, forceMock } = params
  const query = timeStep !== undefined && timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/risk/segments${query}`, 'risk_segments.json', forceMock)
}

export async function getEnvironmentalRisk(params = {}) {
  const { timeStep, forceMock } = params
  const query = timeStep !== undefined && timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/risk/environmental${query}`, 'environmental_risk.json', forceMock)
}

export async function getGeometryRisk(params = {}) {
  return fetchApiOrMock('/api/risk/geometry', 'geometry_risk.json', params.forceMock)
}

export async function getScenarios() {
  return fetchJson(mockUrl('scenarios.json'))
}

export async function getEmergencyRoute(params = {}) {
  const { workerId, timeStep, scenarioId, blockedSegment, forceMock } = params
  const args = []
  if (workerId) args.push(`worker_id=${workerId}`)
  if (timeStep !== undefined) args.push(`time_step=${timeStep}`)
  if (scenarioId) args.push(`scenario=${scenarioId}`)
  if (blockedSegment) args.push(`blocked_segment=${blockedSegment}`)
  
  const query = args.length > 0 ? `?${args.join('&')}` : ''
  if (!USE_API || forceMock) {
    return getMockEmergencyRoute(params)
  }

  try {
    const data = await fetchJson(apiUrl(`/api/routes/emergency${query}`), 4000)
    return normalizeApiPayload(data)
  } catch (err) {
    console.warn('Emergency route API request failed.', err)
    throw err
  }
}

async function getMockEmergencyRoute(params = {}) {
  const { workerId, scenarioId, blockedSegment, timeStep } = params
  const [segments, workers] = await Promise.all([
    fetchJson(mockUrl('segments.json'), 2000),
    fetchJson(mockUrl('workers.json'), 2000)
  ])
  const selectedWorker = workers.find((worker) => worker.worker_id === workerId) || workers[0]
  const startSegment = selectedWorker?.current_segment || segments[0]?.segment_id
  const collapseScenario = scenarioId === 'collapse' || scenarioId === 'collapse_s004'
  const activeBlockedSegment = blockedSegment || (collapseScenario ? 'S004' : null)
  const segmentLookup = new Map(segments.map((segment) => [segment.segment_id, segment]))
  const exitSegment = segments.find((segment) => segment.is_exit)?.segment_id || 'S001'

  function findRoute() {
    if (!startSegment || !segmentLookup.has(startSegment)) return []
    if (activeBlockedSegment && startSegment === activeBlockedSegment) return []

    const queue = [[startSegment, [startSegment]]]
    const seen = new Set([startSegment])
    while (queue.length > 0) {
      const [current, path] = queue.shift()
      if (current === exitSegment) return path
      const currentSegment = segmentLookup.get(current)
      for (const next of currentSegment?.connected_segments || []) {
        if (seen.has(next)) continue
        if (activeBlockedSegment && next === activeBlockedSegment) continue
        if (!segmentLookup.has(next)) continue
        seen.add(next)
        queue.push([next, [...path, next]])
      }
    }
    return []
  }

  const routeSegments = findRoute()
  const reachable = routeSegments.length > 1
  const trapped = !reachable
  return normalizeApiPayload({
    scenario_id: scenarioId || 'show_route',
    event_type: collapseScenario ? 'collapse' : 'route_preview',
    worker_id: selectedWorker?.worker_id || workerId || null,
    affected_workers: selectedWorker?.worker_id ? [selectedWorker.worker_id] : [],
    start_segment: startSegment,
    blocked_segment: activeBlockedSegment,
    exit_segment: reachable ? routeSegments[routeSegments.length - 1] : exitSegment,
    reachable,
    exit_reachable: reachable,
    trapped,
    route: routeSegments,
    route_segments: routeSegments,
    alternative_route_available: reachable,
    route_edge_valid: reachable,
    invalid_route_edges: [],
    emergency_status: reachable ? 'ROUTE_AVAILABLE' : 'NO_ROUTE_TO_EXIT',
    message: reachable
      ? 'Mock route uses connected segment graph to reach the exit.'
      : 'Mock route could not find a connected exit path after blockage constraints.',
    time_step: timeStep ?? 0
  })
}

export async function getWorkerAnomalies(params = {}) {
  const { workerId, timeStep, eventType, severity, forceMock } = params
  if (!USE_API || forceMock) return []

  const args = []
  if (workerId) args.push(`worker_id=${encodeURIComponent(workerId)}`)
  if (timeStep !== undefined && timeStep !== '') args.push(`time_step=${encodeURIComponent(timeStep)}`)
  if (eventType) args.push(`event_type=${encodeURIComponent(eventType)}`)
  if (severity) args.push(`severity=${encodeURIComponent(severity)}`)
  const query = args.length > 0 ? `?${args.join('&')}` : ''

  try {
    const data = await fetchJson(apiUrl(`/api/workers/anomalies${query}`), 4000)
    return normalizeApiPayload(data)
  } catch (err) {
    console.warn('Worker anomaly API request failed.', err)
    return []
  }
}

export async function getWorkerAnomalySummary(params = {}) {
  if (!USE_API || params.forceMock) {
    return { source: 'uwb_behavior_anomaly', summary: { event_count: 0 }, warnings: [] }
  }

  try {
    const data = await fetchJson(apiUrl('/api/workers/anomalies/summary'), 4000)
    return normalizeApiPayload(data)
  } catch (err) {
    console.warn('Worker anomaly summary API request failed.', err)
    return { source: 'uwb_behavior_anomaly', summary: { event_count: 0 }, warnings: [] }
  }
}

export async function getGasSensors(params = {}) {
  const { timeStep, forceMock } = params
  const query = timeStep !== undefined && timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/gas-sensors${query}`, 'gas_sensors.json', forceMock)
}

export async function getSystemStatus() {
  return fetchJson(mockUrl('system_status.json'))
}

export async function getPointCloudMetadata(params = {}) {
  return fetchApiOrMock('/api/digital-twin/pointcloud', 'pointcloud_metadata.json', params.forceMock)
}

export async function getSimulationState(params = {}) {
  const { timeStep, forceMock } = params
  const query = timeStep !== undefined && timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/simulation/state${query}`, 'segments.json', forceMock)
}

export async function getSimulationScenario(params = {}) {
  const { scenarioId, timeStep, workerId, forceMock } = params
  const args = []
  if (scenarioId) args.push(`scenario_id=${encodeURIComponent(scenarioId)}`)
  if (timeStep !== undefined) args.push(`time_step=${encodeURIComponent(timeStep)}`)
  if (workerId) args.push(`worker_id=${encodeURIComponent(workerId)}`)
  const query = args.length > 0 ? `?${args.join('&')}` : ''
  return fetchApiOrMock(`/api/simulation/scenario${query}`, 'segments.json', forceMock)
}

export async function getTrappedState(params = {}) {
  const timeStep = params.timeStep !== undefined ? params.timeStep : ''
  const query = timeStep !== '' ? `?time_step=${timeStep}` : ''
  return fetchApiOrMock(`/api/simulation/trapped${query}`, 'system_status.json')
}

export async function getIntegrationStatus(params = {}) {
  const { timeStep, scenarioId, workerId } = params
  const args = []
  if (timeStep !== undefined) args.push(`time_step=${encodeURIComponent(timeStep)}`)
  if (scenarioId) args.push(`scenario_id=${encodeURIComponent(scenarioId)}`)
  if (workerId) args.push(`worker_id=${encodeURIComponent(workerId)}`)
  const query = args.length > 0 ? `?${args.join('&')}` : ''
  return fetchApiOrMock(`/api/integration/status${query}`, 'system_status.json')
}
