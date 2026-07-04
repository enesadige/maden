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

function hasGraphConnection(source, target) {
  if (!source || !target) return false
  const sourceConnections = source.connected_segments || []
  const targetConnections = target.connected_segments || []
  return sourceConnections.includes(target.segment_id) || targetConnections.includes(source.segment_id)
}

export function buildRouteEdges(routeSegmentIds, segments) {
  const lookup = buildSegmentLookup(segments)
  const edges = []
  for (let index = 0; index < routeSegmentIds.length - 1; index += 1) {
    const sourceId = routeSegmentIds[index]
    const targetId = routeSegmentIds[index + 1]
    const source = lookup[sourceId]
    const target = lookup[targetId]
    if (!source?.center || !target?.center) {
      edges.push({
        key: `${sourceId}-${targetId}-${index}`,
        source: sourceId,
        target: targetId,
        from: source?.center,
        to: target?.center,
        valid: false,
        missingPoint: true
      })
      continue
    }
    edges.push({
      key: `${sourceId}-${targetId}-${index}`,
      source: sourceId,
      target: targetId,
      from: source.center,
      to: target.center,
      valid: hasGraphConnection(source, target),
      missingPoint: false
    })
  }
  return edges
}
