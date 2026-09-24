import forge_backend as backend


def assert_common_security_headers(response):
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"


def test_static_app_response_has_browser_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200

    assert_common_security_headers(response)

    csp = response.headers["Content-Security-Policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "connect-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ):
        assert directive in csp


def test_api_responses_receive_same_browser_hardening(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200

    assert_common_security_headers(response)
    assert response.headers["Content-Security-Policy"] == (
        backend.CONTENT_SECURITY_POLICY
    )


def test_hsts_is_not_enabled_for_local_test_environment(client):
    response = client.get("/")
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_is_enabled_for_deployment_environment(client, monkeypatch):
    monkeypatch.setitem(
        backend.app.config,
        "FORGE_ENVIRONMENT",
        "production",
    )

    response = client.get("/")

    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
