---
inclusion: fileMatch
fileMatchPattern: "{src/**/*.py,frontend/**/*.js}"
---

# Documentation Sync

When modifying any source file under `src/` or `frontend/`, verify that documentation stays in sync.

## Checklist

After any change to API endpoints, request/response shapes, query parameters, error handling, algorithms, or technical behavior:

1. **`doc/api.md`** — Update the affected endpoint's section:
   - Request parameters (new fields, changed constraints, removed fields)
   - Response shape (new fields, changed types, removed fields)
   - Example JSON (must reflect the actual current response)
   - If a new endpoint is added, add a full section with method, path, parameters, and example response

2. **`README.md`** — If the change affects user-facing features:
   - Update the Features list if a new capability was added or removed
   - Update Usage instructions if the workflow changed
   - Update the Schedule Grid section if grid behavior changed

3. **`doc/algorithms.md`** — If the change affects algorithm behavior:
   - Team strength ratings (iteration, dampening, convergence)
   - Clinching scenarios solver (pipeline, thresholds, method selection)
   - CP solver (hybrid approach, constraint propagation, decomposition)
   - Update diagrams if the flow changed

4. **`doc/technical.md`** — If the change affects:
   - Parallel simulation (worker distribution, merging, platform behavior)
   - Solver performance export (data flow, file format, grouping logic)

5. **`doc/solver-performance.md`** — If the export format or columns change:
   - Note: this file is machine-generated; update the `_FILE_HEADER` in `src/experience_export.py` instead

## What counts as an API surface change

- Adding, removing, or renaming an endpoint
- Adding or removing a field in a request body or response
- Changing parameter types, defaults, or validation constraints
- Changing error codes or error message format
- Changing the semantics of an existing field (e.g., percentage vs fraction)

## Verification

After updating docs, confirm:
- Example JSON in `doc/api.md` is valid JSON (no trailing commas, correct types)
- Parameter tables match the actual validation logic in `server.py`
- No stale endpoint references remain in any doc file
