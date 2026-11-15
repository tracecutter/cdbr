"""HTTP boundary tests for cdbrd."""

from fastapi.testclient import TestClient

from cdbr import __version__
from cdbr.server import app

client = TestClient(app)


def test_home_serves_upload_experience():
    response = client.get("/")

    assert response.status_code == 200
    assert "Solve your Code Break" in response.text
    assert 'action="/solve"' in response.text


def test_web_assets_are_served():
    stylesheet = client.get("/static/app.css")
    script = client.get("/static/app.js")
    logo = client.get("/static/f-logo.png")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"


def test_health_reports_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_solve_rejects_empty_upload():
    response = client.post("/solve", files={"photo": ("puzzle.jpg", b"", "image/jpeg")})

    assert response.status_code == 400
    assert response.json() == {"detail": "Photograph is empty"}


def test_solve_rejects_unknown_image():
    response = client.post("/solve", files={"photo": ("puzzle.jpg", b"not an image", "image/jpeg")})

    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported or unrecognised image format"}


def test_solve_requires_photo():
    response = client.post("/solve")

    assert response.status_code == 422
