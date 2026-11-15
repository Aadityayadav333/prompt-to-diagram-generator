def test_pages_render_and_have_no_inline_scripts(client):
    for path in ("/", "/login", "/register"):
        r = client.get(path)
        assert r.status_code == 200, path
        html = r.get_data(as_text=True)
        assert "DiagramForge AI" in html
        # CSP forbids inline scripts, so none may exist
        import re
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html), path


def test_private_pages_redirect_to_login(client):
    for path in ("/dashboard", "/editor/abc123"):
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_editor_page_for_logged_in_user_and_bad_id(client):
    from conftest import register
    register(client)
    assert client.get("/dashboard").status_code == 200
    assert client.get("/editor/abc123").status_code == 200
    assert client.get("/editor/<script>").status_code == 404
