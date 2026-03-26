# --- ENUMS ---

STATUS_CHOICES = ("draft", "published", "archived")

# --- User & Auth Choices ---
USER_TYPE_CHOICES = ("employee", "general")

ROLE_CHOICES = (
    "superadmin",
    "admin",
    "user",
    "creator",
    "approver",
    "editor",
    "publisher",
    "deo",
    "manager",
    "general",
)

UI_TYPE_CHOICES = (
    # Flex layout: A simple, flexible box layout
    "flex",  # Flexbox layout that arranges elements in a row or column
    # Grid layout with two columns: A layout that uses CSS grid with 2 columns
    "grid-cols-2",  # CSS grid layout with two columns
    # Tabbed layout: A layout where content is organized into separate tabs
    "tabbed",  # Tabbed interface layout, useful for segregating content into tabs
    # Custom layout: A user-defined or more complex layout
    "custom",  # Custom layout, could be user-defined or specialized for specific needs
    # Grid layout with multiple columns: A layout using a CSS grid with multiple columns
    "grid-cols-3",  # CSS grid layout with three columns
    # Full-width layout: A layout where content takes up the entire width of the screen/container
    "full-width",  # Full width layout, useful for displaying wide content like images or banners
    # Card-based layout: A layout where content is organized in "cards"
    "card",  # Card-based layout, often used for displaying items in a grid of cards
    # List-based layout: A layout where content is arranged in a list (vertical stack)
    "list",  # List layout, typically used for vertical stacking of items
    # Sidebar layout: A layout that includes a sidebar (for navigation or additional content)
    "sidebar",  # Sidebar layout, useful for navigation or adding supplementary content to the side
    # Split layout: A layout where the screen is divided into two or more sections
    "split",  # Split screen layout, useful for creating a two-panel or multi-panel design
    # Overlay layout: A layout where content is presented over a background (e.g., modals, pop-ups)
    "overlay",  # Overlay layout, typically used for modal windows or floating elements
    # Dashboard layout: A layout that groups multiple widgets/cards in a grid-like structure
    "dashboard",  # Dashboard layout, often used for analytics, metrics, or widgets
    # Centered layout: A layout that centers content both horizontally and vertically
    "centered",  # Centered content layout, often used for forms, modals, or single content views
    # Stacked layout: A layout where elements are stacked vertically (often used in mobile designs)
    "stacked",  # Stacked layout, useful for mobile-first or single-column designs
    # Masonry layout: A grid layout with varying row heights, similar to Pinterest
    "masonry",  # Masonry layout, commonly used for galleries, image-heavy content
    # Fixed-layout: A layout where the width or height of elements is fixed, typically used for banners
    "fixed",  # Fixed layout, where elements do not resize or adjust based on the screen size
)

FIELD_TYPE_CHOICES = (
    # Basic Input Types
    "input",  # Single-line text input
    "textarea",  # Multi-line text input
    "number",  # Numeric input
    "email",  # Email input with validation
    "mobile",  # Mobile number input with validation
    "url",  # URL input with validation
    "password",  # Password input (masked)
    "tel",  # Telephone number input
    "calculate",  # Calculated field
    "note",  # Note field
    # Selection Input Types
    "select",  # Dropdown select list
    "dropdown",  # Another term for select dropdown
    "radio",  # Radio button for single choice selection
    "checkbox",  # Checkbox for binary options (true/false)
    "multi_select",  # Multi-select dropdown (select multiple items)
    "checkboxes",  # Multiple checkboxes for selections
    "matrix_choice",  # Multi-choice options in a matrix format
    # Specialized Input Types
    "boolean",  # Binary choice, true/false (yes/no)
    "rating",  # Star rating input (e.g., 1-5 stars)
    "date",  # Date input (select a single date)
    "time",  # Time input (select a time of day)
    "datetime",  # Date and time input
    "datetime-local",  # Date and time input without timezone
    "month",  # Month input (select a month)
    "week",  # Week input (select a week)
    # Advanced Input Types
    "file_upload",  # Upload a single file
    "multi-file_upload",  # Upload multiple files
    "file_picker",  # File picker input (single/multiple files)
    "file_list",  # List of uploaded files
    "image",  # Image upload (for images specifically)
    "video_upload",  # Video upload
    "audio_upload",  # Audio file upload
    "signature",  # Signature input (e.g., drawing pad)
    "signature_pad",  # Another term for signature input pad
    "image_gallery",  # Select from an image gallery
    # Location and Geospatial Inputs
    "map_location",  # Select location on a map
    "address",  # Address input (could be text-based or auto-complete)
    "address_lookup",  # Address input with auto-completion (e.g., Google Places API)
    # Calculated and API-based Inputs
    "calculated",  # A field that gets its value based on calculations (e.g., dynamic)
    "api_search",  # Input field that calls an API to fetch search results
    "otp",  # OTP (One-Time Password) input field for verification
    # Text-based Inputs
    "short_text",  # A small text input field (e.g., a name or title)
    "paragraph",  # A paragraph-style input field (larger text block)
    "rich_text",  # Rich-text input (styled text with bold, italics, etc.)
    "textarea_editor",  # Rich text editor (e.g., TinyMCE, CKEditor)
    "markdown_editor",  # Markdown editor for formatted text
    # Visual Inputs
    "color_picker",  # Color selection input
    "slider",  # Slider input (for range selection)
    "range",  # Range input (like for selecting a range of numbers)
    # Time and Date Ranges
    "date_range",  # Select a range of dates
    "time_range",  # Select a range of times
    "stepper",  # Step-by-step navigation (wizard-like form)
    # Other Specialized Inputs
    "country_select",  # Dropdown for selecting a country
    "state_select",  # Dropdown for selecting a state
    "city_select",  # Dropdown for selecting a city
    "social_media_handle",  # Social media username/handle
    "website_url",  # Website URL input
    "phone_number",  # Specialized phone number input with validation
    "captcha",  # CAPTCHA input (e.g., reCAPTCHA for verification)
    "unit_select",  # Input for selecting units (kg, lbs, etc.)
    "price",  # Specialized field for monetary amounts (e.g., with currency formatting)
    "age",  # Age input field with validation
    "toggle",  # Toggle switch (on/off)
    "hidden",  # Hidden field, typically for form use (no user input)
    "custom_field",  # Custom input field for flexible usage
    "multi_checkbox",  # A set of checkboxes for multiple selections
    "email_list",  # Multiple email addresses input (comma-separated)
    "qr_code_scan",  # QR code scanner input
    "search",  # General search field
    "file",  # Generic file input (for any type of file)
)


FIELD_API_CALL_CHOICES = ("uhid", "employee_id", "form", "otp", "custom")

# --- Condition Choices ---
CONDITION_TYPE_CHOICES = ("simple", "group")

LOGICAL_OPERATOR_CHOICES = ("AND", "OR", "NOT", "NOR", "NAND")

CONDITION_SOURCE_TYPE_CHOICES = (
    "field",
    "hidden_field",
    "url_param",
    "user_info",
    "calculated_value",
)

CONDITION_OPERATOR_CHOICES = (
    "equals",
    "not_equals",
    "greater_than",
    "less_than",
    "greater_than_equals",
    "less_than_equals",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
    "in_list",
    "not_in_list",
    "matches_regex",
    "between",
    "is_checked",
)

COMPARISON_TYPE_CHOICES = ("constant", "field", "url_param", "user_info", "calculation")

# --- Response Choices ---
RESPONSE_STATUS_CHOICES = ("submitted", "processed", "error", "archived")
REVIEW_STATUS_CHOICES = ("pending", "approved", "rejected")

# --- Access Control Choices ---
ACCESS_LEVEL_CHOICES = ("private", "group", "organization", "public")
RESOURCE_TYPE_CHOICES = ("form", "project", "submission", "view")

PERMISSION_CHOICES = (
    "view",
    "edit",
    "delete",
    "publish",
    "export_data",
    "manage_access",
    "approve_submissions",
    "approve_hooks",
)

# --- Approval Workflow Choices ---
APPROVAL_TYPE_CHOICES = ("sequential", "parallel", "maker-checker", "any_one")
WORKFLOW_STATUS_CHOICES = ("pending", "in_review", "approved", "rejected", "reverted")

# --- Trigger Choices ---
TRIGGER_EVENT_CHOICES = (
    "on_load",
    "on_submit",
    "on_change",
    "on_status_change",
    "on_validate",
    "on_approval_step",
    "on_creation",
)

TRIGGER_ACTION_CHOICES = (
    "webhook",
    "email",
    "sms",
    "notification",
    "update_field",
    "execute_script",
    "hide_show",
    "enable_disable",
    "validation_error",
    "calculation",
    "api_call",
    "form_data",
    "external_hook",
    "predefined_url",
)
