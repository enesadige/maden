export const RISK_COLORS = {
  low: '#3ddc84',
  medium: '#f5a623',
  high: '#ff5630',
  critical: '#e3174f',
  blocked: '#333740',
  unknown: '#7a8290'
}

export const WORKER_COLOR = '#3aa0ff'
export const WORKER_AT_RISK_COLOR = '#ffd23a'
export const ROUTE_COLOR = '#34f5c5'

export function getRiskColor(riskLevel, isBlocked) {
  if (isBlocked) return RISK_COLORS.blocked
  return RISK_COLORS[riskLevel] || RISK_COLORS.unknown
}

export function getRiskLabel(riskLevel) {
  const labels = {
    low: 'Düşük',
    medium: 'Orta',
    high: 'Yüksek',
    critical: 'Kritik',
    blocked: 'Kapalı',
    unknown: 'Bilinmiyor'
  }
  return labels[riskLevel] || labels.unknown
}
