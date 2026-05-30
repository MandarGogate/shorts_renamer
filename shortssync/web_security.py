"""
Security helpers for the web backend.

Pure, dependency-free functions (no Flask import) so they can be unit-tested in
isolation. Covers three PLAN.md Phase 1 concerns:

* BUG-001 - authentication token + loopback-only default.
* BUG-002 - filesystem path allow-listing.
* BUG-003 - download URL validation (SSRF) + output filename containment.

Environment variables (all optional):
* SHORTSSYNC_TOKEN  - shared secret required on /api/* when set.
* SHORTSSYNC_HOST   - bind host (default 127.0.0.1).
* SHORTSSYNC_ROOTS  - os.pathsep-separated directories that requests may touch.
                      When unset, paths are allowed (preserves local-tool UX).
* SHORTSSYNC_CORS_ORIGINS - comma-separated allowed origins (REST layer).
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import socket
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse

LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def get_auth_token() -> Optional[str]:
    """Return the configured shared secret, or None if auth is disabled."""
    token = os.environ.get("SHORTSSYNC_TOKEN", "").strip()
    return token or None


def token_matches(provided: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time comparison of a provided token against the expected one."""
    if not expected:
        # Auth disabled -> always allowed.
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def is_loopback_host(host: str) -> bool:
    """True if host is a loopback hostname/address (safe to bind without auth)."""
    if host in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def get_allowed_roots() -> List[Path]:
    """Parse SHORTSSYNC_ROOTS into a list of resolved directories (may be empty)."""
    raw = os.environ.get("SHORTSSYNC_ROOTS", "").strip()
    if not raw:
        return []
    roots: List[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).expanduser().resolve())
    return roots


def resolve_within_roots(path: str, roots: Iterable[Path]) -> Optional[Path]:
    """
    Resolve ``path`` and confirm it lives inside one of ``roots``.

    Returns the resolved Path on success or None if the path is invalid or
    escapes every allowed root. An empty ``roots`` collection means "no
    allow-list configured" and any resolvable path is accepted (preserves the
    local single-user workflow when SHORTSSYNC_ROOTS is unset).
    """
    if not path or not isinstance(path, str):
        return None
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None

    root_list = list(roots)
    if not root_list:
        return resolved

    for root in root_list:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None


def is_safe_download_url(url: str) -> bool:
    """
    Best-effort SSRF guard: allow only http(s) URLs whose host resolves to
    public (non-private/loopback/link-local/reserved) addresses.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False

    if not infos:
        return False

    for info in infos:
        ip_str = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True
