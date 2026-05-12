class OutboundAssistantError(Exception):
    """Base application error."""


class ProviderError(OutboundAssistantError):
    """Raised when an external provider fails."""


class EscalationRequired(OutboundAssistantError):
    """Raised when the session should escalate immediately."""
