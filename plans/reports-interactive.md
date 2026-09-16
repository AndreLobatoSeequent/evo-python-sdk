# Block Model Reports — Interactive Create Wizard

## Goal

Add `--interactive` / `-i` to `evo blockmodels reports create` (and `update`) to guide
users through building a report specification step-by-step. The wizard fetches live data
at each stage so users select real column names, real unit IDs, and real aggregation
options — no memorising API strings required.

`bm_id` becomes **optional** when `--interactive` is set: if omitted the wizard opens
with a block model selection step first. CLI flags already provided skip their step.

Non-interactive behaviour is unchanged.

---

## Visual style — `emit_panel`

A new `emit_panel(title, body_lines, *, width=68)` helper is added to `evo.cli.output`.
It uses single-line Unicode box-drawing (same style as error borders in some terminal
UIs). It is a no-op in JSON mode.

```
┌─ Step 1/11 · Select block model ───────────────────────────────┐
│  Choose which block model you want to create a report for.     │
│                                                                 │
│    1)  Copper Main Pit             (bbbbbbbb-0000-…-0001)      │
│    2)  Gold Underground Zone A     (bbbbbbbb-0000-…-0002)      │
│    3)  Iron Ore Stage 2            (bbbbbbbb-0000-…-0003)      │
└─────────────────────────────────────────────────────────────────┘
Block model [1]:
```

Summary panel before final API call:

```
┌─ Review your report ───────────────────────────────────────────┐
│  Block model   Copper Main Pit                                  │
│  Name          Gold Resource Report                             │
│  Columns       Au Grade  (MASS_AVERAGE  g/t)                   │
│                Cu        (SUM  %[mass])                        │
│  Category      Domain                                           │
│  Density       2.7 t/m3 (fixed)                                │
│  Mass unit     t                                                │
│  Cutoffs       Au ≥ 0.5, 1.0                                    │
│  Autorun       yes                                              │
│  Run now       yes                                              │
└─────────────────────────────────────────────────────────────────┘
Create this report? [Y/n]:
```

---

## Step sequence (11 steps)

### Step 0 — Pre-flight (automatic, no prompt)

After block model is known:
- `client.list_versions(bm_id)` + `client.get_version(bm_id, versions[0].version_uuid)` →
  builds column catalogue `list[ColumnMeta]`
- `client._units_api.get_units(org_id=...)` → all `UnitInfo` objects for later filtering
- Errors from these calls surface via `_api_error` and abort the wizard.

---

### Step 1 — Select block model *(skipped if `bm_id` given as CLI arg)*

**Panel:** "Choose which block model to create a report for."

**API:** `client.list_block_models(workspace_id=..., org_id=...)` — paginated, fetches
all pages. Shows name + UUID excerpt.

**Prompt:** `Block model [1]:` — numbered single-select.

After selection, run Step 0 (pre-flight) silently.

---

### Step 2 — Report name *(skipped if `--name` given)*

**Panel:** "Give your report a descriptive name."

**Prompt:** `Report name:` — non-empty string, loops on blank.

---

### Step 3 — Value columns *(skipped if any `--column` flag given)*

**Panel heading:** "Step 3 · Value columns"

**Explanation:**
> Select which numeric block model columns to aggregate into the report.
> Each column produces one result column in the output table.

**Body:** Numbered list of numeric columns (Float64, Int64; excludes CATEGORY-typed).
Shows title + native unit.

**Prompt:** `Column numbers (comma-separated):` — at least one required, loops on invalid.

For each selected column, three sub-prompts:

**3a. Label**
```
Label for "Au" [Au]:
```
Enter to keep default.

**3b. Aggregation**
```
Aggregation for "Au":
  1) MASS_AVERAGE  – weighted mean per unit mass; use for grade (g/t, %, ppm)
  2) SUM           – direct sum; use for absolute quantities (metal kg, contained oz)
Choice [1]:
```

**3c. Output unit** (optional)
Shows units whose `unit_type` matches the column's native unit type, plus "keep native".
```
Output unit for "Au":
  1) g/t           (keep native)
  2) oz t/ton      troy ounces per short ton
  3) ppm[mass]     parts per million
  …
Choice [1 – keep native]:
```

---

### Step 4 — Category columns *(skipped if any `--category` flag given)*

**Panel:** "A category column splits results by domain value (e.g. ore type, lithology).
Up to 5 categories are supported."

**Body:** All columns, including category/string typed.

**Prompt:** `Category column numbers (0 to skip) [0]:` — optional, max 5.

For each selected: `Label for "{title}" [{title}]:` — optional override.

---

### Step 5 — Density *(skipped if any `--density-*` flag given)*

**Panel explanation:**
> Density converts block volume to mass. A column reads density per block (most accurate
> when density varies). A fixed value applies one number to all blocks.

```
  1) Density column  – block-by-block values (most accurate)
  2) Fixed value     – single value for all blocks
  3) Both            – column with fixed fallback for blocks with no value
Choice [1]:
```

**If column (1 or 3):** numbered list of MASS_PER_VOLUME columns.
`Density column:`

**If fixed (2 or 3):**
`Density value (e.g. 2.7):` — float, loops on parse error.
Then show MASS_PER_VOLUME unit list.
`Density unit:`

---

### Step 6 — Mass unit *(skipped if `--mass-unit` given)*

**Panel:** "The mass unit controls how tonnage is displayed. t (tonnes) is standard at
mine scale; kt or Mt for large deposits."

**Body:** Numbered list of all MASS units from the API (symbol + description).

**Prompt:** `Mass unit [t]:` — defaults to `t`.

---

### Step 7 — Cutoff thresholds *(skipped if `--cutoff-column` or `--cutoff` given)*

**Panel explanation:**
> Cutoffs define minimum grade thresholds. Each cutoff produces a separate result block
> showing only material at or above that grade. Typical set: 0.0, 0.5, 1.0, 2.0.

**Prompt:** `Set cutoff thresholds? [y/N]:` — optional.

If yes:
- Numbered list of numeric columns. `Cutoff column:`
- `Cutoff values (space or comma-separated, e.g. 0 0.5 1.0):`

---

### Step 8 — Autorun *(skipped if `--autorun`/`--no-autorun` given)*

**Panel explanation:**
> Autorun triggers a new reporting job whenever a block model version is published,
> keeping results current automatically.

**Prompt:** `Enable autorun? [Y/n]:`

---

### Step 9 — Run now *(skipped if `--run-now`/`--no-run-now` given)*

**Panel:** "Run the report against the latest version immediately after creating."

**Prompt:** `Run report now? [Y/n]:`

---

### Step 10 — Summary + confirm

Show the Review panel (see Visual style above).
`Create this report? [Y/n]:`

- Yes → call the existing `_do_create` with collected params, show result.
- No → print `Aborted.` exit 0.

---

## Implementation files

| Action | File |
|--------|------|
| Modify | `packages/evo-cli/src/evo/cli/output.py` — add `emit_panel(title, body_lines, *, width=68)` |
| Create | `packages/evo-cli/src/evo/cli/blockmodels/interactive.py` — `InteractiveReportWizard` class |
| Modify | `packages/evo-cli/src/evo/cli/blockmodels/reports.py` — `bm_id` optional in `create`/`update`, add `--interactive` flag |
| Create | `packages/evo-cli/tests/blockmodels/interactive.py` — wizard tests |

---

## `InteractiveReportWizard` interface

```python
class InteractiveReportWizard:
    def __init__(
        self,
        client: BlockModelAPIClient,
        env: Environment,
        *,
        bm_id: str | None = None,    # pre-set if given on CLI
    ): ...

    async def run(
        self,
        *,
        name: str | None = None,
        columns: list[str] | None = None,
        categories: list[str] | None = None,
        mass_unit: str | None = None,
        density_column: str | None = None,
        density_value: float | None = None,
        density_unit: str | None = None,
        cutoff_column: str | None = None,
        cutoffs: list[float] | None = None,
        autorun: bool | None = None,
        run_now: bool | None = None,
    ) -> dict:   # kwargs for _do_create/_do_update
```

Pre-filled values skip their steps. The wizard returns a dict; `reports.py` passes it
to the existing `_do_create`/`_do_update` unchanged.

---

## Tests (`tests/blockmodels/interactive.py`)

Use `CliRunner(mix_stderr=False)` with `input=` to pipe answers.
Mock: `list_block_models`, `list_versions`, `get_version`, `_units_api.get_units`,
`_reports_api.create_report_specification`.

| Test | What it checks |
|------|---------------|
| `test_bm_id_selection_when_not_provided` | Step 1 shown, selecting [1] sets bm_id |
| `test_bm_id_skipped_when_provided_as_arg` | Step 1 absent in output |
| `test_happy_path_creates_report` | Full piped input, exit 0, API called once |
| `test_name_skipped_when_flag_given` | `--name X` → name panel absent |
| `test_column_step_skipped_when_flag_given` | `--column X:SUM` → column panel absent |
| `test_invalid_column_number_reloops` | Pipe "99\n1\n…" → "Invalid" line, re-prompted |
| `test_density_column_path` | Choice 1 → density_col_id set, value/unit None |
| `test_density_value_path` | Choice 2 → density_value + unit set, col_id None |
| `test_no_cutoffs` | Answer "n" → cutoff_col_id=None, cutoff_values=[] |
| `test_abort_on_confirm_no` | Answer "n" at summary → API not called, exit 0 |
| `test_autorun_disabled` | Answer "n" to autorun → autorun=False in API call |
| `test_run_now_triggers_job` | Answer "y" → run_reporting_job called |
| `test_json_mode_exits_before_wizard` | `--format json --interactive` → error + exit |
| `test_emit_panel_format` | Unit-test `emit_panel` directly: ┌/└/│ lines |

---

## Status

**Status: PLANNED** — not yet implemented.
