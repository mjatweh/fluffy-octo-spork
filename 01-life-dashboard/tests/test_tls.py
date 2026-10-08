import ssl

from life_dashboard import tls


def test_context_is_shared_and_verifies():
    ctx = tls.context()
    assert ctx is tls.context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
