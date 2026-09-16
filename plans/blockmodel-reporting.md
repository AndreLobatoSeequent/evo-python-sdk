# Block Model Reports — CLI Implementation Plan

## Architecture notes

- All report API calls go through `client._reports_api.*` (not yet promoted to high-level `BlockModelAPIClient` methods — we call it directly, same as the typed wrapper does)
- `create` and `update` need a silent column-resolution step: fetch the latest version to build a `title → col_id` map before calling the API (no output unless it fails)
- Results output as a plain-text ASCII table — the natural representation of tabular grade/tonnage data
- New file: `packages/evo-cli/src/evo/cli/blockmodels/reports.py`

---

## Phase 1 — Read commands (list, get spec)

**Status: DONE** — `reports.py` implemented, 8 tests passing in `test_blockmodels_reports.py`

**Commands:**
```
evo blockmodels reports list <bm_id>
evo blockmodels reports get  <bm_id> <spec_id>
```

**What to implement:**
- `list` calls `_reports_api.list_block_model_report_specifications` → renders name, spec UUID, autorun flag, last run version + date
- `get` calls `_reports_api.get_report_specification` → renders full spec: columns (title, aggregation, unit), categories, density settings, cutoffs, autorun, bbox

**Output helpers to write:**
- `_spec_to_dict(spec)` — serialises `ReportSpecificationWithLastRunInfo` to JSON-friendly dict
- `_format_spec_plain(data)` — multi-line plain text summary

No tricky bits here. Good warm-up before the write commands.

---

## Phase 2 — Write commands (create, update)

**Status: DONE** — 9 tests passing in `test_blockmodels_reports_write.py`

**Commands:**
```
evo blockmodels reports create <bm_id>
    --name "Gold Report"
    --column "Au:MASS_AVERAGE:g/t"        # title:aggregation[:unit], repeat
    --category "Domain"                    # title[:label], repeat, max 5
    --density-column "Density"             # OR:
    --density-value 2.7 --density-unit t/m3
    --mass-unit t
    --cutoff-column "Au"                   # optional
    --cutoff 0.5 --cutoff 1.0             # repeat, max 20
    --autorun / --no-autorun              # default: autorun
    --no-run-now                          # skip immediate run (default: run now)

evo blockmodels reports update <bm_id> <spec_id>   [same flags, all optional]
```

**What to implement:**
- `_parse_column_spec(entry)` — parses `"Title:AGG:unit"` → `ReportColumnSpec`; `AGG` accepts `SUM`, `AVG` (alias for `MASS_AVERAGE`), `MASS_AVERAGE`
- `_parse_category_spec(entry)` — parses `"Title"` or `"Title:Label"` → `ReportCategorySpec`
- Silent resolution step: `await client.get_version(bm_uuid, latest_version_uuid)` to build `{title: col_id}` map; errors here surface normally
- Calls `_reports_api.create_report_specification` or `update_report_specification`

**Output:** spec summary (same as `get`) + `"Created"` / `"Updated"` prefix

**Complexity:** `update` must fetch the existing spec first to know which fields to patch (`UpdateReportSpecification` model — check which fields it accepts)

---

## Phase 3 — Result commands (run, results list, results get)

**Status: DONE** — 8 tests passing in `test_blockmodels_reports_write.py`

**Commands:**
```
evo blockmodels reports run <bm_id> <spec_id> [--version-uuid <uuid>]
evo blockmodels reports results list <bm_id> <spec_id>
evo blockmodels reports results get  <bm_id> <spec_id> <result_uuid>
```

**What to implement:**
- `run` → calls `_reports_api.run_reporting_job` then immediately fetches the result via `_reports_api.get_report_result` (two calls, single output — the result table)
- `results list` → calls `_reports_api.get_report_results_list` → table of result UUIDs, version IDs, run dates
- `results get` → fetches one `ReportResult` → renders the result table

**Result table renderer** (`_format_result_table`): adapts `ReportResult.to_dataframe()` logic without the pandas dependency — iterates `result_sets → rows` directly, produces a fixed-width plain-text table with cutoff, category columns, value columns

**Output example:**
```
Report: Gold Resource Report  (spec_uuid)
Block model v5  2025-06-01T09:30:00Z

cutoff  Domain   Tonnage       Au Grade
------- -------  ------------  --------
0.0     North    1,250,000 t   1.80 g/t
0.0     South      980,000 t   2.10 g/t
0.5     North      870,000 t   2.30 g/t
```

This phase is the most valuable for users — prioritise the renderer quality.

---

## Phase 4 — Compare command

**Status: DONE** — 4 tests passing in `test_blockmodels_reports_write.py`

**Command:**
```
evo blockmodels reports compare <bm_id> <spec_id> --from <result_uuid> --to <result_uuid>
```

**What to implement:**
- Calls `_reports_api.get_report_result_comparison`
- Renders a delta table: same structure as the result table but each value shows `from → to` and `Δ%`

**Lowest priority** — implement after Phase 3 is solid.

---

## Suggested implementation order

1. **Phase 1** — Read commands. Zero complexity, establishes file structure and `_spec_to_dict` helper.
2. **Phase 3** (results get/list first) — Build the result table renderer before the create command, so existing specs can be validated end-to-end immediately.
3. **Phase 2** — Create/update. Parser complexity, but with Phase 3 done you can test immediately.
4. **Phase 3** (run) — Simple once result rendering exists.
5. **Phase 4** — Compare, when the rest is stable.
