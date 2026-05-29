# Gap Analysis & Future-Proof Dynamic Schema Plan

This report provides a comprehensive breakdown of structural discrepancies, model gaps, and a dynamic architectural blueprint to make the RIDP Form Platform highly scalable and future-proof.

---

## 1. Executive Summary & Context

The RIDP Form Platform was recently refactored to align the frontend model entities with the Flask/MongoEngine backend models. The old separate models (`FormQuestion`, `FormSection`, `BuilderForm`, `FormVersion`) were deleted and replaced by unified models in [lib/models/form_models.dart](file:///home/ravi/workspace/frontend/lib/models/form_models.dart).

However, the **Form Builder Properties panels** under [lib/features/form_builder/presentation/widgets/properties/](file:///home/ravi/workspace/frontend/lib/features/form_builder/presentation/widgets/properties) were **not** updated to match the new models. Consequently, the UI reads and writes data using outdated variables, leading to state loss, failed serializations, and non-functional configuration tabs (zombie inputs).

---

## 2. Complete Word-to-Word Model Discrepancies & Gaps

Below are the exact mismatches and missing variables between the Frontend Models ([lib/models/form_models.dart](file:///home/ravi/workspace/frontend/lib/models/form_models.dart)) and the Backend Models ([models/Form.py](file:///home/ravi/workspace/docker/apps/form-backend/models/Form.py)).

### A. `Question` Model
* **Frontend:** `Question` class
* **Backend:** `Question` class

| Variable / Field | Status | Detail & Context |
| :--- | :--- | :--- |
| **`is_required`** | ⚠️ **Mismapped / Architectural Difference** | The frontend defines `is_required` as a top-level boolean field (`bool isRequired`). In the backend, `is_required` belongs under the nested `validation` object as part of the `Validation` embedded document. |
| **`is_sensitive`** | ❌ **Missing in Frontend** | Present in the backend to flag FLE/PII protection. |
| **`order`** | ❌ **Missing in Frontend** | Present in the backend to maintain sequential ordering of questions. |
| **`response_templates`** | ❌ **Missing in Frontend** | Present in the backend for custom exports. |
| **`matrix_rows`** | ❌ **Missing in Frontend** | Present in the backend to configure matrix-based fields. |

---

### B. `Section` Model
* **Frontend:** `Section` class
* **Backend:** `Section` class

| Variable / Field | Status | Detail & Context |
| :--- | :--- | :--- |
| **`conditional_logic`** | ❌ **Missing in Frontend** | Present in the backend as a dynamic dictionary for complex conditional rules. |
| **`style`** | ❌ **Missing in Frontend** | Present in the backend for custom visual layout overrides. |
| **`version`** | ❌ **Missing in Frontend** | Present in the backend as a reference field tracking which version this section belongs to. |
| **`response_templates`** | ❌ **Missing in Frontend** | Present in the backend. |
| **`organization_id`** | ❌ **Missing in Frontend** | Since backend `Section` is a standalone collection inheriting from `BaseDocument`, it possesses an automatic tenant partition key `organization_id` which the frontend does not represent. |
| **`is_deleted` & `deleted_at`** | ❌ **Missing in Frontend** | Backend has soft delete capability via `SoftDeleteMixin`. |

---

### C. `Form` Model
* **Frontend:** `Form` class
* **Backend:** `Form` class

| Variable / Field | Status | Detail & Context |
| :--- | :--- | :--- |
| **`project`** | ❌ **Missing in Frontend** | The backend links the Form to a parent Project container using a reference field. |
| **`sections`** | ⚠️ **Architectural Difference** | In the frontend, `sections` is directly nested inside `FormVersion`. In the backend `Form` class, there is a top-level `sections` reference list. |
| **`active_version`** | ⚠️ **Type Mismatch** | The frontend represents it as a nullable string (`String? activeVersion`). The backend represents it as a `ReferenceField(Version)` mapping to a `Version` model object. |
| **`head_commit_id`** | ❌ **Missing in Frontend** | Backend uses this UUID for git-like auditing and snapshots. |
| **`active_publish_commit_id`**| ❌ **Missing in Frontend** | Backend versioning/snapshot controller ID. |
| **`branches`** | ❌ **Missing in Frontend** | Backend tracking for structural version-controlled branch maps. |
| **`translations`** | ❌ **Missing in Frontend** | Backend stores internationalized translation tables on the Form root, whereas the frontend only lists `supported_languages` and `default_language`. |
| **`editors` & `viewers` & `submitters`**| ❌ **Missing in Frontend** | Backend permissions arrays to implement access control list parameters. |
| **`approval_enabled`** | ❌ **Missing in Frontend** | Present in the backend to check whether workflow responses need explicit reviewer approvals. |
| **`triggers`** | ❌ **Missing in Frontend** | Present in the backend for handling event triggers. |

---

### D. `FormVersion` Model
* **Frontend:** `FormVersion` class
* **Backend:** `FormVersion` class

| Variable / Field | Status | Detail & Context |
| :--- | :--- | :--- |
| **`version`** | ⚠️ **Type Mismatch** | The frontend uses `required String version`. The backend represents `version` as a relational model reference: `ReferenceField(Version, required=True)`. |
| **`sections`** | ⚠️ **Architectural Difference** | The frontend treats sections as an inline list directly on the version. The backend delegates actual layout snapshotting to the `snapshot_ref` pointing to `SnapshotStore` to avoid exceeding document limitations. |
| **`form`** | ❌ **Missing in Frontend** | Present in the backend to establish the backwards relation link to the main form document. |
| **`access_policy`** | ❌ **Missing in Frontend** | Present in the backend version snapshot. |

---

## 3. Form Builder UI Properties Panel vs Model Variable Gaps

### A. Field (Question) Properties Mismatches
* **UI Panel Location:** `lib/features/form_builder/presentation/widgets/properties/`
* **Target Model:** `Question`

| Properties Panel Feature | Variable in UI Code | Variable in New Model | Mapping Status & Mismatches |
| :--- | :--- | :--- | :--- |
| **Field Type Selection** | `widget.question.type` | `widget.question.fieldType` | ⚠️ **Mismatched Type:** UI expects `QuestionType` (an enum) but model uses a raw `String fieldType`. |
| **Variable Reference** | `widget.question.variableName` | `widget.question.variableName` | ✅ **Correct** |
| **Visibility Toggle** | `widget.question.isHidden` | `widget.question.isHidden` | ✅ **Correct** |
| **Repetition Switch** | `widget.question.isRepeatable` | `widget.question.isRepeatable` | ✅ **Correct** |
| **Cache Option** | `widget.question.keepLastValue` | `widget.question.keepLastValue` | ✅ **Correct** |
| **Advanced Actions** | `widget.question.actionConfig` | *None* | ❌ **Missing:** `actionConfig` does not exist in the new model. |
| **Validation Option** | `widget.question.isRequired` | `widget.question.isRequired` | ✅ **Correct** (though backend nests this in `validation.is_required`). |
| **Read Only Flag** | `widget.question.isReadOnly` | `widget.question.isReadOnly` | ✅ **Correct** |
| **Min Character Length**| `widget.question.minLength` | `widget.question.validation['min_length']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Max Character Length**| `widget.question.maxLength` | `widget.question.validation['max_length']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Validation Pattern** | `widget.question.validationRegex`| `widget.question.validation['regex']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Min Words** | `widget.question.minWordCount` | `widget.question.validation['min_word_count']`| ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Max Words** | `widget.question.maxWordCount` | `widget.question.validation['max_word_count']`| ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Min Value** | `widget.question.minValue` | `widget.question.validation['min_value']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Max Value** | `widget.question.maxValue` | `widget.question.validation['max_value']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Input Mask String** | `widget.question.inputMask` | `widget.question.validation['input_mask']` | ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Error Message Text** | `widget.question.customErrorMessage`| `widget.question.validation['error_message']`| ❌ **Mismapped:** UI calls direct field, but model nests in validation map. |
| **Prepend Styling Icon** | `widget.question.style.prefixIcon`| `widget.question.ui['prefix_icon']` | ❌ **Mismapped:** UI uses a nested `style` model, new model expects a `Map<String, dynamic> ui`. |
| **Append Styling Icon** | `widget.question.style.suffixIcon`| `widget.question.ui['suffix_icon']` | ❌ **Mismapped:** UI uses a nested `style` model, new model expects a `Map<String, dynamic> ui`. |
| **Logic Configuration** | `widget.question.logic` | `widget.question.logic` | ⚠️ **Mismatched Structure:** UI handles logic via condition lists, model expects a dynamic map. |

### B. Section Properties Mismatches
* **UI Panel Location:** `lib/features/form_builder/presentation/widgets/properties/`
* **Target Model:** `Section`

| Properties Panel Feature | Variable in UI Code | Variable in New Model | Mapping Status & Mismatches |
| :--- | :--- | :--- | :--- |
| **Section Header** | `widget.section.title` | `widget.section.title` | ✅ **Correct** |
| **Section Description** | `widget.section.description` | `widget.section.description` | ✅ **Correct** |
| **Section Layout Grid** | `widget.section.layout` | `widget.section.layout` | ✅ **Correct** |
| **Grid Sizing Width** | `widget.section.gridColumns` | `widget.section.gridColumns` | ✅ **Correct** |
| **Visual Customization**| `widget.section.style` | `widget.section.ui` / `metadata` | ⚠️ **Mismapped:** UI style modifications are not linked to a unified nested style map in the new `Section` model. |
| **Dependency Logic** | `widget.section.logic` | `widget.section.logic` | ⚠️ **Mismatched Structure:** UI handles section logic via condition rules, model expects a dynamic map. |

### C. Form Properties Mismatches
* **UI Panel Location:** `lib/features/form_builder/presentation/widgets/properties/`
* **Target Model:** `Form`

| Properties Panel Feature | Variable in UI Code | Variable in New Model | Mapping Status & Mismatches |
| :--- | :--- | :--- | :--- |
| **Form Title** | `widget.form.title` | `widget.form.title` | ✅ **Correct** |
| **Form Slug** | `widget.form.slug` | `widget.form.slug` | ✅ **Correct** |
| **Form Description** | `widget.form.description` | `widget.form.description` | ✅ **Correct** |
| **Form Rendering Engine**| `widget.form.uiType` | `widget.form.uiType` | ✅ **Correct** |
| **Color styling** | `widget.form.style` | `widget.form.style` | ✅ **Correct** |
| **Approval Flow Chart** | `widget.form.workflows` | `widget.form.workflows` | ✅ **Correct** |
| **Access Rights Policy**| `widget.form.accessPolicy` | `widget.form.accessPolicy` | ✅ **Correct** |

---

## 4. Aligned Design Specifications (Detailed Grill-Me Session)

The following is an exhaustive record of the decisions made during the interactive `/grill-me` alignment interview to establish a unified and scalable architecture for the form platform properties panel:

### Decision 1: Model Schema Alignment
* **Question Asked:** How should we align the frontend Properties widgets with the unified models?
* **Options Considered:**
  * **Option A (Dynamic Schema-Driven - SELECTED):** Bind visual constraints and properties to the dynamic maps (`validation`, `ui`, `logic`) in the `Question` and `Section` models.
  * **Option B (Direct Field Alignment):** Make all validation properties direct fields on the Dart model classes and match them strictly to explicit backend class fields.
* **Architectural Rationale:** The team selected **Option A**. The dynamic schema maps align perfectly with the backend MongoEngine dynamic documents and allow new controls to be added in the future with zero database migrations or backend model updates.

### Decision 2: UI Panel Binding & Rendering Strategy
* **Question Asked:** Since we are using dynamic maps for storing properties, how should the properties UI panel generate its controls?
* **Options Considered:**
  * **Option A.1 (Static Layout with Map Bindings):** Maintain the existing visual layout files but write map getters/setters under the hood.
  * **Option B.1 (Fully Schema-Driven UI Generation - SELECTED):** Parse a schema and dynamically render input controls on the fly, styling them with curated, high-end aesthetics.
* **Architectural Rationale:** The team selected **Option B.1** with a strict requirement for **modern, state-of-the-art aesthetics**. This eliminates frontend layout maintenance while using vibrant palettes, glassmorphic card overlays, and subtle hover states.

### Decision 3: Schema Registry Storage Location
* **Question Asked:** Since the properties panel dynamically renders visual inputs based on a configuration schema, where should the schema definitions be stored?
* **Options Considered:**
  * **Option A.2 (Local Dynamic Registry):** Declare the visual property schemas in a dedicated local Dart registry file on the frontend.
  * **Option B.2 (Backend Schema API - SELECTED):** Fetch the configuration schema dynamically from a Flask API endpoint, adding support for server-side CRUD routes.
* **Architectural Rationale:** The team selected **Option B.2** with a strong constraint to **add CRUD endpoints on the backend without breaking or deleting any existing database logic or controllers**. This enables adding new options server-side instantly, which propagates to all frontend clients without new app updates.

### Decision 4: Fallback & Shimmer Loading UX
* **Question Asked:** How should the builder behave while the dynamic configuration schema is loading or if the network is completely offline?
* **Options Considered:**
  * **Option A.3 (Premium Shimmer & Local cached Fallback):** Display skeleton animations and load a cached local fallback if the API is offline.
  * **Option B.3 (Strict API Dependency - SELECTED):** Establish a strict network dependency to prevent data divergence, and display a high-fidelity shimmer loading skeleton.
* **Architectural Rationale:** The team selected **Option B.3** with the constraint to strictly display a **loading skeleton shimmer**. This maintains the premium aesthetic quality of the UI during the network latency phase while ensuring strict synchronization.

### Decision 5: Editing Complex Values (e.g. Option Arrays, Matrix Rows)
* **Question Asked:** How should the schema-driven UI render complex multi-value fields like selection choices or matrix rows?
* **Options Considered:**
  * **Option A.4 (Inline Dynamic Card Lists - SELECTED):** Render options directly inside the properties panel using inline, expandable cards with slide micro-animations.
  * **Option B.4 (Polished Modal Dialogs):** Launch a spacious modal dialog workspace overlay to configure selection list options.
* **Architectural Rationale:** The team selected **Option A.4**. Inline dynamic cards maintain visual context, keep the builder layout uncluttered, and prevent workflow interruption caused by disruptive modal popup actions.

---

## 5. Implementation Specifications & Payload Contracts

To ensure perfect alignment, the following payload structure has been engineered:

### A. The Backend Schema Contract (Dynamic CRUD API JSON)
* **Endpoint:** `GET /mahasangraha/api/v1/schemas/questions/{question_type}`
* **Response Payload Example:**
```json
{
  "question_type": "shortText",
  "groups": [
    {
      "name": "Validation",
      "fields": [
        {
          "key": "min_length",
          "type": "number",
          "label": "Minimum Character Limit",
          "placeholder": "e.g., 2",
          "target": "validation"
        },
        {
          "key": "regex",
          "type": "text",
          "label": "Custom Validation Pattern (RegEx)",
          "placeholder": "^[a-zA-Z]*$",
          "target": "validation"
        }
      ]
    },
    {
      "name": "Aesthetics",
      "fields": [
        {
          "key": "prefix_icon",
          "type": "select",
          "label": "Prefix Icon Style",
          "options": ["none", "email", "phone", "person"],
          "target": "ui"
        }
      ]
    }
  ]
}
```

### B. Flask MongoEngine Schema Definition
```python
# new file: models/SchemaDefinition.py
from database import db
from datetime import datetime

class SchemaDefinition(db.Document):
    meta = {
        'collection': 'schema_definitions',
        'indexes': ['question_type']
    }
    
    question_type = db.StringField(required=True, unique=True)
    groups = db.ListField(db.DictField(), default=list)
    created_at = db.DateTimeField(default=datetime.utcnow)
    updated_at = db.DateTimeField(default=datetime.utcnow)

    def to_json(self):
        return {
            "question_type": self.question_type,
            "groups": self.groups
        }
```

### C. Frontend Dynamic UI Element Builder (Flutter/Dart)
The frontend uses the dynamic maps of the `Question` model to build controls based on the fetched schema:

```dart
Widget buildDynamicControl({
  required Map<String, dynamic> fieldSchema,
  required Question question,
  required Function(String mapType, String key, dynamic value) onUpdate,
}) {
  final String key = fieldSchema['key'];
  final String type = fieldSchema['type'];
  final String label = fieldSchema['label'];
  final String target = fieldSchema['target']; // 'validation', 'ui', or 'logic'

  // Retrieve current value dynamically
  final dynamic currentValue = (target == 'validation')
      ? question.validation[key]
      : (target == 'ui')
          ? question.ui[key]
          : question.logic[key];

  switch (type) {
    case 'number':
      return TextFormField(
        decoration: InputDecoration(labelText: label, hintText: fieldSchema['placeholder']),
        initialValue: currentValue?.toString() ?? '',
        keyboardType: TextInputType.number,
        onChanged: (val) => onUpdate(target, key, int.tryParse(val)),
      );
    case 'text':
      return TextFormField(
        decoration: InputDecoration(labelText: label, hintText: fieldSchema['placeholder']),
        initialValue: currentValue?.toString() ?? '',
        onChanged: (val) => onUpdate(target, key, val),
      );
    case 'select':
      final List<String> opts = List<String>.from(fieldSchema['options'] ?? []);
      return DropdownButtonFormField<String>(
        decoration: InputDecoration(labelText: label),
        value: currentValue?.toString() ?? opts.first,
        items: opts.map((opt) => DropdownMenuItem(value: opt, child: Text(opt.toUpperCase()))).toList(),
        onChanged: (val) => onUpdate(target, key, val),
      );
    default:
      return const SizedBox();
  }
}
```

---

## 6. Risk Assessment & Safety Protocols

1. **Schema Breaking Safety:** Because we utilize dynamic maps (`DictField` in MongoEngine, `Map<String, dynamic>` in Dart), introducing new configuration properties in the schema definitions **cannot cause serialization crashes**. Fallback defaults are cleanly applied on the fly.
2. **Backwards Compatibility:** Old configurations matching explicit database columns will degrade gracefully and remain accessible.
3. **Database Guardrails:** The Flask CRUD controller for dynamic schema endpoints strictly enforces validation rules on the incoming JSON definitions before saving them to the MongoDB cluster.

---

## 7. Migration & Playbook

To securely fix existing discrepancies and introduce the schema-driven bindings, execute the following step-by-step playbook:

### Step 1: Frontend Dependency Resolution
Replace imports across all properties widgets:
```diff
-import 'package:frontend/features/form_builder/domain/entities/form_question.dart';
+import 'package:frontend/models/form_models.dart';
```

### Step 2: Controller Alignment
Expose flexible metadata-updating states so the panels can write dynamic values into maps rather than hardcoded fields.

### Step 3: Run OpenAPI Regeneration
```bash
make openapi
make generate-dart-client
```

### Step 4: Validate Contract Tests
```bash
flutter test test/unit/form_logic_engine_test.dart
```
