"""Custom errors for Signal Engine."""


class SignalEngineError(Exception):
    """Base exception for all Signal Engine errors."""
    pass


class SourceError(SignalEngineError):
    """Raised when a data source fails to return usable data."""
    pass


class ConfigError(SignalEngineError):
    """Raised when configuration is invalid or missing."""
    pass


class RenderError(SignalEngineError):
    """Raised when rendering a derived artifact fails."""
    pass


class WriteError(SignalEngineError):
    """Raised when writing an output file fails."""
    pass
