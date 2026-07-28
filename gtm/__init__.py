"""GTM Research Platform — core package."""

from .net import enable_system_trust_store

# Use the OS trust store for TLS (handles corporate proxy CAs). Safe no-op if
# truststore is unavailable or GTM_NO_TRUSTSTORE=1.
enable_system_trust_store()

__version__ = "0.1.0"
