# Haki LiDAR Handoff

This document records Haki's LiDAR / digital twin handoff without changing the
current backend sample API files.

## Location

Haki outputs are staged under:

```text
backend/data_processed/sample/haki_lidar/
```

This folder is intentionally separate from the current backend sample files such
as `backend/data_processed/sample/digital_twin/segments.json`. The existing
backend route engine still expects the legacy `from_node` / `to_node` segment
format, so this handoff does not overwrite those files.

## Files

```text
haki_lidar/
  pointcloud/
    global_shift.json
    tunnel_preview_500k.ply
    tunnel_downsampled.ply

  segments/
    map_segments.json
    segment_metadata.json

  graph/
    mine_graph.json

  risk/
    geometry_risk.json

  viewer_ground_truth/
    walkable_floor_highlight.ply
    artifact_markers.ply
    ground_truth_artifacts_local.json
    ex_topology_graph.json
    floor_density_topdown.svg
    preview.html
    road_visibility_layers.json
    road_visibility_summary.json
```

## Segment ID Standard

All new Haki outputs use:

```text
S001, S002, S003, ...
```

Legacy `SEG_047`, `S47`, or `S04` values should be normalized by backend code to
`S047` / `S004` before joining with worker, gas, risk, or route data.

## Digital Twin Layers

The point-cloud digital twin is a layered scene:

```text
tunnel_downsampled.ply
walkable_floor_highlight.ply
artifact_markers.ply
map_segments.json
mine_graph.json
geometry_risk.json
```

The `walkable_floor_highlight.ply` layer is generated from actual LiDAR
floor-like points. It is preferred over synthetic grid centerline overlays for
road visibility.

## Important Limitation

`systems_tunnel_ground_truth-master/network/data/ex_edgelist.csv` provides the
DARPA EX topology and chokepoint metadata, but it does not include 3D node
coordinates. It should be used for route logic and graph validation, not drawn
directly over the LiDAR point cloud without registration.

## Frontend Loading Suggestion

Load these first:

```text
backend/data_processed/sample/haki_lidar/pointcloud/tunnel_downsampled.ply
backend/data_processed/sample/haki_lidar/viewer_ground_truth/walkable_floor_highlight.ply
backend/data_processed/sample/haki_lidar/viewer_ground_truth/artifact_markers.ply
```

Suggested point sizes:

```text
tunnel_downsampled.ply        0.018 - 0.03
walkable_floor_highlight.ply  0.07 - 0.10
artifact_markers.ply          0.10 - 0.14
```

## Pipeline Scripts

```text
pipelines/colab_lidar_pipeline.ipynb
pipelines/colab_lidar_pipeline.py
pipelines/generate_ground_truth_road_visibility.py
```

The Colab notebook produces the base pointcloud, segment, graph, and geometry
risk outputs. The road visibility script produces ground-truth-aware viewer
layers from the processed point cloud.
