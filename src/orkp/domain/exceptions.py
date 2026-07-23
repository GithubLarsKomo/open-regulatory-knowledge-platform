"""
Typed domain exceptions for ORKP.

Expected business failures use typed exceptions rather than None/False returns.
API handlers map these to appropriate HTTP status codes.
"""


class ORKPError(Exception):
    """Base exception for all ORKP domain errors."""

    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class ObjectNotFoundError(ORKPError):
    """Raised when a regulatory object is not found."""

    status_code = 404
    message = "Object not found"


class InvalidLifecycleTransitionError(ORKPError):
    """Raised when a lifecycle state transition is not allowed."""

    status_code = 409
    message = "Invalid lifecycle transition"


class ImmutableVersionError(ORKPError):
    """Raised when attempting to modify an approved/immutable version."""

    status_code = 409
    message = "Version is immutable after approval"


class OptimisticLockError(ORKPError):
    """Raised when a concurrent modification is detected."""

    status_code = 409
    message = "Concurrent modification detected; retry the operation"


class InvalidRelationError(ORKPError):
    """Raised when an object relation is invalid."""

    status_code = 422
    message = "Invalid object relation"


class ProductCompletenessError(ORKPError):
    """Raised when a product does not meet minimum completeness requirements."""

    status_code = 422
    message = "Product completeness check failed"


class ClaimApprovalError(ORKPError):
    """Raised when a claim cannot be approved due to insufficient evidence."""

    status_code = 422
    message = "Claim approval check failed"


class EvidenceCoverageError(ORKPError):
    """Raised when evidence coverage is insufficient."""

    status_code = 422
    message = "Evidence coverage insufficient"


class ConsistencyError(ORKPError):
    """Raised when consistent checking detects conflicts."""

    status_code = 422
    message = "Claim consistency check failed"


class RelationNotFoundError(ORKPError):
    """Raised when a relation is not found."""

    status_code = 404
    message = "Relation not found"


class RelationAlreadyInactiveError(ORKPError):
    """Raised when attempting to deactivate an already inactive relation."""

    status_code = 409
    message = "Relation is already inactive"


class BaselineValidationError(ORKPError):
    """Raised when baseline creation fails validation."""

    status_code = 422
    message = "Baseline validation failed"


class RiskCompletenessError(ORKPError):
    """Raised when a risk analysis is not complete."""

    status_code = 422
    message = "Risk completeness check failed"


class RiskEvaluationError(ORKPError):
    """Raised when risk evaluation fails."""

    status_code = 422
    message = "Risk evaluation failed"


class RiskControlVerificationError(ORKPError):
    """Raised when risk control verification fails."""

    status_code = 422
    message = "Risk control verification failed"


class AuthorizationError(ORKPError):
    """Raised when an operation is not authorized."""

    status_code = 403
    message = "Operation not authorized"


class SelfApprovalNotAllowedError(ORKPError):
    """Raised when an author attempts to self-approve."""

    status_code = 403
    message = "Self-approval is not allowed"


class ObjectTypeMismatchError(ORKPError):
    """Raised when an object's type does not match the expected type."""

    status_code = 422
    message = "Object type mismatch"


class ObjectVersionNotFoundError(ORKPError):
    """Raised when a specific object version is not found."""

    status_code = 404
    message = "Object version not found"


class InvalidLifecycleStateError(ORKPError):
    """Raised when an object is in an invalid lifecycle state."""

    status_code = 409
    message = "Invalid lifecycle state for operation"


class InvalidPersistedPayloadError(ORKPError):
    """Raised when a persisted payload fails validation."""

    status_code = 422
    message = "Invalid persisted payload"


class InvalidObjectIdentifierError(ORKPError):
    """Raised when an object identifier has an invalid format."""

    status_code = 422
    message = "Invalid object identifier format"
