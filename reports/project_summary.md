# MadenGuard AI Project Summary

MadenGuard AI is now set up as a local, raw-data-safe prototype under `/Users/enesdasci/Desktop/madenguard`.

## What This Pass Built

- Raw data paths are configured in `config/paths.json` and `config/paths.yaml`.
- The 10 GB MediumRes LAS remains on the NTFS flash disk and is not copied into the project.
- A lightweight LAS reader extracts header metadata and a small point sample without calling `las.read()`.
- DARPA EX graph edges are converted into segment records.
- LiDAR sampled points are converted into slice-level geometry risk features.
- UTIL UWB pose data is converted into a worker timeline.
- Methane CSV data is converted into a gas sensor risk timeline.
- UCI batch DAT files are converted into sensor reliability/drift summaries.
- Graph blocking/chokepoint risk is computed per segment.
- Segment risk is fused by time step.
- A route stress-test scenario is produced from the highest-risk local-safe pass result.
- A self-contained HTML dashboard is generated.

## Current Result

The first local-safe run did not produce a CRITICAL risk segment. The emergency route layer therefore reports a highest-risk segment stress test instead of claiming a real critical collapse event.

## Safety Notes

- Raw LAS copied locally: no.
- Full LAS loaded into RAM: no.
- Local project size after first run: about 14 MB.
- Dashboard point layer: sampled/embedded only.

## Next Technical Step

Install `laspy` or `PDAL` if a fuller LiDAR pass is needed. The current code already has PDAL pipeline JSON files for CloudCompare-ready decimated LAS outputs, but PDAL is not installed on this Mac yet.
