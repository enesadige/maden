// Backend source-of-truth (Haki) artık S001/S002/.../W001/GAS-001 formatını kullanıyor.
// Bu dosya, eski prototip formatında (S04, S4, SEG_047, W01) bir API yanıtı
// gelirse frontend'in çökmemesi için savunma amaçlı bir normalizasyon katmanıdır.
// Mock veriler zaten yeni formatta; bu sadece gerçek API mode için bir güvenlik ağıdır.

function pad(prefix, numStr) {
  return `${prefix}${numStr.padStart(3, '0')}`
}

export function normalizeSegmentId(id) {
  if (typeof id !== 'string') return id
  const match = id.match(/^(?:SEG[_-]?|S)(\d+)$/i)
  if (!match) return id
  return pad('S', match[1])
}

export function normalizeWorkerId(id) {
  if (typeof id !== 'string') return id
  const match = id.match(/^(?:WORKER[_-]?|W)(\d+)$/i)
  if (!match) return id
  const num = parseInt(match[1], 10)
  return `WORKER_${num.toString().padStart(2, '0')}`
}

export function formatWorkerName(workerId, name) {
  if (name) return name
  if (typeof workerId !== 'string') return workerId
  const match = workerId.match(/^(?:WORKER[_-]?|W)(\d+)$/i)
  if (match) {
    const num = parseInt(match[1], 10)
    return `İşçi ${num.toString().padStart(2, '0')}`
  }
  return workerId
}

export function normalizeSensorId(id) {
  if (typeof id !== 'string') return id
  // Matches: GAS-001, GAS_001, GAS_SENSOR_01, GAS-SENSOR-01, etc.
  const match = id.match(/^GAS[_-](?:SENSOR[_-])?(\d+)$/i)
  if (!match) return id
  return pad('GAS-', match[1])
}

const SEGMENT_KEYS = new Set(['segment_id', 'current_segment', 'blocked_segment', 'exit_segment'])
const SEGMENT_LIST_KEYS = new Set(['connected_segments', 'route', 'route_segments'])
const WORKER_KEYS = new Set(['worker_id'])
const WORKER_LIST_KEYS = new Set(['affected_workers'])
const SENSOR_KEYS = new Set(['sensor_id'])

// API yanıtındaki bilinen ID alanlarını yeni formata çevirerek dolaşır.
// Bilinmeyen alanlara dokunmaz, segment_id eşleşme mantığını bozmaz.
export function normalizeApiPayload(data) {
  if (Array.isArray(data)) return data.map(normalizeApiPayload)
  if (data === null || typeof data !== 'object') return data

  const result = {}
  for (const [key, value] of Object.entries(data)) {
    if (SEGMENT_KEYS.has(key)) {
      result[key] = normalizeSegmentId(value)
    } else if (SEGMENT_LIST_KEYS.has(key) && Array.isArray(value)) {
      result[key] = value.map(normalizeSegmentId)
    } else if (WORKER_KEYS.has(key)) {
      result[key] = normalizeWorkerId(value)
    } else if (WORKER_LIST_KEYS.has(key) && Array.isArray(value)) {
      result[key] = value.map(normalizeWorkerId)
    } else if (SENSOR_KEYS.has(key)) {
      result[key] = normalizeSensorId(value)
    } else if (Array.isArray(value) || (value !== null && typeof value === 'object')) {
      result[key] = normalizeApiPayload(value)
    } else {
      result[key] = value
    }
  }
  return result
}
