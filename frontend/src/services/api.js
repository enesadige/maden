import { normalizeApiPayload } from '../utils/idNormalize'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const USE_API = API_BASE_URL.length > 0

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${url} (${response.status})`)
  }
  return response.json()
}

function apiUrl(path) {
  return `${API_BASE_URL}${path}`
}

function mockUrl(file) {
  return `/mock/${file}`
}

// In API mode, a failed backend call falls back to the matching mock file
// instead of crashing the dashboard.
// API mode'da gerçek backend yanıtı eski prototip ID formatında gelirse
// (S04, W01, SEG_047 gibi) normalizeApiPayload onu Haki'nin S001/W001
// standardına çevirir. Mock dosyalar zaten yeni formatta, dokunulmaz.
async function fetchApiOrMock(path, mockFile) {
  if (!USE_API) return fetchJson(mockUrl(mockFile))

  try {
    const data = await fetchJson(apiUrl(path))
    return normalizeApiPayload(data)
  } catch (err) {
    console.warn(`API request failed for ${path}, falling back to mock data.`, err)
    return fetchJson(mockUrl(mockFile))
  }
}

export function isApiMode() {
  return USE_API
}

export async function getHealth() {
  if (!USE_API) return { status: 'ok', mode: 'mock' }
  try {
    return await fetchJson(apiUrl('/api/health'))
  } catch (err) {
    console.warn('API health check failed, reporting degraded status.', err)
    return { status: 'unreachable', mode: 'api' }
  }
}

export async function getSegments() {
  return fetchApiOrMock('/api/digital-twin/segments', 'segments.json')
}

export async function getSegmentMetadata() {
  return fetchJson(mockUrl('segment_metadata.json'))
}

export async function getGraph() {
  return fetchApiOrMock('/api/digital-twin/graph', 'mine_graph.json')
}

export async function getWorkers() {
  return fetchApiOrMock('/api/workers', 'workers.json')
}

export async function getRiskSegments() {
  return fetchApiOrMock('/api/risk/segments', 'risk_segments.json')
}

export async function getEnvironmentalRisk() {
  return fetchJson(mockUrl('environmental_risk.json'))
}

export async function getGeometryRisk() {
  return fetchJson(mockUrl('geometry_risk.json'))
}

export async function getScenarios() {
  return fetchJson(mockUrl('scenarios.json'))
}

export async function getEmergencyRoute(scenarioId) {
  return fetchApiOrMock(`/api/scenarios/collapse?scenario=${scenarioId}`, 'emergency_route.json')
}

export async function getGasSensors() {
  return fetchApiOrMock('/api/gas-sensors', 'gas_sensors.json')
}

export async function getSystemStatus() {
  return fetchJson(mockUrl('system_status.json'))
}

export async function getPointCloudMetadata() {
  return fetchApiOrMock('/api/digital-twin/pointcloud', 'pointcloud_metadata.json')
}

