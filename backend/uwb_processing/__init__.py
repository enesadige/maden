"""MadenGuard UWB worker-tracking MVP package.

The current Haki handoff provides bounds-center geometry. Dynamic anchor planning is performed at segment/graph level using segment centers, bounds, graph edges and edge weights. Exact centerline-based tunnel curve placement is not available until Haki provides centerline/start-end geometry.

UTIL UWB pose_x, pose_y and pose_z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions. In this MVP they are used only as worker movement proxies.

TODO:
- expose the stable public pipeline interface after implementation
"""
