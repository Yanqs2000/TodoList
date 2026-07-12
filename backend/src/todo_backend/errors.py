class ConfigurationError(ValueError):
    """Raised when required backend configuration is invalid."""


class DatabaseVersionError(RuntimeError):
    """Raised when the database schema is newer than this backend supports."""
