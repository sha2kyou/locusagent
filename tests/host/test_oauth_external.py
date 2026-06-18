"""OAuth 外部浏览器回调页。"""

from __future__ import annotations

from locus_host.oauth_external import oauth_callback_html


def test_oauth_callback_html_success() -> None:
    page = oauth_callback_html(ok=True, server_name="notion")
    assert "OAuth 授权" in page
    assert "notion" in page
    assert "tool-card" in page
    assert "badge-ok" in page


def test_oauth_callback_html_failure_escapes_message() -> None:
    page = oauth_callback_html(ok=False, message='<script>alert("x")</script>')
    assert "badge-error" in page
    assert "<script>" not in page
