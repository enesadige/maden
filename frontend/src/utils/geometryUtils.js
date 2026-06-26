export function buildSegmentLookup(segments) {
  const map = {}
  for (const segment of segments) {
    map[segment.segment_id] = segment
  }
  return map
}

export function buildConnectionLines(segments) {
  const lookup = buildSegmentLookup(segments)
  const lines = []
  const seen = new Set()

  for (const segment of segments) {
    for (const connectedId of segment.connected_segments || []) {
      const key = [segment.segment_id, connectedId].sort().join('-')
      if (seen.has(key)) continue
      seen.add(key)

      const target = lookup[connectedId]
      if (!target) continue

      lines.push({
        key,
        from: segment.center,
        to: target.center
      })
    }
  }

  return lines
}

export function buildRoutePoints(routeSegmentIds, segments) {
  const lookup = buildSegmentLookup(segments)
  return routeSegmentIds
    .map((id) => lookup[id]?.center)
    .filter(Boolean)
}
