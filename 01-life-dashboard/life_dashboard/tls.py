"""One TLS context for every HTTPS / IMAP connection.

The python.org macOS installer ships Python without trusted root certificates
until "Install Certificates.command" is run, and a company Mac may add its own
root for a network filter. Either way Python's defaults fail with
CERTIFICATE_VERIFY_FAILED while Safari works. This context trusts the system
defaults plus certifi's bundle (when installed) plus the macOS keychains.
"""
from __future__ import annotations

import ssl
import subprocess
import sys
from functools import lru_cache

MAC_KEYCHAINS = [
    "/System/Library/Keychains/SystemRootCertificates.keychain",
    "/Library/Keychains/System.keychain",
]


def _mac_keychain_pem() -> str:
    try:
        out = subprocess.run(["security", "find-certificate", "-a", "-p", *MAC_KEYCHAINS],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if "BEGIN CERTIFICATE" in out.stdout else ""


@lru_cache(maxsize=1)
def context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    if sys.platform == "darwin":
        pem = _mac_keychain_pem()
        if pem:
            try:
                ctx.load_verify_locations(cadata=pem)
            except ssl.SSLError:
                # one malformed certificate rejects the whole bundle; add them one by one
                for block in pem.split("-----END CERTIFICATE-----"):
                    if "BEGIN CERTIFICATE" in block:
                        try:
                            ctx.load_verify_locations(cadata=block + "-----END CERTIFICATE-----\n")
                        except ssl.SSLError:
                            pass
    return ctx
