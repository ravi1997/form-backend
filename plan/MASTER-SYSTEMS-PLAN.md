# RIDP Form Platform: Canonical Master Systems Plan

**Document Version:** 1.0  
**Status:** APPROVED & ACTIVE  
**Updated:** 2026-05-26  

This document serves as the high-level canonical specification and step-by-step master plan for the three core separate systems of the RIDP Form Platform. It incorporates the current status, alignments, gap remediations, and complete database/service specifications to serve as the unified source of truth for both backend and frontend repositories.

---

## 1. Executive Summary & Repository Context

The RIDP Form Platform is a multi-tenant platform designed to manage forms, dashboards, and analytical calculations securely and responsively. It is partitioned into three separate systems:
1. **Form Builder & Submission System**: Structure layout, versioned schema definitions, and secure validated submissions.
2. **Dashboard Builder & Response Viewer**: Layout customization, aggregated widgets rendering, response grid viewing, and advanced filters.
3. **Analysis Board Builder**: A modular mathematical playground allowing researchers to wire calculation aspects (nodes) using predefined aggregate, statistical, and semantic formulas over form data.

### Architectural Hard Invariants
- **Multi-Tenancy**: The database must isolate all operations by `organization_id`. Server-side tenant scope is mandatory. Global overrides are only allowed for the `superadmin` role.
- **Data Integrity**: Soft deletes are enforced via `is_deleted=True` for forms, dashboards, and analysis boards.
- **REST Envelope Policies**: All endpoints must return standard response structures:
  - Success: `{"success": true, "data": DTO_PAYLOAD}`
  - Error: `{"success": false, "message": "REASON_STRING", "details": {...}}`
- **Pydantic V2 Enforcement**: Every backend route must deserialize payloads using strict Pydantic models.
- **Dart Client Generation**: Generated DTOs under `lib/generated/api/` are read-only and must be compiled automatically from the backend OpenAPI schema.

---

## 2. System 1: Form Builder & Submission System

### System Scope
A visual form editor capable of laying out multi-section, smart-grid forms that generate schema-driven JSON targets, paired with a public/private submission handler that validates inputs, repeat structures, cascading dropdown restrictions, and calculated fields.

### Current Implementation Status
* **Backend Models**: `models/Form.py` (complete versioning support, metadata snapshot, status flows), `models/components.py` (sections, fields, layouts), `models/Response.py` (individual submissions).
* **Backend Services**: `FormValidationService` (multi-level repeat validation limits, dependency-cycle detection, cascading selects constraint verification), `ConditionEvaluator` (advanced Python evaluation engine for calculated expressions).
* **Backend Routes**: `routes/v1/form/form.py` (form CRUD), `routes/v1/form/validation.py`, `routes/v1/form/responses.py` (individual and public submit endpoints).
* **Frontend UI**: `lib/features/form_builder/` (dynamic form canvas, field properties pane, sections manager, drag-and-drop primitives).
* **Frontend Submissions**: `lib/features/responses/` (response capture, form rendering widgets, reactive validation, cascading select controller).

---

### Step-by-Step Implementation Details

```
   Step 1.1: Separated Grid Canvas   ──>   Step 1.2: Public Secure Submit   ──>   Step 1.3: Calculation Evaluator
 (Flex / Grid uiType & auto-spans)       (No Auth token, scheduled bounds)        (Prevent client-tampering)
```

#### Step 1.1: Frontend Smart Grid & Responsive Layout Separation
- **Description**: Separate form-level structures (`form.uiType` / `ui_type`) from section-specific canvas structures (`section.layout`), ensuring manual/automatic grid spans are fully responsive across web and mobile viewports.
- **Tasks**:
  1. **UI Canvas Update**: In `lib/features/form_builder/presentation/widgets/canvas_grid.dart`, build a responsive column layout mapping sections to grid cells based on `FieldSpan` parameters (1 to 12 columns).
  2. **JSON Schema Mapping**: Align the generated frontend model with the backend components representation of sections, validating that width properties are stored accurately.
- **Verification**: Run Flutter responsiveness tests; verify container sizing on desktop and mobile viewports.

#### Step 1.2: Public Submission Engine Hardening
- **Description**: Enable complete anonymous submission support for forms flagged as public and active, rejecting late submissions, and preventing duplicate processing.
- **Tasks**:
  1. **Anonymous Endpoint**: Route `POST /form/api/v1/forms/public/submit` must bypass JWT interceptors. Derive `organization_id` strictly from the requested form itself to ensure tenant context.
  2. **Time Window Checks**: Validate current UTC time falls between form version's `scheduled_start` and `scheduled_end` keys.
  3. **Idempotency Guard**: Require a client-generated `Idempotency-Key` header. Cache the key along with response status in Redis for 24 hours. If re-submitted, return the cached result instead of writing a new document.
- **Verification**: Run integration tests under `tests/test_idempotency.py` to ensure request replays bypass write layers and return identical responses.

#### Step 1.3: Advanced Calculation Engine & Cascading Select Validation
- **Description**: Harden validation logic during responses submission to ensure dynamic calculation fields are evaluated on the server-side, blocking illegal payloads.
- **Tasks**:
  1. **Calculated Field Recalculation**: During response ingestion in `FormValidationService`, identify all calculated questions in the form version snapshot. Run `ConditionEvaluator` over the payload values and compare results against the submitted values. If a discrepancy is found, reject the payload with a `400 Validation Error`.
  2. **Cascading Dropdowns Validation**: If Question B's list options are filtered by selected value in A, verify that the submitted value for B matches one of the allowed choices listed under the selected parent A choice in the form schema.
- **Verification**: Run `test_form_refactor.py` and `test_hardening.py` to verify calculated evaluation chains.

---

## 3. System 2: Dashboard Builder & Response Viewer

### System Scope
A visual dashboard layouts customizer populated by modular aggregation widgets (line, bar, pie charts, counter KPIs, and data list tables) paired with a high-throughput response browser supporting compound filters.

### Current Implementation Status
* **Backend Models**: `models/Dashboard.py` (complete Dashboard model and layout schemes, embedded `DashboardWidget` specification, `UserDashboardSettings` registry).
* **Backend Services**: `DashboardService` (dashboard CRUD), high-performance aggregation runner `resolve_widget_data` using native MongoDB `$group` and arithmetic operators (`$sum`, `$avg`, `$min`, `$max`).
* **Backend Routes**: `routes/v1/dashboard_route.py` (CRUD routes with dynamic widget calculations), `routes/v1/dashboard_settings_route.py` (user preferences).
* **Frontend UI**: `lib/features/dashboard/` (dashboard grid layout, drag-and-drop positioning, widget settings sidebar, charts integration with FL Chart/Syncfusion).

---

### Step-by-Step Implementation Details

```
   Step 2.1: Mongo Aggregation Opt   ──>   Step 2.2: Advanced Filter Builder   ──>   Step 2.3: Audited Grid Details
 (Index pre-filtering & pipeline limits)      (Visual multi-field compound filters)     (Infinite scroll & secure audit logs)
```

#### Step 2.1: High-Performance Widget Aggregation Optimizations
- **Description**: Speed up widget data calculations under large scales, eliminating Python-side calculation loops and utilizing optimized database lookups.
- **Tasks**:
  1. **Composite Indexes**: Declare optimized composite indexes on the `form_responses` collection:
     `{ form: 1, is_deleted: 1, organization_id: 1, "data.question_id": 1 }`.
  2. **Aggregation Pruning**: In `resolve_widget_data()`, execute matching filters before running pipeline groupings. Enforce projection clauses to pull only targeted mathematical columns, saving database memory.
- **Verification**: Run performance benchmarker with 5 widgets over 500,000 mocked responses; assert rendering latency stays below 300ms.

#### Step 2.2: Advanced Filter Builder Engine
- **Description**: Empower admins to build complex queries combining multiple conditions (equality, comparison, logical operators) visually.
- **Tasks**:
  1. **Query Parser**: Implement a secure query compiler in `DashboardService` converting filter arrays (`[ { "field": "q-1", "operator": "equals", "value": "Male" }, { "field": "q-2", "operator": "gt", "value": 25 } ]`) into isolated MongoDB query dictionaries.
  2. **Filter Dialog UI**: Design a unified filter model in Flutter loading fields dynamically depending on form type, enabling text, numerical, boolean, and date comparisons.
- **Verification**: Write unit tests for the filter parser asserting security bounds, blocking arbitrary database scripts injections.

#### Step 2.3: Grid Visualization and Audited Response Detail Viewer
- **Description**: Virtualized interactive table showing form submissions mapped to schemas, fully audited for regulatory compliance.
- **Tasks**:
  1. **Response List Grid**: Build a virtualized infinite scroll grid in Flutter displaying question labels as columns. Supports dynamic sorting, column toggles, and Excel/CSV download hooks.
  2. **View Access Audit**: In the response detail controller, when an admin retrieves a submission, dispatch a background event via `audit_logger` recording user ID, response ID, tenant context, and date.
- **Verification**: Check MongoDB `AuditLog` collection to verify secure trace logs exist for every response lookup.

---

## 4. System 3: Analysis Board Builder

### System Scope
A specialized visual calculation board editor. Unlike basic dashboards, the Analysis Board Builder allows researchers to wire separate calculation cards (nodes) together, applying predefined arithmetic, statistical, and text analytics formulas to evaluate complex ratios, variances, and correlations across responses.

### Predefined Functions Specification

The mathematical core of System 3 must support the following predefined aspect functions:

| Function ID | Category | Mathematical Equation | Description / Input |
| :--- | :--- | :--- | :--- |
| `SUM` | Basic Aggregate | $S = \sum_{i=1}^N x_i$ | Sums values of a target numerical field. |
| `COUNT` | Basic Aggregate | $C = \sum 1$ | Counts submissions matching node filters. |
| `AVERAGE` | Basic Aggregate | $\mu = \frac{1}{N}\sum x_i$ | Computes average of numerical inputs. |
| `MIN` / `MAX` | Basic Aggregate | $\min(X)$ / $\max(X)$ | Identifies peak values in numerical series. |
| `PERCENT` | Ratio | $P = \frac{C_{\text{segment}}}{C_{\text{total}}} \times 100$| Proportion of matching segment over total. |
| `STD_DEV` | Statistical | $\sigma = \sqrt{\frac{\sum (x_i - \mu)^2}{N}}$ | Population standard deviation of numeric data. |
| `RATIO` | Calculation | $R = \frac{V_A}{V_B}$ | Divides value A by B. Safe-handles $V_B = 0$ by returning `null`. |
| `DIFFERENCE`| Calculation | $D = V_A - V_B$ | Net difference between two calculated aspects. |
| `CORRELATION`| Stat Correlation| $r = \frac{N\sum XY - \sum X\sum Y}{\sqrt{[N\sum X^2 - (\sum X)^2][N\sum Y^2 - (\sum Y)^2]}}$ | Pearson Correlation coefficient between two numeric fields. |
| `FREQ_DIST` | Semantic | Frequency mapping | Token occurrences counter for text questions. |

---

### Step-by-Step Implementation Details

```
   Step 3.1: Schemas & Models   ──>   Step 3.2: Aggregation Service   ──>   Step 3.3: REST & OpenAPI Routes   ──>   Step 3.4: Visual Canvas UI
 (AnalysisBoard & Node objects)        (Custom optimized MongoDB facets)      (OpenAPI annotations & Dart DTOs)     (Flutter nodes canvas layout)
```

#### Step 3.1: Define Database Models & Pydantic Schemas
- **Description**: Declare the database structures for Analysis Boards and nodes.
- **Tasks**:
  1. **Database Document Model**: In `models/AnalysisBoard.py`, create `AnalysisNode` embedded structures and `AnalysisBoard` base documents. Maintain index bounds by `organization_id` and `project_id`.
  2. **Pydantic Deserializers**: Create `AnalysisBoardCreateSchema` and `AnalysisBoardUpdateSchema` in the backend schemas layer conforming to Pydantic v2 parameters.
- **Verification**: Run unit tests validating schema instantiations, missing properties rejection, and tenant isolation constraints.

#### Step 3.2: Develop Calculation & Aggregation Services
- **Description**: The mathematical calculation heart of System 3, transforming calculation nodes into high-performance MongoDB facets.
- **Tasks**:
  1. **Visual Pipeline Compiler**: In `services/analysis_board_service.py`, build a compiler mapping calculations to database aggregates. Run standard formulas inside a single `$facet` command to optimize throughput. For statistics (`STD_DEV`), use `{"$stdDevPop": "$data.value"}`. For `CORRELATION`, extract mathematical sums ($X, Y, X^2, Y^2, XY$) and resolve the Pearson coefficient formula.
  2. **Redis Result Caching**: Cache computed boards. Evict caches instantly on event notifications of new responses.
- **Verification**: Unit test calculation calculations against static data inputs for all ten predefined functions (SUM through FREQ_DIST).

#### Step 3.3: REST Endpoints & OpenAPI Documentation
- **Description**: Expose secure administration routes and update contracts for client generation.
- **Tasks**:
  1. **CRUD Endpoints**: Implement `POST /projects/{project_id}/analysis-boards`, `GET /projects/{project_id}/analysis-boards`, `GET /projects/{project_id}/analysis-boards/{id}`, `PUT /projects/{project_id}/analysis-boards/{id}`, `DELETE /projects/{project_id}/analysis-boards/{id}` in `routes/v1/analysis_board_route.py`.
  2. **Execution Handler**: Implement `/projects/{project_id}/analysis-boards/{id}/execute` to compile pipelines, query database, and return computed metrics. Protect via `@require_permission("analysis_board", "view")`.
  3. **Contracts Generation**: Run `make openapi` and `make generate-dart-client` to update frontend contracts.
- **Verification**: Inspect compiled OpenAPI specifications for exact validation schemas and response envelopes alignment.

#### Step 3.4: Visual Node Builder Canvas (Frontend UI)
- **Description**: An interactive drag-and-drop workspace where researchers wire formulas together visually.
- **Tasks**:
  1. **Calculation Workspace**: In `lib/features/analytics/presentation/pages/analysis_builder_page.dart`, build an interactive layout canvas displaying calculation nodes as draggable components. Draw connection lines between dependent calculation aspect blocks.
  2. **State Management**: Connect a custom Riverpod notifier to sync local modifications. Dispatch debounced autosaves to the API.
  3. **Node View Renderers**: Integrate FL Chart widgets inside nodes showing distributions, and add smooth animated tickers for numerical aggregation outputs.
- **Verification**: Perform screen-reader accessibility runs and WCAG color contrast evaluations over builder elements.

---

## 5. Summary of Verification Gates

At each milestone, the following three-step verification sequence must be triggered:

1. **Backend Unit Testing**: Run the pytest suite ensuring all tests are green:
   ```bash
   docker compose run --rm backend pytest -v
   ```
2. **Contract Consistency Validation**: Ensure zero OpenAPI schema drift:
   ```bash
   make openapi && make generate-dart-client
   ```
3. **Frontend Diagnostics**: Compile the Flutter workspace with zero lint warnings:
   ```bash
   flutter analyze
   ```
