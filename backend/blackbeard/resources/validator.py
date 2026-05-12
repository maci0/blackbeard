"""Resource validation: JSON Schema + ref parsing + cross-resource checks."""

import jsonschema

from blackbeard.resources.spec_schemas import KIND_SCHEMAS
from blackbeard.resources.refs import extract_refs, RefParseError

# Pre-compile validators for each kind (schemas never change at runtime)
_VALIDATORS: dict[str, jsonschema.Draft7Validator] = {
    kind: jsonschema.Draft7Validator(schema) for kind, schema in KIND_SCHEMAS.items()
}


class ValidationError:
    """A single validation error."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError({self.field}: {self.message})"

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


def validate_resource(kind: str, spec: dict) -> list[ValidationError]:
    """Validate a resource spec against its JSON Schema.

    Returns a list of ValidationError objects (empty if valid).
    """
    errors: list[ValidationError] = []

    # Check kind is known
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return [ValidationError(field="kind", message=f"Unknown kind: {kind}")]

    # JSON Schema validation
    for error in sorted(validator.iter_errors(spec), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "spec"
        errors.append(ValidationError(f"spec.{path}", error.message))

    # Validate ref format
    try:
        extract_refs(spec)
    except RefParseError as e:
        errors.append(ValidationError("spec", str(e)))

    return errors

