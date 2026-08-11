/**
 * Shared Form Validation — Story 137.
 *
 * Accessible form primitives with:
 * - Typed field definitions (label, required, validation rules)
 * - Client-side validation with rule composition
 * - Server-error mapping to specific fields or summary
 * - Focus management (first invalid field on submit)
 * - Submitting/disabled state control
 * - Input preservation on recoverable failure
 *
 * Usage:
 *   const form = useForm({ fields: { name: { required: true, minLength: 1 } } });
 *   <FormField field={form.fields.name} />
 */

// =============================================================================
// Types
// =============================================================================

export interface ValidationRule {
  /** Rule name for identification */
  name: string;
  /** Validation function — returns error message or null */
  validate: (value: unknown) => string | null;
}

export interface FieldDefinition {
  /** Human-readable label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Help/description text */
  description?: string;
  /** Field type for input rendering */
  type?: "text" | "email" | "password" | "number" | "textarea" | "select" | "file";
  /** Validation rules (in addition to required) */
  rules?: ValidationRule[];
  /** Min length for text inputs */
  minLength?: number;
  /** Max length for text inputs */
  maxLength?: number;
}

export interface FieldState {
  /** Current field value */
  value: string;
  /** Validation error (client or server) */
  error: string | null;
  /** Whether the field has been touched (blurred) */
  touched: boolean;
  /** Whether the field is currently being validated async */
  validating: boolean;
  /** Unique ID for accessibility (aria-describedby) */
  id: string;
  /** ID for the error message element */
  errorId: string;
  /** ID for the description element */
  descriptionId: string;
}

export interface FormState {
  /** All field states keyed by field name */
  fields: Record<string, FieldState>;
  /** Whether the form is currently submitting */
  submitting: boolean;
  /** Global form error (not field-specific) */
  formError: string | null;
  /** Whether form has been submitted at least once */
  submitted: boolean;
  /** Whether all fields are valid */
  isValid: boolean;
}

export interface ServerError {
  /** Field name this error applies to (null = form-level) */
  field: string | null;
  /** Error message */
  message: string;
  /** Machine-readable code */
  code?: string;
}

// =============================================================================
// Built-in Validation Rules
// =============================================================================

export function required(label: string): ValidationRule {
  return {
    name: "required",
    validate: (value) => {
      if (value === null || value === undefined || String(value).trim() === "") {
        return `${label} is required`;
      }
      return null;
    },
  };
}

export function minLength(label: string, min: number): ValidationRule {
  return {
    name: "minLength",
    validate: (value) => {
      if (String(value).length < min) {
        return `${label} must be at least ${min} characters`;
      }
      return null;
    },
  };
}

export function maxLength(label: string, max: number): ValidationRule {
  return {
    name: "maxLength",
    validate: (value) => {
      if (String(value).length > max) {
        return `${label} must be no more than ${max} characters`;
      }
      return null;
    },
  };
}

export function email(): ValidationRule {
  return {
    name: "email",
    validate: (value) => {
      const str = String(value);
      if (str && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(str)) {
        return "Please enter a valid email address";
      }
      return null;
    },
  };
}

export function pattern(label: string, regex: RegExp, message?: string): ValidationRule {
  return {
    name: "pattern",
    validate: (value) => {
      if (String(value) && !regex.test(String(value))) {
        return message || `${label} format is invalid`;
      }
      return null;
    },
  };
}

// =============================================================================
// Field Validation
// =============================================================================

export function validateField(
  value: string,
  definition: FieldDefinition,
): string | null {
  // Required check
  if (definition.required && (!value || value.trim() === "")) {
    return `${definition.label} is required`;
  }

  // Skip further validation if empty and not required
  if (!value || value.trim() === "") return null;

  // MinLength
  if (definition.minLength && value.length < definition.minLength) {
    return `${definition.label} must be at least ${definition.minLength} characters`;
  }

  // MaxLength
  if (definition.maxLength && value.length > definition.maxLength) {
    return `${definition.label} must be no more than ${definition.maxLength} characters`;
  }

  // Custom rules
  if (definition.rules) {
    for (const rule of definition.rules) {
      const error = rule.validate(value);
      if (error) return error;
    }
  }

  return null;
}

// =============================================================================
// Form Validation (all fields)
// =============================================================================

export function validateForm(
  values: Record<string, string>,
  definitions: Record<string, FieldDefinition>,
): Record<string, string | null> {
  const errors: Record<string, string | null> = {};
  for (const [name, def] of Object.entries(definitions)) {
    errors[name] = validateField(values[name] || "", def);
  }
  return errors;
}

export function hasErrors(errors: Record<string, string | null>): boolean {
  return Object.values(errors).some((e) => e !== null);
}

export function getFirstErrorField(errors: Record<string, string | null>): string | null {
  for (const [name, error] of Object.entries(errors)) {
    if (error !== null) return name;
  }
  return null;
}

// =============================================================================
// Server Error Mapping
// =============================================================================

export function mapServerErrors(
  serverErrors: ServerError[],
  fieldNames: string[],
): { fieldErrors: Record<string, string>; formError: string | null } {
  const fieldErrors: Record<string, string> = {};
  let formError: string | null = null;

  for (const err of serverErrors) {
    if (err.field && fieldNames.includes(err.field)) {
      fieldErrors[err.field] = err.message;
    } else {
      // Accumulate as form-level error
      formError = formError ? `${formError}; ${err.message}` : err.message;
    }
  }

  return { fieldErrors, formError };
}

// =============================================================================
// Focus Management
// =============================================================================

export function focusFirstError(
  errors: Record<string, string | null>,
  fieldPrefix: string = "field-",
): void {
  const firstField = getFirstErrorField(errors);
  if (firstField) {
    const element = document.getElementById(`${fieldPrefix}${firstField}`);
    if (element) {
      element.focus();
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

// =============================================================================
// Accessibility Helpers
// =============================================================================

export function getFieldAriaProps(fieldState: FieldState, definition: FieldDefinition) {
  const describedBy: string[] = [];
  if (definition.description) describedBy.push(fieldState.descriptionId);
  if (fieldState.error) describedBy.push(fieldState.errorId);

  return {
    id: fieldState.id,
    "aria-required": definition.required || false,
    "aria-invalid": fieldState.error ? true : undefined,
    "aria-describedby": describedBy.length > 0 ? describedBy.join(" ") : undefined,
  };
}

// =============================================================================
// Create Initial Field State
// =============================================================================

export function createFieldState(name: string, initialValue: string = ""): FieldState {
  return {
    value: initialValue,
    error: null,
    touched: false,
    validating: false,
    id: `field-${name}`,
    errorId: `field-${name}-error`,
    descriptionId: `field-${name}-desc`,
  };
}

export function createFormState(
  definitions: Record<string, FieldDefinition>,
  initialValues?: Record<string, string>,
): FormState {
  const fields: Record<string, FieldState> = {};
  for (const name of Object.keys(definitions)) {
    fields[name] = createFieldState(name, initialValues?.[name] || "");
  }
  return {
    fields,
    submitting: false,
    formError: null,
    submitted: false,
    isValid: true,
  };
}
