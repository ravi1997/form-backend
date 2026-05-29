# Frontend vs Backend Evidence Matrix for Form Builder and Preview

This matrix is evidence-only. Every row is backed by repository files and line references.

## Scope
- Frontend builder widgets
- Frontend preview page
- Backend model and schema layer
- Backend normalization and metadata surfaces

## Core Question Model

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Field type | `FormQuestion` is used by the builder UI, and the UI reads `widget.question.type` as a `QuestionType` enum. See [field_general_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L12-L17) and [field_general_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L170-L208). | Backend `Question` stores `field_type` as a string and has no `type` field. See [models/Form.py](../models/Form.py#L132-L137). | Mismatch |
| Required | Builder validation panel writes `isRequired` and `copyWith(isRequired: val)`. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L129-L137). | Backend `Validation` stores `is_required`. See [models/Form.py](../models/Form.py#L58-L68). | Mismatch in shape |
| Min/max length | Builder validation panel writes `minLength` / `maxLength`. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L158-L183). | Backend `Validation` stores `min_length` / `max_length`. See [models/Form.py](../models/Form.py#L58-L68). | Mismatch in shape |
| Regex | Builder validation panel writes `validationRegex`. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L303-L327). | Backend `Validation` stores `regex`. See [models/Form.py](../models/Form.py#L58-L68). | Mismatch in shape |
| Input mask | Builder validation panel writes `inputMask`. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L280-L299). | Backend `Validation` stores `input_mask`. See [models/Form.py](../models/Form.py#L58-L68). | Mismatch in shape |
| Date bounds | Builder validation panel writes `dateMin` / `dateMax`. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L334-L340) and [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L684-L698). | Backend `Validation` stores `date_min` / `date_max`. See [models/Form.py](../models/Form.py#L58-L68). | Mismatch in shape |
| Repeatability | Builder uses `isRepeatable`, `repeatMin`, `repeatMax`. See [field_general_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L81-L124) and [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L228-L239). | Backend `Question` stores `is_repeatable`, `repeat_min`, `repeat_max`. See [models/Form.py](../models/Form.py#L145-L148). | Naming mismatch |
| Hidden/read only | Builder uses `isHidden` and `isReadOnly`. See [field_general_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L81-L124). | Backend `Question` stores `is_hidden` and `is_read_only`. See [models/Form.py](../models/Form.py#L150-L152). | Naming mismatch |
| Metadata | Builder still reads `metadata` and values inside it, such as `defaultValue` and `dividerText`. See [field_general_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_general_settings.dart#L44-L72). | Backend `Question` stores `meta_data`. See [models/Form.py](../models/Form.py#L161-L162). | Naming mismatch |

## Style and UI

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Question style | Preview uses `widget.question.style`, including `labelColor`, `helperColor`, `prefixIcon`, `suffixIcon`, and other style fields. See [form_preview_page.dart](../lib/features/form_builder/presentation/pages/form_preview_page.dart#L1578-L1764) and [form_preview_page.dart](../lib/features/form_builder/presentation/pages/form_preview_page.dart#L2741-L2746). | Backend `Question` stores `ui` as an embedded `QuestionUI`, not a direct `style` object. See [models/Form.py](../models/Form.py#L154-L156). | Mismatch in representation |
| Section style | Builder section styling writes `section.style` and `section.metaData`. See [section_style_settings.dart](../lib/features/form_builder/presentation/widgets/properties/section_style_settings.dart#L23-L28). | Backend `Section` stores `style` as a `DictField`. See [models/Form.py](../models/Form.py#L229-L234). | Partial alignment, but frontend and backend names differ in surrounding model layer |

## Sections and Nesting

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Nested sections | Frontend `Section` model stores `sections` inline. See [lib/models/form_models.dart](../lib/models/form_models.dart#L57-L82). Preview renders nested structures from the section tree. See [form_preview_page.dart](../lib/features/form_builder/presentation/pages/form_preview_page.dart#L614-L737). | Backend `Section` stores `sections` as `ListField(ReferenceField("self"))` and validates tree depth. See [models/Form.py](../models/Form.py#L236-L256). | Structural mismatch |
| Section normalization | Frontend builder sends camelCase/legacy variants in section widgets. See [section_logic_settings.dart](../lib/features/form_builder/presentation/widgets/properties/section_logic_settings.dart#L95-L238) and [section_style_settings.dart](../lib/features/form_builder/presentation/widgets/properties/section_style_settings.dart#L23-L28). | Backend normalizes `gridColumns`, `isHidden`, `isRepeatable`, `repeatMin`, `repeatMax`, `conditionalLogic`, `helpText`, `responseTemplates`, and `metaData`. See [services/section_service.py](../services/section_service.py#L55-L130). | Backend compatibility exists, but frontend and backend are not using the same canonical shape |

## Forms, Project Scope, and Workflow

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Form scope | Frontend `Form` model includes `organizationId`, `createdBy`, `uiType`, `activeVersion`, `versions`, `workflows`, `accessPolicy`, and `style`. See [lib/models/form_models.dart](../lib/models/form_models.dart#L106-L136). | Backend `Form` includes `organization_id`, `created_by`, `project`, `ui_type`, `active_version`, `head_commit_id`, `active_publish_commit_id`, `branches`, `editors`, `viewers`, `submitters`, `approval_enabled`, `workflows`, `access_policy`, `response_templates`, and `triggers`. See [models/Form.py](../models/Form.py#L293-L343). | Partial alignment |
| Project scope | Frontend local form model does not expose project relations directly. See [lib/models/form_models.dart](../lib/models/form_models.dart#L106-L136). | Backend `Form` has `project`, and backend `Project` has `forms`, `sub_projects`, `active_version`, and `triggers`. See [models/Form.py](../models/Form.py#L313-L343) and [models/Form.py](../models/Form.py#L404-L417). | Gap |
| Workflow / triggers metadata | Frontend local model exposes `workflows`, but the builder widgets shown here do not demonstrate a contract-aware editor tied to backend trigger structures. | Backend `Form` and `Project` store `triggers`, and builder metadata exposes trigger enums. See [models/Form.py](../models/Form.py#L341-L343), [models/Form.py](../models/Form.py#L416-L417), and [routes/v1/builder_metadata_route.py](../routes/v1/builder_metadata_route.py#L34-L43). | Backend support exists; builder surface is incomplete in the examined widgets |
| Approval/access policy | Frontend local model exposes `accessPolicy`. See [lib/models/form_models.dart](../lib/models/form_models.dart#L132-L135). | Backend `Form` stores `approval_enabled` and `access_policy`, and backend schemas include `access_policy`. See [models/Form.py](../models/Form.py#L338-L343) and [schemas/form.py](../schemas/form.py#L216-L228). | Partial alignment |

## Validation and Conditional Logic

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Validation schema | Frontend properties write validation fields directly on the old `FormQuestion` entity. See [field_validation_settings.dart](../lib/features/form_builder/presentation/widgets/properties/field_validation_settings.dart#L129-L327). | Backend validation is structured as `Validation` with `is_required`, `min_length`, `max_length`, `min_value`, `max_value`, `regex`, `error_message`, `date_min`, `date_max`, `disable_*`, file rules, selection rules, and `custom_validations`. See [models/Form.py](../models/Form.py#L58-L68). | Shape mismatch |
| Conditional logic | Builder logic panel uses `conditionalLogic` on section widgets. See [section_logic_settings.dart](../lib/features/form_builder/presentation/widgets/properties/section_logic_settings.dart#L95-L238). | Backend `Section` has `conditional_logic`, and backend `LogicComponentSchema` exposes `conditional_logic` and `triggers`. See [models/Form.py](../models/Form.py#L229-L234) and [schemas/components.py](../schemas/components.py#L89-L102). | Naming mismatch but concept exists |
| Logic evaluation surface | Frontend has a local logic evaluator service. See [form_logic_evaluator.dart](../lib/features/form_builder/domain/services/form_logic_evaluator.dart#L1-L105). | Backend has `form_validation_service.py` and `hook_service.py` for validation and trigger execution. See [services/form_validation_service.py](../services/form_validation_service.py#L1-L497) and [services/hook_service.py](../services/hook_service.py#L1-L160). | Different enforcement layers |

## Builder Metadata and Generated API

| Area | Frontend evidence | Backend evidence | Result |
|---|---|---|---|
| Builder metadata | No direct evidence in the examined widgets that they consume `/builder-metadata`. | Backend exposes `/builder-metadata` with field types, UI types, condition operators, trigger enums, access levels, validation groups, and languages. See [routes/v1/builder_metadata_route.py](../routes/v1/builder_metadata_route.py#L24-L76). | Backend surface exists; frontend consumption not proven in the examined files |
| Generated contract models | Generated `QuestionSchema`, `SectionSchemaStruct`, and `FormSchema` reflect backend names such as `field_type`, `validation`, `logic`, `ui`, `response_templates`, `sections`, `active_version`, `approval_enabled`, `triggers`, and `is_deleted`. See [question_schema.dart](../lib/generated/api/lib/src/model/question_schema.dart#L19-L66), [section_schema_struct.dart](../lib/generated/api/lib/src/model/section_schema_struct.dart#L19-L50), and [form_schema.dart](../lib/generated/api/lib/src/model/form_schema.dart#L19-L78). | Backend schemas contain the same core names. See [schemas/form.py](../schemas/form.py#L88-L228). | Stronger alignment at generated API layer than at local builder widget layer |

## Evidence-Based Conclusions

1. The local builder widgets and preview page are still wired to an older `FormQuestion`/`QuestionType` surface.
2. The backend model and schema layers already support the major concept set: questions, sections, forms, versions, project scope, workflows, access policy, and validation logic.
3. The backend also already has compatibility normalization for legacy/camelCase payloads.
4. The generated Dart API models are much closer to backend schema names than the hand-authored form builder model layer.
5. The most obvious break risk is not the backend missing data. The break risk is inconsistent frontend contract usage across:
   - builder widgets,
   - preview rendering,
   - local form models,
   - and generated API schemas.

## Recommended Next Step
If you want the form-builder and preview page to work for all questions, properties, internal sections, project scopes, workflows, validation logic, and conditions, the next step should be a contract consolidation pass:

- choose one canonical frontend model surface for builder/preview,
- map every widget to that model only,
- and preserve the backend normalization rules where legacy payloads still exist.

