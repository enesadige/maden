import { Component, useMemo, useRef, useState, useEffect, useCallback } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Line, Html } from '@react-three/drei'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import * as THREE from 'three'
import { getRiskColor, WORKER_COLOR, WORKER_AT_RISK_COLOR, ROUTE_COLOR, RISK_COLORS } from '../utils/riskColors'
import { buildConnectionLines, buildRouteEdges } from '../utils/geometryUtils'
import { getPointCloudMetadata, isApiMode, apiUrl } from '../services/api'

const UP = new THREE.Vector3(0, 1, 0)
const FORWARD = new THREE.Vector3(0, 0, 1)

const SHORT_LABELS = {
  S001: 'Giriş',
  S002: 'Ana Yol',
  S003: 'Dar Galeri',
  S004: 'Riskli Bölge',
  S005: 'Derin Tünel'
}

const AXIS_KEYS = ['x', 'y', 'z']
const WORKER_OVERLAY_OFFSETS = [
  [-1.8, 0, 2.2],
  [0, 0, 2.5],
  [1.8, 0, 2.2],
  [-2.4, 0, 0.4],
  [2.4, 0, 0.4],
  [-1.8, 0, -1.6],
  [1.8, 0, -1.6],
  [0, 0, -2.4]
]

function pointToArray(point) {
  if (Array.isArray(point)) return [Number(point[0]) || 0, Number(point[1]) || 0, Number(point[2]) || 0]
  if (point && typeof point === 'object') return [Number(point.x) || 0, Number(point.y) || 0, Number(point.z) || 0]
  return [0, 0, 0]
}

function getPointBounds(points) {
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  for (const point of points) {
    const arr = pointToArray(point)
    for (let i = 0; i < 3; i++) {
      min[i] = Math.min(min[i], arr[i])
      max[i] = Math.max(max[i], arr[i])
    }
  }
  const size = min.map((value, index) => Math.max(max[index] - value, 0.0001))
  const center = min.map((value, index) => value + size[index] / 2)
  return { min, max, size, center }
}

function largestAxes(size, count = 2) {
  return [0, 1, 2].sort((a, b) => size[b] - size[a]).slice(0, count)
}

function createPlyOverlayTransform(segments, plyBounds) {
  if (!plyBounds?.min || !plyBounds?.max || !segments?.length) return null
  const centers = segments.map(segment => segment.center).filter(Boolean)
  if (!centers.length) return null

  const source = getPointBounds(centers)
  const [sourceAxisA, sourceAxisB] = largestAxes(source.size, 2)
  const sourceVerticalAxis = [0, 1, 2].find(axis => axis !== sourceAxisA && axis !== sourceAxisB) ?? 2

  const targetMin = [plyBounds.min.x, plyBounds.min.y, plyBounds.min.z]
  const targetMax = [plyBounds.max.x, plyBounds.max.y, plyBounds.max.z]
  const targetSize = [plyBounds.size.x, plyBounds.size.y, plyBounds.size.z]
  const targetPaddingX = targetSize[0] * 0.06
  const targetPaddingZ = targetSize[2] * 0.06
  const targetY = targetMax[1] + Math.max(targetSize[1] * 0.035, 0.45)
  const verticalRange = Math.max(targetSize[1] * 0.08, 0.8)

  function mapAxis(value, sourceAxis, targetAxis, padding = 0) {
    const normalized = (value - source.min[sourceAxis]) / source.size[sourceAxis]
    return targetMin[targetAxis] + padding + normalized * Math.max(targetSize[targetAxis] - padding * 2, 0.0001)
  }

  return (point, extraY = 0) => {
    const arr = pointToArray(point)
    const verticalOffset = ((arr[sourceVerticalAxis] - source.center[sourceVerticalAxis]) / source.size[sourceVerticalAxis]) * verticalRange
    return [
      mapAxis(arr[sourceAxisA], sourceAxisA, 0, targetPaddingX),
      targetY + verticalOffset + extraY,
      mapAxis(arr[sourceAxisB], sourceAxisB, 2, targetPaddingZ)
    ]
  }
}

function transformSegmentsForPly(segments, transformPoint) {
  if (!transformPoint) return segments
  return segments.map(segment => ({ ...segment, center: transformPoint(segment.center) }))
}

function buildSegmentMap(segments) {
  const map = {}
  for (const segment of segments) map[segment.segment_id] = segment
  return map
}

function buildWorkerOverlayData(workers, sourceSegments, transformPoint) {
  if (!transformPoint) return workers
  const sourceMap = buildSegmentMap(sourceSegments)
  const slotBySegment = new Map()
  return workers.map(worker => {
    const segment = sourceMap[worker.current_segment]
    const basePoint = segment?.center || worker.position
    const slot = slotBySegment.get(worker.current_segment) || 0
    slotBySegment.set(worker.current_segment, slot + 1)
    const offset = WORKER_OVERLAY_OFFSETS[slot % WORKER_OVERLAY_OFFSETS.length]
    const position = transformPoint(basePoint, 0.9).map((value, index) => value + offset[index])
    return { ...worker, position }
  })
}

function buildSensorOverlayData(gasSensors, sourceSegments, transformPoint) {
  if (!transformPoint) return gasSensors || []
  const sourceMap = buildSegmentMap(sourceSegments)
  return (gasSensors || []).map((sensor, index) => {
    const segment = sourceMap[sensor.segment_id]
    const basePoint = segment?.center || sensor.position
    const side = index % 2 === 0 ? 1 : -1
    const position = transformPoint(basePoint, 1.1)
    return { ...sensor, position: [position[0] + side * 2.6, position[1], position[2] - 2.4] }
  })
}

function shortWorkerLabel(workerId) {
  const match = String(workerId || '').match(/(\d+)$/)
  return match ? `W${match[1].padStart(2, '0')}` : 'W'
}

function shortSensorLabel(sensorId, index) {
  const match = String(sensorId || '').match(/(\d+)$/)
  return match ? `G${match[1].padStart(2, '0')}` : `G${String(index + 1).padStart(2, '0')}`
}

// ─── Error Boundary ───────────────────────────────────────────────────────────

class ModelErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() { return { hasError: true } }
  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

// ─── PLY Loader ───────────────────────────────────────────────────────────────

function resolveUrl(url) {
  if (!url) return url
  if (isApiMode() && url.startsWith('/')) {
    return apiUrl(url)
  }
  return url
}

function LidarPointCloud({ setStatus, metadata, onLoaded, setFailReason }) {
  const [geometry, setGeometry] = useState(null)

  useEffect(() => {
    if (!metadata) return
    const loader = new PLYLoader()
    setStatus('loading')

    const onLoad = (geo, statusStr) => {
      geo.rotateX(-Math.PI / 2)
      geo.computeBoundingBox()
      const size = new THREE.Vector3()
      geo.boundingBox.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      if (maxDim > 0 && maxDim !== Infinity) {
        const scale = 160 / maxDim
        geo.scale(scale, scale, scale)
      }
      geo.center()
      geo.computeBoundingSphere()
      geo.computeBoundingBox()
      onLoaded(geo.boundingSphere, geo.boundingBox)
      setGeometry(geo)
      setStatus(statusStr)
    }

    // Build ordered list of URLs to try:
    // 1. Backend preview, 2. Backend downsampled, 3. Local preview, 4. Local downsampled
    const LOCAL_PREVIEW = '/models/tunnel_preview_500k.ply'
    const LOCAL_DOWNSAMPLED = '/models/tunnel_downsampled.ply'

    const urlsToTry = []
    if (metadata.preview_url) {
      const resolved = resolveUrl(metadata.preview_url)
      urlsToTry.push({ url: resolved, label: 'preview', source: resolved })
    }
    if (metadata.downsampled_url) {
      const resolved = resolveUrl(metadata.downsampled_url)
      urlsToTry.push({ url: resolved, label: 'downsampled', source: resolved })
    }
    // Always add local fallbacks if not already identical to what's above
    if (!urlsToTry.some(u => u.url === LOCAL_PREVIEW)) {
      urlsToTry.push({ url: LOCAL_PREVIEW, label: 'preview', source: 'local' })
    }
    if (!urlsToTry.some(u => u.url === LOCAL_DOWNSAMPLED)) {
      urlsToTry.push({ url: LOCAL_DOWNSAMPLED, label: 'downsampled', source: 'local' })
    }

    let idx = 0
    function tryNext(failedUrl) {
      if (failedUrl) console.warn('[PLY] Failed to load:', failedUrl)
      if (idx >= urlsToTry.length) {
        setFailReason('Backend CORS hatası ve local PLY dosyası bulunamadı')
        setStatus('not_found')
        return
      }
      const { url, label } = urlsToTry[idx++]
      loader.load(url, (geo) => onLoad(geo, label), undefined, () => tryNext(url))
    }
    tryNext()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metadata])

  if (!geometry) return null
  const hasColors = geometry.hasAttribute('color')
  return (
    <points geometry={geometry}>
      <pointsMaterial
        size={0.4}
        vertexColors={hasColors}
        color={hasColors ? 0xffffff : '#34f5c5'}
        sizeAttenuation={true}
        transparent
        opacity={hasColors ? 0.9 : 0.85}
      />
    </points>
  )
}

// ─── Camera Controller ────────────────────────────────────────────────────────

function CameraController({ bounds, cameraAction, onActionComplete }) {
  const { camera } = useThree()
  const controlsRef = useRef()

  useEffect(() => {
    if (!bounds || !controlsRef.current || !cameraAction) return
    const { center, radius, size } = bounds

    // For a flat mine (large X/Z, small Y), use actual dimensions for smart positioning
    const maxHoriz = size ? Math.max(size.x, size.z) : radius * 2
    const vertSize = size ? size.y : radius * 0.1

    camera.near = 0.1
    camera.far = Math.max(radius * 20, 1000)

    if (cameraAction === 'reset' || cameraAction === 'initial') {
      // Diagonal view: see the full flat mine from above-and-to-the-side
      const d = maxHoriz * 0.85
      camera.position.set(center.x, center.y + d * 0.45, center.z + d)
    } else if (cameraAction === 'top') {
      // Straight overhead: see the full XZ footprint
      const d = maxHoriz * 0.9
      camera.far = d * 3
      camera.position.set(center.x, center.y + d, center.z)
    } else if (cameraAction === 'side') {
      // Elevated side-front: see the mine width and depth at a readable angle
      const d = maxHoriz * 0.8
      camera.position.set(center.x + d * 0.3, center.y + vertSize * 3 + radius * 0.4, center.z - d)
    } else if (cameraAction === 'focus') {
      // Closer zoom-in for detail
      const d = maxHoriz * 0.3
      camera.position.set(center.x, center.y + d * 0.5, center.z + d)
    }

    camera.lookAt(center)
    camera.updateProjectionMatrix()
    controlsRef.current.target.copy(center)
    controlsRef.current.update()
    if (cameraAction !== 'initial') onActionComplete()
  }, [bounds, camera, cameraAction, onActionComplete])

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan={true}
      screenSpacePanning={true}
      enableZoom={true}
      enableRotate={true}
      panSpeed={0.8}
      rotateSpeed={0.8}
      zoomSpeed={1.2}
      maxPolarAngle={Math.PI - 0.05}
    />
  )
}

// ─── Placeholder Tunnel (when PLY not found) ──────────────────────────────────

function CorridorSegment({ line }) {
  const start = useMemo(() => new THREE.Vector3(...line.from), [line.from])
  const end = useMemo(() => new THREE.Vector3(...line.to), [line.to])
  const direction = useMemo(() => new THREE.Vector3().subVectors(end, start), [start, end])
  const length = direction.length()
  if (length < 0.01) return null

  const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5)
  const dirNormalized = direction.clone().normalize()
  const tubeQuaternion = new THREE.Quaternion().setFromUnitVectors(UP, dirNormalized)
  const ringQuaternion = new THREE.Quaternion().setFromUnitVectors(FORWARD, dirNormalized)

  let perp = new THREE.Vector3().crossVectors(dirNormalized, UP)
  if (perp.lengthSq() < 0.001) perp = new THREE.Vector3(1, 0, 0)
  perp.normalize().multiplyScalar(0.95)

  const floorY = -1.15
  const railA = [[start.x + perp.x, start.y + floorY, start.z + perp.z], [end.x + perp.x, end.y + floorY, end.z + perp.z]]
  const railB = [[start.x - perp.x, start.y + floorY, start.z - perp.z], [end.x - perp.x, end.y + floorY, end.z - perp.z]]
  const centerLine = [[start.x, start.y + floorY, start.z], [end.x, end.y + floorY, end.z]]
  const archCount = Math.max(2, Math.round(length / 4))
  const arches = []
  for (let i = 1; i <= archCount; i++) {
    const t = i / (archCount + 1)
    const pos = new THREE.Vector3().lerpVectors(start, end, t)
    arches.push(
      <group key={`arch-${line.key}-${i}`} position={pos} quaternion={ringQuaternion}>
        <mesh>
          <torusGeometry args={[1.35, 0.07, 8, 24]} />
          <meshStandardMaterial color="#4a5263" metalness={0.6} roughness={0.4} />
        </mesh>
      </group>
    )
  }

  return (
    <group>
      <mesh position={mid} quaternion={tubeQuaternion}>
        <cylinderGeometry args={[1.35, 1.35, length, 20, 1, true]} />
        <meshStandardMaterial color="#1a1e29" transparent opacity={0.3} side={THREE.DoubleSide} roughness={0.8} />
      </mesh>
      {arches}
      <Line points={railA} color="#525a68" lineWidth={1.2} />
      <Line points={railB} color="#525a68" lineWidth={1.2} />
      <Line points={centerLine} color="#2f3540" lineWidth={1} dashed dashSize={0.5} gapSize={0.4} />
    </group>
  )
}

function PlaceholderTunnel({ segments }) {
  const lines = useMemo(() => buildConnectionLines(segments), [segments])
  return (
    <group>
      {lines.map(line => <CorridorSegment key={line.key} line={line} />)}
      {segments.map(segment => (
        <group key={`chamber-${segment.segment_id}`} position={segment.center}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[1.7, 1.7, 2.8, 24, 1, true]} />
            <meshStandardMaterial color="#11141c" transparent opacity={0.4} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={[0, -1.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[1.7, 24]} />
            <meshStandardMaterial color="#0b0d14" />
          </mesh>
        </group>
      ))}
    </group>
  )
}

function BlockedMark() {
  const color = RISK_COLORS.critical
  return (
    <group position={[0, 0.1, 0]}>
      <mesh rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[2, 0.18, 0.18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
      </mesh>
      <mesh rotation={[0, 0, -Math.PI / 4]}>
        <boxGeometry args={[2, 0.18, 0.18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
      </mesh>
    </group>
  )
}

function DebrisField() {
  const chunks = useMemo(() => [
    { pos: [0.6, -0.9, 0.3], scale: 0.55, rot: [0.4, 0.2, 0.1] },
    { pos: [-0.7, -0.95, -0.2], scale: 0.4, rot: [0.1, 0.8, 0.3] },
    { pos: [0.1, -1.0, 0.6], scale: 0.35, rot: [0.6, 0.1, 0.5] },
    { pos: [-0.3, -0.85, 0.4], scale: 0.45, rot: [0.2, 0.5, 0.7] },
    { pos: [0.8, -0.9, -0.4], scale: 0.3, rot: [0.9, 0.3, 0.2] }
  ], [])
  return (
    <group>
      {chunks.map((c, i) => (
        <mesh key={i} position={c.pos} rotation={c.rot} scale={c.scale}>
          <dodecahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color="#3c372e" roughness={0.95} />
        </mesh>
      ))}
    </group>
  )
}

// ─── Full Overlay (shown only when PLY is NOT loaded) ─────────────────────────

function WorkerHelmetGlow({ color }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    ref.current.material.opacity = 0.5 + Math.sin(clock.elapsedTime * 3) * 0.25
  })
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.42, 0.55, 24]} />
      <meshBasicMaterial color={color} transparent opacity={0.5} side={THREE.DoubleSide} />
    </mesh>
  )
}

function SegmentMarker({ segment, risk, isSelected, onSelect }) {
  const isBlocked = segment.is_blocked
  const color = getRiskColor(risk?.risk_level, segment.is_blocked)
  const isCritical = !isBlocked && risk?.risk_level === 'critical'
  const isHigh = !isBlocked && risk?.risk_level === 'high'
  const haloColor = isCritical ? RISK_COLORS.critical : isHigh ? RISK_COLORS.high : null
  const shortLabel = SHORT_LABELS[segment.segment_id]

  return (
    <group position={segment.center}>
      {haloColor && (
        <mesh>
          <sphereGeometry args={[0.5, 20, 20]} />
          <meshBasicMaterial color={haloColor} transparent opacity={isCritical ? 0.25 : 0.15} />
        </mesh>
      )}
      <mesh onClick={e => { e.stopPropagation(); onSelect(segment.segment_id) }}>
        <sphereGeometry args={[isSelected ? 0.3 : 0.18, 24, 24]} />
        <meshStandardMaterial
          color={color} emissive={color}
          emissiveIntensity={isSelected ? 0.9 : (isCritical || isHigh) ? 0.6 : 0.35}
        />
      </mesh>
      {isBlocked && <><BlockedMark /><DebrisField /></>}
      <Html distanceFactor={22} position={[0, 1.2, 0]}>
        <div className="segment-label" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>
          {segment.segment_id}{shortLabel ? ` - ${shortLabel}` : ''}
        </div>
      </Html>
    </group>
  )
}

function WorkerMarker({ worker }) {
  const isAtRisk = worker.status === 'at_risk' || worker.status === 'trapped'
  const bodyColor = isAtRisk ? WORKER_AT_RISK_COLOR : WORKER_COLOR
  return (
    <group position={worker.position}>
      {isAtRisk && <WorkerHelmetGlow color={RISK_COLORS.critical} />}
      <mesh position={[0, 0.18, 0]}>
        <cylinderGeometry args={[0.16, 0.2, 0.4, 10]} />
        <meshStandardMaterial color={bodyColor} emissive={bodyColor} emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, 0.46, 0]}>
        <sphereGeometry args={[0.17, 14, 14]} />
        <meshStandardMaterial color="#ffd23a" emissive="#ffd23a" emissiveIntensity={0.4} />
      </mesh>
    </group>
  )
}

function GasSensorMarker({ sensor }) {
  const isAlarm = sensor.status === 'alarm'
  const color = isAlarm ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current || !isAlarm) return
    ref.current.material.emissiveIntensity = 0.7 + Math.sin(clock.elapsedTime * 6) * 0.4
  })
  return (
    <group position={sensor.position}>
      <mesh position={[0, -0.3, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 0.6, 8]} />
        <meshStandardMaterial color="#454c58" />
      </mesh>
      <mesh ref={ref} position={[0, 0.1, 0]} rotation={[0, 0, Math.PI / 4]}>
        <octahedronGeometry args={[isAlarm ? 0.32 : 0.24, 0]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={isAlarm ? 1 : 0.4} />
      </mesh>
    </group>
  )
}

function ConnectionLines({ segments }) {
  const lines = useMemo(() => buildConnectionLines(segments), [segments])
  return (
    <group>
      {lines.map(line => (
        <Line key={line.key} points={[line.from, line.to]} color="#4a5160" lineWidth={1.2} />
      ))}
    </group>
  )
}

function EmergencyRouteLine({ emergencyRoute, segments }) {
  const routeSegments = emergencyRoute?.route_segments || emergencyRoute?.route
  if (!routeSegments?.length) return null
  const routeEdges = buildRouteEdges(routeSegments, segments).filter(edge => edge.from && edge.to)
  if (!routeEdges.length) return null
  const isRouteSafe = Boolean(emergencyRoute.exit_reachable && emergencyRoute.alternative_route_available)
  return (
    <group>
      {routeEdges.map(edge => {
        const valid = edge.valid && emergencyRoute.route_edge_valid !== false
        const color = valid && isRouteSafe ? ROUTE_COLOR : RISK_COLORS.critical
        return (
          <Line
            key={edge.key}
            points={[
              [edge.from[0], edge.from[1] + 0.4, edge.from[2]],
              [edge.to[0], edge.to[1] + 0.4, edge.to[2]]
            ]}
            color={color}
            lineWidth={valid && isRouteSafe ? 4 : 3}
            dashed={!valid || !isRouteSafe}
            dashSize={0.6}
            gapSize={0.4}
          />
        )
      })}
    </group>
  )
}

// ─── Demo Overlay (shown when PLY loaded + mode = 'demo') ─────────────────────

function DemoOverlayLayer({ segments, risks, workers, gasSensors, emergencyRoute, selectedSegmentId, selectedWorkerId, onSelect }) {
  const riskBySegment = useMemo(() => {
    const map = {}
    for (const risk of risks) map[risk.segment_id] = risk
    return map
  }, [risks])

  const connLines = useMemo(() => buildConnectionLines(segments), [segments])

  const routeIds = useMemo(
    () => emergencyRoute?.route_segments || emergencyRoute?.route || [],
    [emergencyRoute]
  )
  const routeEdges = useMemo(() => buildRouteEdges(routeIds, segments), [routeIds, segments])
  const isRouteSafe = Boolean(emergencyRoute?.exit_reachable && emergencyRoute?.alternative_route_available)
  const hasInvalidRouteEdge = emergencyRoute?.route_edge_valid === false || routeEdges.some(edge => !edge.valid)

  return (
    <group>
      {connLines.map(line => (
        <Line key={line.key} points={[line.from, line.to]} color="#1a2030" lineWidth={0.6} />
      ))}

      {segments.map(seg => {
        const risk = riskBySegment[seg.segment_id]
        const color = getRiskColor(risk?.risk_level, seg.is_blocked)
        const isSelected = selectedSegmentId === seg.segment_id
        const isRouteSegment = routeIds.includes(seg.segment_id)
        return (
          <group key={seg.segment_id} position={seg.center}>
            <mesh onClick={e => { e.stopPropagation(); onSelect(seg.segment_id) }}>
              <sphereGeometry args={[isSelected ? 0.42 : isRouteSegment ? 0.28 : 0.18, 16, 16]} />
              <meshBasicMaterial color={color} transparent opacity={isSelected || isRouteSegment || seg.is_blocked ? 0.95 : 0.7} />
            </mesh>
            {seg.is_blocked && <><BlockedMark /><DebrisField /></>}
            {isSelected && (
              <Html distanceFactor={18} position={[0, 1.35, 0]}>
                <div className="demo-label-chip">{seg.segment_id}</div>
              </Html>
            )}
          </group>
        )
      })}

      {workers.map(w => {
        const isAtRisk = w.status === 'at_risk' || w.status === 'trapped'
        const selected = w.worker_id === selectedWorkerId
        const color = isAtRisk ? WORKER_AT_RISK_COLOR : WORKER_COLOR
        return (
          <group key={w.worker_id} position={w.position}>
            {selected && (
              <mesh rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[0.78, 1.02, 28]} />
                <meshBasicMaterial color="#ffffff" transparent opacity={0.8} side={THREE.DoubleSide} />
              </mesh>
            )}
            {isAtRisk && <WorkerHelmetGlow color={RISK_COLORS.critical} />}
            <mesh position={[0, 0.2, 0]}>
              <sphereGeometry args={[0.52, 16, 16]} />
              <meshBasicMaterial color={color} />
            </mesh>
            <mesh position={[0, 0.78, 0]}>
              <sphereGeometry args={[0.28, 14, 14]} />
              <meshBasicMaterial color="#ffd23a" />
            </mesh>
            <Html distanceFactor={18} position={[0, 1.45, 0]}>
              <div className={`demo-worker-chip${selected ? ' demo-worker-chip--selected' : ''}`}>
                {shortWorkerLabel(w.worker_id)}
              </div>
            </Html>
          </group>
        )
      })}

      {(gasSensors || []).map((sensor, index) => {
        const color = sensor.status === 'alarm' ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
        return (
          <group key={sensor.sensor_id} position={sensor.position}>
            <mesh position={[0, -0.45, 0]}>
              <cylinderGeometry args={[0.08, 0.08, 0.9, 8]} />
              <meshBasicMaterial color="#8a92a6" />
            </mesh>
            <mesh rotation={[0, 0, Math.PI / 4]}>
              <octahedronGeometry args={[0.48, 0]} />
              <meshBasicMaterial color={color} transparent opacity={0.95} />
            </mesh>
            <Html distanceFactor={18} position={[0, 0.95, 0]}>
              <div className="demo-sensor-chip">{shortSensorLabel(sensor.sensor_id, index)}</div>
            </Html>
          </group>
        )
      })}

      {routeEdges.filter(edge => edge.from && edge.to).map(edge => {
        const valid = edge.valid && emergencyRoute?.route_edge_valid !== false
        const mid = [
          (edge.from[0] + edge.to[0]) / 2,
          (edge.from[1] + edge.to[1]) / 2 + 1.25,
          (edge.from[2] + edge.to[2]) / 2
        ]
        return (
          <group key={edge.key}>
            <Line
              points={[
                [edge.from[0], edge.from[1] + 0.08, edge.from[2]],
                [edge.to[0], edge.to[1] + 0.08, edge.to[2]]
              ]}
              color={valid && isRouteSafe ? ROUTE_COLOR : RISK_COLORS.critical}
              lineWidth={valid && isRouteSafe ? 5 : 3}
              dashed={!valid || !isRouteSafe}
              dashSize={0.5}
              gapSize={0.4}
            />
            {!valid && (
              <Html distanceFactor={18} position={mid}>
                <div className="demo-route-warning-chip">
                  Graph bağlantısı yok: {edge.source} → {edge.target}
                </div>
              </Html>
            )}
          </group>
        )
      })}

      {hasInvalidRouteEdge && routeEdges.length > 0 && (
        <Html distanceFactor={18} position={[
          routeEdges.find(edge => edge.from)?.from?.[0] || 0,
          (routeEdges.find(edge => edge.from)?.from?.[1] || 0) + 2.4,
          routeEdges.find(edge => edge.from)?.from?.[2] || 0
        ]}>
          <div className="demo-route-warning-chip">
            Rota graph doğrulamasından geçmedi.
          </div>
        </Html>
      )}
    </group>
  )
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function DigitalTwinViewer({
  segments,
  risks,
  workers,
  gasSensors,
  emergencyRoute,
  onSegmentSelect,
  selectedSegmentId,
  selectedWorkerId
}) {
  const [plyStatus, setPlyStatus] = useState('loading')
  const [plyMetadata, setPlyMetadata] = useState(null)
  const [plyBounds, setPlyBounds] = useState(null)
  const [cameraAction, setCameraAction] = useState(null)
  const [overlayMode, setOverlayMode] = useState('demo')
  const [plyFailReason, setPlyFailReason] = useState('')

  useEffect(() => {
    getPointCloudMetadata()
      .then(meta => setPlyMetadata(meta))
      .catch(() => setPlyMetadata({
        preview_url: '/models/tunnel_preview_500k.ply',
        downsampled_url: '/models/tunnel_downsampled.ply'
      }))
  }, [])

  const handlePlyLoaded = useCallback((sphere, box) => {
    const size = new THREE.Vector3()
    if (box) box.getSize(size)
    setPlyBounds({
      center: sphere.center.clone(),
      radius: sphere.radius,
      size,
      min: box?.min.clone(),
      max: box?.max.clone()
    })
    setCameraAction('initial')
  }, [])

  const riskBySegment = useMemo(() => {
    const map = {}
    for (const risk of risks) map[risk.segment_id] = risk
    return map
  }, [risks])

  const isRealPlyLoaded = plyStatus === 'preview' || plyStatus === 'downsampled'
  const showFullOverlays = !isRealPlyLoaded
  const showDemoOverlay = isRealPlyLoaded && overlayMode === 'demo'
  const plyOverlayTransform = useMemo(
    () => createPlyOverlayTransform(segments, plyBounds),
    [segments, plyBounds]
  )
  const plyOverlaySegments = useMemo(
    () => transformSegmentsForPly(segments, plyOverlayTransform),
    [segments, plyOverlayTransform]
  )
  const plyOverlayWorkers = useMemo(
    () => buildWorkerOverlayData(workers, segments, plyOverlayTransform),
    [workers, segments, plyOverlayTransform]
  )
  const plyOverlayGasSensors = useMemo(
    () => buildSensorOverlayData(gasSensors, segments, plyOverlayTransform),
    [gasSensors, segments, plyOverlayTransform]
  )

  let statusText = 'Yükleniyor...'
  if (plyStatus === 'preview') {
    const file = plyMetadata?.preview_url?.split('/').pop() || 'tunnel_preview_500k.ply'
    statusText = `Gerçek LiDAR point cloud yüklendi: ${file}`
  } else if (plyStatus === 'downsampled') {
    const file = plyMetadata?.downsampled_url?.split('/').pop() || 'tunnel_downsampled.ply'
    statusText = `Gerçek LiDAR point cloud yüklendi: ${file}`
  } else if (plyStatus === 'not_found') {
    statusText = `LiDAR modeli yüklenemedi — ${plyFailReason || 'PLY dosyası bulunamadı'}.`
  }

  return (
    <div className="viewer-canvas">
      {/* Status indicator */}
      <div className="viewer-status-bar">
        <span
          className="viewer-status-dot"
          style={{ background: plyStatus === 'not_found' ? '#f5a623' : plyStatus === 'loading' ? '#8a92a6' : '#34f5c5' }}
        />
        {statusText}
      </div>

      {/* Demo overlay warning strip */}
      {isRealPlyLoaded && overlayMode === 'demo' && (
        <div className="overlay-demo-warning">
          Demo overlay: segment, işçi, sensör ve rota LiDAR üstüne yaklaşık hizalanmıştır.
        </div>
      )}

      {/* Controls: camera buttons + overlay toggle */}
      <div className="viewer-controls-panel">
        <div className="viewer-camera-buttons">
          <button onClick={() => setCameraAction('reset')} className="scenario-button">Reset</button>
          <button onClick={() => setCameraAction('top')} className="scenario-button">Üstten</button>
          <button onClick={() => setCameraAction('side')} className="scenario-button">Yandan</button>
          <button onClick={() => setCameraAction('focus')} className="scenario-button">Odaklan</button>
        </div>

        {isRealPlyLoaded && (
          <div className="overlay-toggle">
            <span className="overlay-toggle-label">3B Overlay:</span>
            <button
              className={`overlay-toggle-btn${overlayMode === 'off' ? ' overlay-toggle-btn--active' : ''}`}
              onClick={() => setOverlayMode('off')}
            >
              Kapalı
            </button>
            <button
              className={`overlay-toggle-btn${overlayMode === 'demo' ? ' overlay-toggle-btn--active' : ''}`}
              onClick={() => setOverlayMode('demo')}
            >
              Demo
            </button>
          </div>
        )}
      </div>

      {/* Bottom info: PLY/Map relation or off-mode note */}
      {isRealPlyLoaded && (
        <div className="ply-info-note">
          {overlayMode === 'off'
            ? '3B overlay kapalı — risk/worker/gaz detayları için Harita Görünümü\'nü kullanın.'
            : 'PLY üstünde segment ağı, işçi, gaz sensörü, göçük ve acil rota katmanları yaklaşık hizalama ile gösteriliyor.'
          }
        </div>
      )}

      {/* Three.js Canvas */}
      <Canvas camera={{ fov: 45, position: [0, 120, 200], near: 0.1, far: 2000 }}>
        <fog attach="fog" args={['#06080b', 200, 1200]} />
        <color attach="background" args={['#06080b']} />
        <ambientLight intensity={0.4} />
        <directionalLight position={[15, 20, 10]} intensity={0.9} color="#e6f2ff" />
        <pointLight position={[6, 5, 8]} intensity={0.8} color="#34f5c5" distance={40} />

        <LidarPointCloud setStatus={setPlyStatus} metadata={plyMetadata} onLoaded={handlePlyLoaded} setFailReason={setPlyFailReason} />

        {plyStatus === 'not_found' && <PlaceholderTunnel segments={segments} />}

        {showFullOverlays && (
          <>
            <ConnectionLines segments={segments} />
            {segments.map(segment => (
              <SegmentMarker
                key={segment.segment_id}
                segment={segment}
                risk={riskBySegment[segment.segment_id]}
                isSelected={selectedSegmentId === segment.segment_id}
                onSelect={onSegmentSelect}
              />
            ))}
            {workers.map(worker => <WorkerMarker key={worker.worker_id} worker={worker} />)}
            {(gasSensors || []).map(sensor => <GasSensorMarker key={sensor.sensor_id} sensor={sensor} />)}
            <EmergencyRouteLine emergencyRoute={emergencyRoute} segments={segments} />
          </>
        )}

        {showDemoOverlay && (
          <DemoOverlayLayer
            segments={plyOverlaySegments}
            risks={risks}
            workers={plyOverlayWorkers}
            gasSensors={plyOverlayGasSensors}
            emergencyRoute={emergencyRoute}
            selectedSegmentId={selectedSegmentId}
            selectedWorkerId={selectedWorkerId}
            onSelect={onSegmentSelect}
          />
        )}

        <gridHelper args={[500, 500, '#1c1f27', '#0a0c11']} position={[0, -3, 0]} />
        <CameraController
          bounds={plyBounds}
          cameraAction={cameraAction}
          onActionComplete={() => setCameraAction(null)}
        />
      </Canvas>
    </div>
  )
}
