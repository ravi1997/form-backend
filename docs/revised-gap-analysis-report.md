# Gap Analysis and Architecture Review for RIDP Form Builder

## Scope
This report corrects the original analysis by separating:
- verified backend/frontend drift,
- claims that are not supported by the current codebase,
- and the architectural direction captured from the grill-me session.

I verified the backend model layer and the frontend builder widgets against the repository state, so the findings below are grounded in actual code rather than inferred from the original write-up.

## Executive Summary
The original gap analysis is directionally useful, but it contains several factual errors and overreaches:

- It claims multiple backend fields are missing from the models when they already exist.
- It proposes a new dynamic schema API even though the backend already exposes builder metadata and already normalizes several legacy request shapes.
- It correctly identifies frontend drift in the form builder properties widgets, but it misattributes some of that drift to backend schema changes instead of stale UI code.
- It does not account for the broader legacy builder layer, which still appears to depend on older question entity abstractions.

The real problem is not “the backend model no longer matches the frontend model” in a blanket sense. The real problem is:
- the builder UI is partially still wired to older field names and behavior,
- the backend already has compatibility and normalization logic that the UI is ignoring,
- and the project needs a contract-aware migration plan, not a parallel schema system built in isolation.

## Corrected Model Alignment

### Question
Verified backend fields in [models/Form.py](../models/Form.py#L132):
- `label`
- `field_type`
- `help_text`
- `default_value`
- `order`
- `variable_name`
- `is_repeatable`
- `repeat_min`
- `repeat_max`
- `keep_last_value`
- `is_hidden`
- `is_read_only`
- `is_sensitive`
- `validation`
- `logic`
- `ui`
- `response_templates`
- `options`
- `matrix_rows`
- `tags`
- `meta_data`

Frontend `Question` in [lib/models/form_models.dart](../../../../frontend/lib/models/form_models.dart#L13):
- uses `fieldType` for `field_type`
- uses `validation`, `logic`, and `ui` as generic maps
- does not model several backend nested documents explicitly

### Section
Verified backend fields in [models/Form.py](../models/Form.py#L211):
- `title`
- `description`
- `help_text`
- `order`
- `layout`
- `grid_columns`
- `is_hidden`
- `is_repeatable`
- `repeat_min`
- `repeat_max`
- `conditional_logic`
- `style`
- `version`
- `logic`
- `ui`
- `questions`
- `sections`
- `response_templates`
- `tags`
- `meta_data`

Frontend `Section` in [lib/models/form_models.dart](../../../../frontend/lib/models/form_models.dart#L57):
- models nested sections inline
- uses `logic` and `ui` as maps
- does not expose some backend-specific references like `version`

### Form
Verified backend fields in [models/Form.py](../models/Form.py#L293):
- `title`
- `slug`
- `organization_id`
- `created_by`
- `project`
- `status`
- `ui_type`
- `active_version`
- `head_commit_id`
- `active_publish_commit_id`
- `branches`
- `description`
- `help_text`
- `expires_at`
- `publish_at`
- `is_template`
- `is_public`
- `supported_languages`
- `default_language`
- `translations`
- `tags`
- `sections`
- `editors`
- `viewers`
- `submitters`
- `approval_enabled`
- `style`
- `workflows`
- `access_policy`
- `response_templates`
- `triggers`

Frontend `Form` in [lib/models/form_models.dart](../../../../frontend/lib/models/form_models.dart#L106):
- covers the core form payload reasonably well
- represents `activeVersion` as a string instead of a version reference
- does not expose the versioning and commit bookkeeping fields
- does not model ACL lists as strongly as the backend does

### FormVersion
Verified backend fields in [models/Form.py](../models/Form.py#L460):
- `form`
- `version`
- `snapshot_ref`
- `translations`
- `access_policy`
- `status`

Frontend `FormVersion` in [lib/models/form_models.dart](../../../../frontend/lib/models/form_models.dart#L87):
- represents `version` as a string
- stores `sections` inline
- omits `form`, `snapshot_ref`, and some snapshot-related behavior

## Verified UI Drift

The frontend properties widgets in `lib/features/form_builder/presentation/widgets/properties/` still use older assumptions.

### Field General Settings
In [field_general_settings.dart](../../../../frontend/lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L510), the UI still references:
- `actionConfig`
- `customErrorMessage`
- `validationRegex`
- `inputMask`
- `minLength`
- `maxLength`
- `minWordCount`
- `maxWordCount`
- `minValue`
- `maxValue`

These do not exist as direct fields in [lib/models/form_models.dart](../../../../frontend/lib/models/form_models.dart#L13). They are either now expected inside maps like `validation`, `logic`, or `ui`, or they belong to older entity abstractions.

### Field Validation Settings
In [field_validation_settings.dart](../../../../frontend/lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L129), the UI still writes to:
- `isRequired`
- `customErrorMessage`
- `minLength`
- `maxLength`
- `minWordCount`
- `maxWordCount`
- `minValue`
- `maxValue`
- `inputMask`
- `validationRegex`

Some of those are compatible at the frontend model level, but several are not aligned with the backend’s nested validation structure.

### Field Style Settings
In [field_style_settings.dart](../../../../frontend/lib/features/form_builder/presentation/widgets/properties/field_style_settings.dart#L398), icon styling still assumes nested style object behavior in the builder UI. The new frontend model uses a generic `ui` map instead, so this area needs explicit mapping logic.

## Backend Compatibility That the Original Report Missed

The backend already contains normalization behavior that should be preserved rather than bypassed:

- [services/section_service.py](../services/section_service.py#L1) normalizes camelCase and legacy aliases into backend field names.
- It maps legacy payloads like `gridColumns`, `isHidden`, `conditionalLogic`, `responseTemplates`, and `required`.
- It also syncs `layout` into `ui.layout_type` for compatibility.

This is important because a fully dynamic schema editor that writes raw maps directly will need to honor the same normalization rules, or it will regress existing clients.

The backend also already exposes dynamic builder metadata in [routes/v1/builder_metadata_route.py](../routes/v1/builder_metadata_route.py#L1), which means the report’s proposed `/schemas/questions/{question_type}` API is not the only possible approach and should not be presented as if it already fits the project direction.

## Grill-Me Session Details
The original report includes a grill-me alignment section. Those decisions should be preserved, but they need to be framed as product/architecture intent rather than as verified implementation state.

### Captured Decisions
1. **Model schema alignment**
- Selected direction: dynamic schema-driven property binding
- Intent: use dynamic maps such as `validation`, `ui`, and `logic`

2. **UI rendering strategy**
- Selected direction: fully schema-driven UI generation
- Intent: generate controls from a schema rather than hardcoding every property panel

3. **Schema registry location**
- Selected direction: backend schema API
- Intent: allow server-side CRUD and centralized schema updates

4. **Loading/offline behavior**
- Selected direction: strict API dependency with shimmer loading
- Intent: prefer synchronization over local fallback

5. **Complex value editing**
- Selected direction: inline dynamic card lists
- Intent: avoid modal interruptions for complex nested inputs

### Important Caveat
These grill-me outcomes are architectural choices, not evidence that the repository currently implements them. The codebase still shows a hybrid state:
- some dynamic map support exists,
- some legacy property widgets remain,
- and some builder code still depends on older model abstractions.

So the grill-me session should be presented as the desired future architecture, not as the current implementation baseline.

## Problems and Issues

### 1. The report overstates backend missing fields
Several fields marked as missing are already present in the backend model layer.

Impact:
- produces false positives
- obscures real contract drift
- can send implementation effort in the wrong direction

### 2. The report proposes a new schema source of truth without reconciling existing metadata
The backend already has `builder-metadata` and several normalization paths.

Impact:
- risk of duplicate schema systems
- risk of divergence between builder metadata, API schema, and persisted form data

### 3. The builder UI still uses legacy property names
The properties widgets are not fully aligned to the new frontend model or backend nesting.

Impact:
- broken updates
- zombie inputs
- state loss on edit/save cycles
- partial serialization failures

### 4. The frontend builder likely has deeper legacy coupling
The builder service layer still imports older question entity abstractions, which suggests the properties panel is not the only stale layer.

Impact:
- fixing only the visible properties widgets will likely leave hidden breakpoints in the builder pipeline

### 5. The analysis does not distinguish between editable form design data and internal backend bookkeeping
Fields like `head_commit_id`, `active_publish_commit_id`, and `branches` are backend lifecycle fields, not necessarily UI-editable design controls.

Impact:
- the report incorrectly treats internal persistence fields as UI gaps
- this can lead to unnecessary frontend surface area

## Recommended Revised Direction
1. Keep the backend’s existing normalization behavior.
2. Treat `builder-metadata` as the current dynamic capability surface unless there is a strong reason to add a new schema API.
3. Fix the properties widgets so they read/write the current frontend model shape correctly.
4. Add compatibility adapters for legacy field names where needed.
5. Only introduce a richer schema registry if the project can define one canonical source of truth across backend, frontend, and generated clients.

## What To Remove From the Original Report
The following claims should be removed or rewritten:
- “These backend fields are missing from the model” for fields that already exist.
- “The backend does not expose dynamic metadata” because it already does.
- “The UI and backend are fully incompatible” because the system is in a mixed compatibility state, not a total mismatch.
- “The new schema CRUD API is the obvious solution” because it is a design proposal, not a verified need.

## Bottom Line
The real defect is not that the backend and frontend are completely out of sync. The real defect is that the form builder is in an in-between state:
- the backend already supports more structure than the report acknowledges,
- the frontend properties widgets still assume older per-field APIs,
- and the architecture discussion needs to be grounded in the actual normalization and metadata surfaces already present in the project.

If you want, I can turn this into one of these next:
1. a polished markdown document ready to paste into your repo,
2. a shorter executive-summary version,
3. or a stricter issue list with severity and file references only.
