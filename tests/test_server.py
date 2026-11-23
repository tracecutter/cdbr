"""HTTP boundary tests for cdbrd."""

from types import SimpleNamespace

import cv2
import numpy as np
from fastapi.testclient import TestClient

import cdbr.server as server_module
from cdbr import __version__
from cdbr.core.model import CodewordPuzzle, extract_slots
from cdbr.core.photo import PhotoFormat
from cdbr.core.puzzle import UNKNOWN, CellEvidence, CellUncertainty, ClueEvidence, PuzzleObservation
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
    assert 'id="puzzle-number" type="number"' in response.text
    assert 'id="game-keyboard"' in response.text
    assert 'data-key="Backspace"' in response.text
    assert 'id="random-puzzle"' in response.text
    assert '<select id="puzzle-select">' not in response.text


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


def test_revealing_an_answer_clears_its_stale_incorrect_marker():
    script = client.get("/static/app.js").text

    single_reveal = script.index("revealed.set(symbol, hint.letter);")
    single_render = script.index("renderReference();", single_reveal)
    assert "incorrectSymbols.delete(symbol);" in script[single_reveal:single_render]

    full_reveal = script.index("revealed.set(numericSymbol, letter);")
    full_render = script.index("renderGame();", full_reveal)
    assert "incorrectSymbols.clear();" in script[full_reveal:full_render]


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
    assert revealed.json() == {"symbol": 20, "letter": "N", "solution_status": "certified"}


def test_corpus_catalog_and_random_session(monkeypatch):
    catalog = client.get("/api/puzzles")

    assert catalog.status_code == 200
    assert {"serial": 1, "title": "Puzzle 1"} in catalog.json()["puzzles"]

    monkeypatch.setattr(server_module.secrets, "choice", lambda choices: choices[0])
    created = client.post("/api/sessions/from-corpus/random")

    assert created.status_code == 201
    assert created.json()["serial"] == 1
    assert created.json()["title"] == "Puzzle 1"


def test_packaged_corpus_preserves_sparse_book_number(tmp_path, monkeypatch):
    asset = tmp_path / "puzzle-31.toml"
    asset.write_text(
        'format_version = 1\nserial = 31\ngrid = ["1 2", "## 1"]\n'
        '[clues]\n"1" = "A"\n[solution]\n"1" = "A"\n"2" = "B"\n'
    )
    monkeypatch.setattr(server_module, "PUZZLE_ROOT", tmp_path)

    catalog = client.get("/api/puzzles")
    created = client.post("/api/sessions/from-corpus/31")

    assert {"serial": 31, "title": "Puzzle 31"} in catalog.json()["puzzles"]
    assert created.status_code == 201
    assert created.json()["serial"] == 31
    assert created.json()["title"] == "Puzzle 31"


def test_check_marks_incorrect_symbols_without_revealing_answers():
    created = client.post("/api/sessions/from-corpus/1").json()

    wrong = client.post(
        f"/api/sessions/{created['session_id']}/check",
        json={"entries": {"20": "A"}},
    )
    correct = client.post(
        f"/api/sessions/{created['session_id']}/check",
        json={"entries": {"20": "N"}},
    )

    assert wrong.status_code == 200
    assert wrong.json() == {
        "checked_symbols": [20],
        "incorrect_symbols": [20],
        "solution_status": "certified",
    }
    assert correct.json()["incorrect_symbols"] == []
    assert "letter" not in wrong.text


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
    assert prepared["solution_status"] == "certified"
    assert "solution" not in prepared
    revealed = client.post(f"/api/sessions/{prepared['session_id']}/reveal/4")
    assert revealed.json() == {"symbol": 4, "letter": "D", "solution_status": "certified"}


def test_scan_job_enters_play_before_solving_and_solves_on_first_hint(monkeypatch):
    observation = PuzzleObservation(
        source=server_module.Path("upload.jpg"),
        source_format="JPEG",
        grid=((1, UNKNOWN), (3, 4)),
        clues={1: "A"},
        uncertainties=(CellUncertainty(row=1, column=2, reading="2", confidence=43.0),),
        evidence=(
            CellEvidence(row=1, column=1, reading="1", confidence=90.0, trusted=True),
            CellEvidence(row=1, column=2, reading="2", confidence=43.0, trusted=False),
            CellEvidence(row=2, column=1, reading="3", confidence=91.0, trusted=True),
            CellEvidence(row=2, column=2, reading="4", confidence=92.0, trusted=True),
        ),
        clue_evidence=(ClueEvidence(symbol=1, reading="A", confidence=100.0),),
    )
    puzzle = CodewordPuzzle(grid=((1, 2), (3, 4)), clues={1: "A"}, slots=extract_slots(((1, 2), (3, 4))))
    solved = SimpleNamespace(
        puzzle=puzzle,
        mapping={1: "A", 2: "B", 3: "C", 4: "D"},
        result=SimpleNamespace(exhausted=True, solutions=(object(),)),
    )
    monkeypatch.setattr(server_module, "detect_photo_format", lambda _: PhotoFormat.JPEG)
    monkeypatch.setattr(server_module, "recognize_photo", lambda _source, _work_dir: observation)
    grid_image = np.full((1500, 1500, 3), 255, dtype=np.uint8)
    reference_image = np.full((200, 1300, 3), 245, dtype=np.uint8)
    cv2.putText(
        reference_image,
        "B",
        (125, 82),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (20, 20, 20),
        5,
        cv2.LINE_AA,
    )

    def fake_imread(path):
        return reference_image if str(path).endswith("reference-grid.png") else grid_image

    monkeypatch.setattr(server_module.cv2, "imread", fake_imread)
    solved_observations = []

    def fake_solve_observation(corrected):
        solved_observations.append(corrected)
        return solved

    monkeypatch.setattr(server_module, "solve_observation", fake_solve_observation)

    scanned = client.post(
        "/api/scan-jobs",
        files={"photo": ("puzzle.jpg", b"pretend jpeg", "image/jpeg")},
    )

    assert scanned.status_code == 201
    review = scanned.json()
    assert review["status"] == "review"
    assert review["review_cells"] == [
        {
            "row": 1,
            "column": 2,
            "proposed": 2,
            "confidence": 43.0,
            "reason": "needs confirmation",
            "image": f"/api/scan-jobs/{review['job_id']}/cells/1/2",
        }
    ]
    assert len(review["review_clues"]) == 2
    assert review["review_clues"][0] == {
        "symbol": 1,
        "proposed": "A",
        "confidence": 100.0,
        "ink_pixels": 0,
        "image": f"/api/scan-jobs/{review['job_id']}/clues/1",
    }
    assert review["review_clues"][1]["symbol"] == 2
    assert review["review_clues"][1]["proposed"] is None
    assert review["review_clues"][1]["confidence"] == 0.0
    assert review["review_clues"][1]["ink_pixels"] >= 400
    assert review["review_clues"][1]["image"] == f"/api/scan-jobs/{review['job_id']}/clues/2"
    crop = client.get(review["review_cells"][0]["image"])
    assert crop.status_code == 200
    assert crop.headers["content-type"] == "image/jpeg"
    missed_clue_crop = client.get(review["review_clues"][1]["image"])
    assert missed_clue_crop.status_code == 200
    assert missed_clue_crop.headers["content-type"] == "image/jpeg"

    incomplete = client.post(
        f"/api/scan-jobs/{review['job_id']}/complete",
        json={"cells": [], "clues": []},
    )
    assert incomplete.status_code == 422

    missing_reference_cell = client.post(
        f"/api/scan-jobs/{review['job_id']}/complete",
        json={
            "cells": [{"row": 1, "column": 2, "value": 2}],
            "clues": [{"symbol": 1, "letter": "A"}],
        },
    )
    assert missing_reference_cell.status_code == 422
    assert "2" in missing_reference_cell.json()["detail"]

    completed = client.post(
        f"/api/scan-jobs/{review['job_id']}/complete",
        json={
            "cells": [{"row": 1, "column": 2, "value": 2}],
            "clues": [{"symbol": 1, "letter": "A"}, {"symbol": 2, "letter": "B"}],
        },
    )
    assert completed.status_code == 201
    assert completed.json()["grid"] == [[1, 2], [3, 4]]
    assert completed.json()["clues"] == {"1": "A", "2": "B"}
    assert completed.json()["provenance"] == "photo"
    assert completed.json()["solution_status"] == "not_requested"
    assert solved_observations == []

    hint = client.post(f"/api/sessions/{completed.json()['session_id']}/reveal/4")

    assert hint.json() == {"symbol": 4, "letter": "D", "solution_status": "certified"}
    assert len(solved_observations) == 1
    assert solved_observations[0].clues == {1: "A", 2: "B"}


def test_failed_lazy_solution_keeps_scanned_session_playable(monkeypatch):
    observation = PuzzleObservation(
        source=server_module.Path("discarded-upload.jpg"),
        source_format="JPEG",
        grid=((1, 2), (3, 4)),
        clues={1: "A"},
        uncertainties=(),
    )
    puzzle = {
        "title": "Scanned puzzle",
        "grid": [[1, 2], [3, 4]],
        "clues": {1: "A"},
        "symbols": list(range(1, 27)),
        "used_symbols": [1, 2, 3, 4],
        "provenance": "photo",
    }
    session = server_module._create_session(puzzle, observation=observation)
    monkeypatch.setattr(
        server_module,
        "solve_observation",
        lambda _observation: (_ for _ in ()).throw(ValueError("no solution")),
    )

    hint = client.post(f"/api/sessions/{session.session_id}/reveal/2")
    resumed = client.get(f"/api/sessions/{session.session_id}")
    revealed = client.post(f"/api/sessions/{session.session_id}/reveal")

    assert hint.status_code == 409
    assert "keep playing" in hint.json()["detail"]
    assert resumed.status_code == 200
    assert resumed.json()["solution_status"] == "unavailable"
    assert revealed.json() == {
        "mapping": {"1": "A"},
        "solution_status": "unavailable",
        "complete": False,
    }


def test_lazy_solution_uses_current_player_entries(monkeypatch):
    observation = PuzzleObservation(
        source=server_module.Path("discarded-upload.jpg"),
        source_format="JPEG",
        grid=((1, 2), (3, 4)),
        clues={1: "A"},
        uncertainties=(),
    )
    puzzle = {
        "title": "Scanned puzzle",
        "grid": [[1, 2], [3, 4]],
        "clues": {1: "A"},
        "symbols": list(range(1, 27)),
        "used_symbols": [1, 2, 3, 4],
        "provenance": "photo",
    }
    session = server_module._create_session(puzzle, observation=observation)
    solved_observations = []

    def fake_solve_observation(current):
        solved_observations.append(current)
        return SimpleNamespace(
            mapping=current.clues,
            result=SimpleNamespace(exhausted=False, solutions=()),
        )

    monkeypatch.setattr(server_module, "solve_observation", fake_solve_observation)

    first = client.post(
        f"/api/sessions/{session.session_id}/reveal",
        json={"entries": {"2": "B"}},
    )
    second = client.post(
        f"/api/sessions/{session.session_id}/reveal",
        json={"entries": {"2": "C"}},
    )

    assert first.json()["mapping"] == {"1": "A", "2": "B"}
    assert second.json()["mapping"] == {"1": "A", "2": "C"}
    assert [item.clues for item in solved_observations] == [{1: "A", 2: "B"}, {1: "A", 2: "C"}]


def test_lazy_solution_rejects_duplicate_player_letters():
    observation = PuzzleObservation(
        source=server_module.Path("discarded-upload.jpg"),
        source_format="JPEG",
        grid=((1, 2), (3, 4)),
        clues={1: "A"},
        uncertainties=(),
    )
    puzzle = {
        "title": "Scanned puzzle",
        "grid": [[1, 2], [3, 4]],
        "clues": {1: "A"},
        "symbols": list(range(1, 27)),
        "used_symbols": [1, 2, 3, 4],
        "provenance": "photo",
    }
    session = server_module._create_session(puzzle, observation=observation)

    response = client.post(
        f"/api/sessions/{session.session_id}/reveal",
        json={"entries": {"2": "B", "3": "B"}},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Each letter may be assigned to only one symbol."


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
