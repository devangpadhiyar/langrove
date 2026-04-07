"""Domain exceptions for Langrove."""


class LangroveError(Exception):
    """Base exception for all Langrove errors."""


class NotFoundError(LangroveError):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} '{resource_id}' not found")


class ConflictError(LangroveError):
    """Resource already exists or conflicting operation."""

    def __init__(self, message: str):
        super().__init__(message)


class AuthError(LangroveError):
    """Authentication failure (401)."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message)


class ForbiddenError(LangroveError):
    """Authorization failure (403)."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message)


class ConfigError(LangroveError):
    """Invalid configuration."""

    def __init__(self, message: str):
        super().__init__(message)
