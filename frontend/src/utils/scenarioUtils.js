function cloneSegments(segments) {
  return segments.map((segment) => ({ ...segment }))
}

function cloneRisks(risks) {
  return risks.map((risk) => ({ ...risk, active_reasons: [...risk.active_reasons] }))
}

function cloneWorkers(workers) {
  return workers.map((worker) => ({ ...worker }))
}

function cloneGasSensors(gasSensors) {
  return (gasSensors || []).map((sensor) => ({ ...sensor }))
}

/**
 * Derives the dashboard state for a given scenario from the base mock/API data.
 * Mirrors the fusion logic the backend will eventually perform server-side.
 */
export function applyScenario(scenarioId, baseData, emergencyRouteData) {
  const segments = cloneSegments(baseData.segments)
  const risks = cloneRisks(baseData.risks)
  const workers = cloneWorkers(baseData.workers)
  const gasSensors = cloneGasSensors(baseData.gasSensors)
  let emergencyRoute = null

  const riskByIdMap = {}
  for (const risk of risks) riskByIdMap[risk.segment_id] = risk

  const workerByIdMap = {}
  for (const worker of workers) workerByIdMap[worker.worker_id] = worker

  const gasSensorByIdMap = {}
  for (const sensor of gasSensors) gasSensorByIdMap[sensor.sensor_id] = sensor

  switch (scenarioId) {
    case 'methane_spike': {
      const s004Risk = riskByIdMap.S004
      if (s004Risk) {
        s004Risk.risk_level = 'critical'
        s004Risk.risk_score = 92
        if (!s004Risk.active_reasons.includes('metan anomalisi tespit edildi')) {
          s004Risk.active_reasons.push('metan anomalisi tespit edildi')
        }
        s004Risk.recommended_action = 'Rota varsa tahliye ol; yoksa kurtarma talimatı bekle.'
      }

      const primarySensor = gasSensorByIdMap['GAS-001'] || gasSensorByIdMap['GAS_SENSOR_01'] || gasSensors?.[0]
      if (primarySensor) {
        primarySensor.methane_value = 4.8
        primarySensor.risk_score = 91
        primarySensor.risk_level = 'critical'
        primarySensor.status = 'alarm'
      }
      break
    }

    case 'collapse_s004': {
      const blockedSegment = segments.find((s) => s.segment_id === 'S004')
      if (blockedSegment) {
        blockedSegment.status = 'blocked'
        blockedSegment.is_blocked = true
      }

      const s004Risk = riskByIdMap.S004
      if (s004Risk) {
        s004Risk.risk_level = 'critical'
        s004Risk.risk_score = 90
        if (!s004Risk.active_reasons.includes('göçük / segment kapalı')) {
          s004Risk.active_reasons.push('göçük / segment kapalı')
        }
      }

      emergencyRoute = emergencyRouteData || null
      break
    }

    case 'worker_at_risk': {
      const worker = workerByIdMap.W001
      if (worker) worker.status = 'at_risk'

      const riskSegmentId = worker?.current_segment
      const atRiskSegmentRisk = riskSegmentId ? riskByIdMap[riskSegmentId] : null
      if (atRiskSegmentRisk) {
        atRiskSegmentRisk.risk_level = 'critical'
        atRiskSegmentRisk.risk_score = 85
        if (!atRiskSegmentRisk.active_reasons.includes('işçi riskli segmentte')) {
          atRiskSegmentRisk.active_reasons.push('işçi riskli segmentte')
        }
      }
      break
    }

    case 'show_route': {
      emergencyRoute = emergencyRouteData || null
      break
    }

    case 'normal':
    default:
      break
  }

  return { segments, risks, workers, gasSensors, emergencyRoute }
}

export function findMostCriticalRisk(risks) {
  const order = { critical: 4, high: 3, medium: 2, low: 1, unknown: 0 }
  return [...risks].sort((a, b) => (order[b.risk_level] || 0) - (order[a.risk_level] || 0))[0]
}

/**
 * Picks which segment the Risk Panel should jump to right after a scenario
 * switch, so the panel never lingers on a stale segment that no longer
 * matches the active story (e.g. staying on S01 during a methane alarm).
 */
export function getFocusSegmentId(scenarioId, derived) {
  const { segments, risks, workers, gasSensors, emergencyRoute } = derived

  switch (scenarioId) {
    case 'normal':
      return segments.find((s) => s.is_exit)?.segment_id || segments[0]?.segment_id || null

    case 'methane_spike': {
      const alarmSensor = gasSensors?.find((s) => s.status === 'alarm')
      return alarmSensor?.segment_id || findMostCriticalRisk(risks)?.segment_id || null
    }

    case 'collapse_s004':
    case 'show_route':
      return emergencyRoute?.blocked_segment || findMostCriticalRisk(risks)?.segment_id || null

    case 'worker_at_risk': {
      const atRiskWorker = workers.find((w) => w.status === 'at_risk')
      return atRiskWorker?.current_segment || null
    }

    default:
      return null
  }
}
