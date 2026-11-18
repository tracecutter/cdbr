"""HTTP boundary tests for cdbrd."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

import cdbr.server as server_module
from cdbr import __version__
from cdbr.core.model import CodewordPuzzle, extract_slots
from cdbr.core.photo import PhotoFormat
from cdbr.core.generator import GeneratedPuzzle
from cdbr.server import app

client = TestClient(app)


def test_home_serves_upload_experience():
    response = client.get("/")

    assert response.status_code == 200
    assert "Choose how to begin." in response.text
    assert 'action="/solve"' in response.text
    assert 'id="game-workspace" aria-labelledby="game-title" hidden' in response.text
    assert ">Create</button>" in response.text


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


def test_playable_puzzle_keeps_solution_private():
    response = client.get("/api/puzzles/1")

    assert response.status_code == 200
    assert response.json()["clues"] == {"5": "S", "25": "E", "26": "I"}
    assert response.json()["title"] == "Puzzle 1"
    assert response.json()["serial"] == 1
    assert "Petersfield" not in response.text
    assert "Perfect" not in response.text
    assert "answer" not in response.json()
    assert "solution" not in response.json()
    assert len(response.json()["symbols"]) == 26
    assert len(response.json()["used_symbols"]) == 21


def test_playable_puzzle_reveals_one_symbol():
    response = client.post("/api/puzzles/1/reveal/20")

    assert response.status_code == 200
    assert response.json() == {"symbol": 20, "letter": "N"}


def test_playable_puzzle_can_reveal_complete_mapping():
    response = client.post("/api/puzzles/1/reveal")

    assert response.status_code == 200
    assert response.json()["mapping"]["5"] == "S"
    assert len(response.json()["mapping"]) == 26


def test_corpus_session_converges_on_private_playable_state():
    created = client.post("/api/sessions/from-corpus/1")

    assert created.status_code == 201
    prepared = created.json()
    assert prepared["title"] == "Puzzle 1"
    assert prepared["provenance"] == "corpus"
    assert "solution" not in prepared
    session_id = prepared["session_id"]
    resumed = client.get(f"/api/sessions/{session_id}")
    revealed = client.post(f"/api/sessions/{session_id}/reveal/20")
    assert resumed.json() == prepared
    assert revealed.json() == {"symbol": 20, "letter": "N"}


def test_photo_session_converges_on_same_playable_state(monkeypatch):
    grid = ((1, 2), (3, 4))
    puzzle = CodewordPuzzle(grid=grid, clues={1: "A"}, slots=extract_slots(grid))
    solved = SimpleNamespace(
        puzzle=puzzle,
        mapping={1: "A", 2: "B", 3: "C", 4: "D"},
        result=SimpleNamespace(exhausted=True, solutions=(object(),)),
    )
    monkeypatch.setattr(server_module, "detect_photo_format", lambda _: PhotoFormat.JPEG)
    monkeypatch.setattr(server_module, "solve_photo", lambda _source, _work_dir: solved)

    response = client.post(
        "/api/sessions/from-photo",
        files={"photo": ("puzzle.jpg", b"pretend jpeg", "image/jpeg")},
    )

    assert response.status_code == 201
    prepared = response.json()
    assert prepared["title"] == "Scanned puzzle"
    assert prepared["provenance"] == "photo"
    assert prepared["clues"] == {"1": "A"}
    assert "solution" not in prepared
    revealed = client.post(f"/api/sessions/{prepared['session_id']}/reveal/4")
    assert revealed.json() == {"symbol": 4, "letter": "D"}


def test_photo_preview_converts_upload_to_browser_image(monkeypatch):
    monkeypatch.setattr(server_module, "detect_photo_format", lambda _: PhotoFormat.HEIF)

    def fake_normalize(_source, destination, *, maximum_size):
        assert maximum_size == 1400
        destination.write_bytes(b"preview jpeg")

    monkeypatch.setattr(server_module, "normalize_photo", fake_normalize)
    response = client.post(
        "/api/photo-preview",
        files={"photo": ("puzzle.heic", b"pretend heic", "image/heic")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"preview jpeg"


def test_create_generation_job_is_bounded_and_asynchronous(monkeypatch):
    monkeypatch.setattr(server_module, "_generation_executor", SimpleNamespace(submit=lambda *_: None))

    response = client.post(
        "/api/generation-jobs",
        json={"required_words": ["PERFECT", "FOR"], "excluded_words": ["NESS"], "minutes": 1},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "job_id" in response.json()


def test_publish_generated_candidate_assigns_next_serial():
    server_module._runtime_corpus.clear()
    grid = ((1, 2), (3, 4))
    puzzle = CodewordPuzzle(grid=grid, clues={1: "A", 2: "B", 3: "C"}, slots=extract_slots(grid))
    generated = GeneratedPuzzle(
        puzzle=puzzle,
        answer=("AB", "CD"),
        mapping={1: "A", 2: "B", 3: "C", 4: "D"},
        certification=SimpleNamespace(),
        seed=99,
    )
    job = server_module.GenerationJob(
        job_id="publish-test",
        request=server_module.CreatePuzzleRequest(required_words=["AB"], minutes=1),
        status="complete",
        generated=generated,
    )
    server_module._generation_jobs[job.job_id] = job

    response = client.post("/api/generation-jobs/publish-test/publish")

    assert response.status_code == 201
    assert response.json()["serial"] == 2
    assert response.json()["title"] == "Puzzle 2"
    assert response.json()["origin"] == "cdbr_generated"
    assert "solution" not in response.json()


def test_generation_job_keeps_best_certified_candidate(monkeypatch):
    def generated(grid, seed):
        puzzle = CodewordPuzzle(grid=grid, clues={1: "A"}, slots=extract_slots(grid))
        return GeneratedPuzzle(
            puzzle=puzzle,
            answer=tuple("".join("#" if value is None else "A" for value in row) for row in grid),
            mapping={1: "A", 2: "B", 3: "C", 4: "D"},
            certification=SimpleNamespace(solutions=()),
            seed=seed,
        )

    candidates = iter(
        (
            generated(((1, None), (2, 3)), 1),
            generated(((1, 2), (3, 4)), 2),
        )
    )

    def fake_generate(*_args, **_kwargs):
        try:
            return next(candidates)
        except StopIteration:
            raise ValueError("budget exhausted") from None

    monkeypatch.setattr(server_module, "english_lexicon", lambda: object())
    monkeypatch.setattr(server_module, "generate_puzzle", fake_generate)
    job = server_module.GenerationJob(
        job_id="best-test",
        request=server_module.CreatePuzzleRequest(required_words=["AB"], minutes=0.25),
    )

    server_module._run_generation_job(job)

    assert job.status == "complete"
    assert job.certified_candidates == 2
    assert job.generated is not None
    assert job.generated.seed == 2


def test_running_generation_job_can_publish_best_so_far():
    server_module._runtime_corpus.clear()
    grid = ((1, 2), (3, 4))
    generated = GeneratedPuzzle(
        puzzle=CodewordPuzzle(grid=grid, clues={1: "A", 2: "B", 3: "C"}, slots=extract_slots(grid)),
        answer=("AB", "CD"),
        mapping={1: "A", 2: "B", 3: "C", 4: "D"},
        certification=SimpleNamespace(solutions=()),
        seed=101,
    )
    job = server_module.GenerationJob(
        job_id="running-best-test",
        request=server_module.CreatePuzzleRequest(required_words=["AB"], minutes=1),
        status="running",
        generated=generated,
        certified_candidates=1,
    )
    server_module._generation_jobs[job.job_id] = job

    response = client.post("/api/generation-jobs/running-best-test/publish")

    assert response.status_code == 201
    assert job.status == "accepted"
    assert job.accepted is True
    assert job.cancelled is True


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
