"""Validation shared by adapters that call explicitly local model servers."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from .errors import CoreDomainError


def validate_local_endpoint(value: object) -> tuple[str, bool]:
    """Accept literal loopback/private IPs and reject DNS or public destinations."""
    message = "Use an HTTP(S) loopback or private IP base URL without credentials or query."
    try:
        if not isinstance(value, str) or len(value) > 512 or not value:
            raise ValueError
        if any(ord(character) <= 32 or ord(character) >= 127 for character in value):
            raise ValueError
        if "\\" in value:
            raise ValueError
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or "?" in value
            or "#" in value
            or "%" in value
        ):
            raise ValueError
        host = "127.0.0.1" if url.hostname == "localhost" else url.hostname
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            raise ValueError
        private = any(
            address in ipaddress.ip_network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
        )
        if not address.is_loopback and not private:
            raise ValueError
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError
        if any(part in {".", ".."} for part in url.path.split("/")):
            raise ValueError
        authority = f"[{address}]" if address.version == 6 else str(address)
        if url.port is not None:
            authority += f":{url.port}"
        return f"{url.scheme}://{authority}{url.path.rstrip('/')}", address.is_loopback
    except (ValueError, TypeError) as error:
        raise CoreDomainError("PROVIDER_ENDPOINT_INVALID", message) from error
