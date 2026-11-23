"""Confidence-first review reports for the two photographed-puzzle OCR concerns."""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Mapping, Sequence
import html
from pathlib import Path
import tomllib
from typing import Any

import cv2
import numpy as np

from cdbr.core.recognition import WARP_SIZE


_STYLE = """
:root{--paper:#f2efe8;--bright:#fffefa;--ink:#171918;--muted:#686b66;--red:#c82d22;--green:#27725c;--line:#d8d4ca}
*{box-sizing:border-box}body{margin:0;padding:32px;font:15px/1.4 system-ui;background:var(--paper);color:var(--ink)}
header{position:sticky;top:0;z-index:3;padding:18px;background:rgba(242,239,232,.97);border-bottom:1px solid var(--line)}
h1{margin:0;font:40px Georgia,serif}header p{max-width:850px;margin:7px 0;color:var(--muted)}
a{color:var(--red);font-weight:750}.back{display:inline-block;margin-bottom:10px}.summary{display:flex;gap:12px;flex-wrap:wrap}
.metric{min-width:150px;padding:14px;background:var(--bright);border:1px solid var(--line)}.metric strong{display:block;font-size:25px}
main{max-width:1400px;margin:24px auto}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.card{padding:10px;border:1px solid var(--line);background:var(--bright)}.card.is-error{border:2px solid var(--red)}
.images{display:grid;grid-template-columns:1fr 1fr;gap:6px}.images img,.single-image img{width:100%;aspect-ratio:1;object-fit:cover;border:1px solid var(--ink)}
.single-image img{object-fit:contain}.identity{display:flex;justify-content:space-between;margin-top:7px}.confidence{font-size:20px;font-weight:800}
.badges{min-height:26px}.badge{display:inline-block;margin:3px 4px 3px 0;padding:2px 5px;background:#fde5e1;color:var(--red);font-size:11px}
.badge.ok{background:#dcebe5;color:var(--green)}.legend{font-size:12px;color:var(--muted)}
.queues{display:grid;grid-template-columns:1fr 1fr;gap:18px}.queue{padding:20px;background:var(--bright);border:1px solid var(--line)}
.queue h2{font:30px Georgia,serif;margin:0 0 8px}.queue a{font-size:19px}.queue p{color:var(--muted)}
.solution-puzzle{margin:0 0 28px;padding:18px;background:var(--bright);border:1px solid var(--line)}
.solution-puzzle h2{margin:0 0 5px;font:30px Georgia,serif}.solution-grid{display:grid;grid-template-columns:repeat(13,minmax(58px,1fr));gap:5px;margin:14px 0}
.solution-cell{display:grid;grid-template-columns:1fr 28px;gap:3px;align-items:center}.solution-cell img{width:100%;aspect-ratio:1;object-fit:cover;border:1px solid var(--line)}
.solution-cell input{width:28px;height:34px;padding:2px;text-align:center;text-transform:uppercase;font-weight:800;border:1px solid var(--line)}
.solution-cell.is-low input{border:2px solid var(--red);background:#fde5e1}.solution-cell small{grid-column:1/-1;color:var(--muted)}
.solution-actions{display:flex;gap:10px;align-items:center}.solution-actions button{padding:9px 14px;border:0;background:var(--ink);color:white;font-weight:750}.solution-output{width:100%;min-height:90px;margin-top:10px;font:12px/1.35 ui-monospace,monospace}
@media(max-width:760px){body{padding:12px}.queues{grid-template-columns:1fr}.cards{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}
"""


def _image_uri(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 84])
    if not success:
        raise ValueError("Could not encode corpus-audit image")
    return "data:image/jpeg;base64," + b64encode(encoded).decode("ascii")


def _document(*, title: str, header: str, description: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><header><a class="back" href="index.html">← Audit summary</a><h1>{html.escape(header)}</h1><p>{html.escape(description)}</p></header><main>{body}</main></body></html>"""


def _metric(value: int | float | str, label: str) -> str:
    return f'<div class="metric"><strong>{html.escape(str(value))}</strong>{html.escape(label)}</div>'


def _accuracy_metrics(summary: Mapping[str, Any], noun: str) -> str:
    coverage = int(summary.get("puzzles", 0))
    if not coverage:
        return _metric("Not scored", f"No reviewed {noun} truth yet")
    metrics = "".join(
        (
            _metric(f'{float(summary["accuracy_percent"]):.3f}%', f"{noun} accuracy"),
            _metric(int(summary["incorrect"]), "known errors"),
            _metric(int(summary["samples"]), "reviewed samples"),
            _metric(coverage, "puzzles with truth"),
        )
    )
    if noun == "clue-character":
        metrics += _metric(int(summary.get("false_positives", 0)), "false positives")
    return metrics


def _number_priority_cards(
    *,
    entries: Sequence[Any],
    results: Mapping[int, Mapping[str, Any]],
    work_root: Path,
    review_threshold: float,
) -> tuple[list[str], int]:
    records: list[tuple[int, float, int, int, int, str]] = []
    truth_puzzles = 0
    for entry in entries:
        result = results.get(entry.puzzle_id)
        if result is None or result.get("status") != "ok":
            continue
        original = cv2.imread(str(work_root / f"puzzle_{entry.puzzle_id:02d}" / "grid.png"))
        solution = cv2.imread(str(entry.solution))
        if original is None or solution is None:
            continue
        original = cv2.resize(original, (WARP_SIZE, WARP_SIZE), interpolation=cv2.INTER_CUBIC)
        solution = cv2.resize(solution, (WARP_SIZE, WARP_SIZE), interpolation=cv2.INTER_CUBIC)
        size = len(result["grid"])
        cell_size = WARP_SIZE // size
        mismatches = {
            (int(item["row"]), int(item["column"])): item
            for item in [
                *result.get("number_accuracy", {}).get("mismatches", ()),
                *result.get("number_defects", ()),
            ]
        }
        truth_puzzles += int("number_accuracy" in result)
        for item in result["evidence"]:
            row = int(item["row"])
            column = int(item["column"])
            confidence = float(item["confidence"])
            mismatch = mismatches.get((row, column))
            if bool(item["trusted"]) and confidence >= review_threshold and mismatch is None:
                continue
            original_cell = original[
                (row - 1) * cell_size : row * cell_size,
                (column - 1) * cell_size : column * cell_size,
            ]
            solution_cell = solution[
                (row - 1) * cell_size : row * cell_size,
                (column - 1) * cell_size : column * cell_size,
            ]
            badges = []
            if not item["trusted"]:
                badges.append('<span class="badge">untrusted</span>')
            if mismatch is not None:
                badges.append(f'<span class="badge">truth: {html.escape(str(mismatch["expected"]))}</span>')
            elif "number_accuracy" in result:
                badges.append('<span class="badge ok">truth agrees</span>')
            card = f"""
<article class="card{' is-error' if mismatch else ''}">
  <div class="images"><img src="{_image_uri(original_cell)}" alt="Photographed puzzle cell"><img src="{_image_uri(solution_cell)}" alt="Published solution cell, supporting evidence only"></div>
  <div class="identity"><strong>Puzzle {entry.puzzle_id} · r{row:02d}c{column:02d}</strong><span class="confidence">{confidence:.0f}%</span></div>
  <div>OCR reading: <strong>{html.escape(str(item['reading']) or 'unknown')}</strong></div><div class="badges">{''.join(badges)}</div>
</article>"""
            records.append((0 if mismatch is not None else 1, confidence, entry.puzzle_id, row, column, card))
    records.sort(key=lambda record: record[:-1])
    return [record[-1] for record in records], truth_puzzles


def _clue_priority_cards(
    *, entries: Sequence[Any], results: Mapping[int, Mapping[str, Any]], work_root: Path
) -> tuple[list[str], int]:
    records: list[tuple[int, float, int, int, str]] = []
    truth_puzzles = 0
    for entry in entries:
        result = results.get(entry.puzzle_id)
        if result is None or result.get("status") != "ok":
            continue
        mismatches = {int(item["symbol"]): item for item in result.get("clue_accuracy", {}).get("mismatches", ())}
        truth_puzzles += int("clue_accuracy" in result)
        evidence = {int(item["symbol"]): item for item in result.get("clue_evidence", ())}
        symbols = set(evidence) | set(mismatches)
        reference_grid = cv2.imread(str(work_root / f"puzzle_{entry.puzzle_id:02d}" / "reference-grid.png"))
        for symbol in symbols:
            item = evidence.get(symbol, {"reading": "", "confidence": 0.0})
            confidence = float(item["confidence"])
            mismatch = mismatches.get(symbol)
            source = work_root / f"puzzle_{entry.puzzle_id:02d}" / f"clue-source-{symbol}.jpg"
            cleaned = work_root / f"puzzle_{entry.puzzle_id:02d}" / f"clue-{symbol}.png"
            images = []
            for candidate, label in ((source, "Reference-grid cell"), (cleaned, "OCR input")):
                image = cv2.imread(str(candidate)) if candidate.exists() else None
                if image is not None:
                    images.append(f'<img src="{_image_uri(image)}" alt="{label}">')
            if not images and reference_grid is not None:
                row = 0 if symbol <= 13 else 1
                column = (symbol - 1) % 13
                cell = reference_grid[row * 100 : (row + 1) * 100, column * 100 : (column + 1) * 100]
                images.append(f'<img src="{_image_uri(cell)}" alt="Reference-grid cell missed by OCR">')
            badges = []
            if mismatch is not None:
                expected = mismatch["expected"] or "blank"
                badges.append(f'<span class="badge">truth: {html.escape(str(expected))}</span>')
            elif "clue_accuracy" in result:
                badges.append('<span class="badge ok">truth agrees</span>')
            card = f"""
<article class="card{' is-error' if mismatch else ''}">
  <div class="{'images' if len(images) == 2 else 'single-image'}">{''.join(images) or '<em>No crop was produced</em>'}</div>
  <div class="identity"><strong>Puzzle {entry.puzzle_id} · symbol {symbol}</strong><span class="confidence">{confidence:.0f}%</span></div>
  <div>OCR reading: <strong>{html.escape(str(item['reading']) or 'blank')}</strong></div><div class="badges">{''.join(badges)}</div>
</article>"""
            records.append((0 if mismatch is not None else 1, confidence, entry.puzzle_id, symbol, card))
    records.sort(key=lambda record: record[:-1])
    return [record[-1] for record in records], truth_puzzles


def _solution_glyph(cell: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
    cleaned = np.zeros_like(binary)
    for index in range(1, count):
        _, y, width, height, area = statistics[index]
        if y + height >= 68 and y >= 28 and height >= 20 and 4 <= width <= 65 and area >= 60:
            cleaned[labels == index] = 255
    points = np.argwhere(cleaned > 0)
    if not len(points):
        return None
    y_min, x_min = (int(value) for value in points.min(axis=0))
    y_max, x_max = (int(value) for value in points.max(axis=0))
    glyph = cleaned[y_min : y_max + 1, x_min : x_max + 1]
    scale = min(36 / glyph.shape[0], 36 / glyph.shape[1])
    resized = cv2.resize(
        glyph,
        (max(1, round(glyph.shape[1] * scale)), max(1, round(glyph.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )
    feature = np.zeros((40, 40), dtype=np.float32)
    y = (40 - resized.shape[0]) // 2
    x = (40 - resized.shape[1]) // 2
    feature[y : y + resized.shape[0], x : x + resized.shape[1]] = resized / 255.0
    return feature


def _reviewed_grid(result: Mapping[str, Any]) -> list[list[int | str]]:
    grid = [list(row) for row in result["grid"]]
    for mismatch in result.get("number_accuracy", {}).get("mismatches", ()):
        grid[int(mismatch["row"]) - 1][int(mismatch["column"]) - 1] = int(mismatch["expected"])
    return grid


def _solution_review_sections(
    entries: Sequence[Any], results: Mapping[int, Mapping[str, Any]]
) -> tuple[list[str], int]:
    prepared: dict[
        int, tuple[Any, dict[int, str], dict[int, str], dict[int, list[np.ndarray]], dict[int, np.ndarray]]
    ] = {}
    templates: dict[str, list[np.ndarray]] = {}
    for entry in entries:
        result = results.get(entry.puzzle_id)
        if result is None or result.get("status") != "ok" or entry.truth is None:
            continue
        with entry.truth.open("rb") as stream:
            truth = tomllib.load(stream)
        clues = {int(symbol): str(letter).upper() for symbol, letter in truth.get("clues", {}).items()}
        confirmed = {int(symbol): str(letter).upper() for symbol, letter in truth.get("solution", {}).items()}
        image = cv2.imread(str(entry.solution))
        if image is None:
            continue
        image = cv2.resize(image, (WARP_SIZE, WARP_SIZE), interpolation=cv2.INTER_CUBIC)
        grid = _reviewed_grid(result)
        size = len(grid)
        cell_size = WARP_SIZE // size
        features: dict[int, list[np.ndarray]] = {}
        crops: dict[int, np.ndarray] = {}
        for row, values in enumerate(grid):
            for column, value in enumerate(values):
                if not isinstance(value, int):
                    continue
                cell = image[
                    row * cell_size : (row + 1) * cell_size,
                    column * cell_size : (column + 1) * cell_size,
                ]
                crops.setdefault(value, cell)
                feature = _solution_glyph(cell)
                if feature is not None:
                    features.setdefault(value, []).append(feature)
        averages = {symbol: np.mean(samples, axis=0) for symbol, samples in features.items()}
        for symbol, letter in clues.items():
            if symbol in averages:
                templates.setdefault(letter, []).append(averages[symbol])
        prepared[entry.puzzle_id] = (entry, clues, confirmed, features, crops)

    sections = []
    for puzzle_id, (_entry, clues, confirmed, features, crops) in sorted(prepared.items()):
        cells = []
        for symbol in range(1, 27):
            samples = features.get(symbol, [])
            feature = np.mean(samples, axis=0) if samples else None
            scores = []
            if feature is not None:
                for letter, references in templates.items():
                    scores.append((min(float(np.mean((feature - reference) ** 2)) for reference in references), letter))
            scores.sort()
            proposed = confirmed.get(symbol) or clues.get(symbol) or (scores[0][1] if scores else "")
            margin = (scores[1][0] - scores[0][0]) / max(scores[1][0], 1e-9) if len(scores) > 1 else 0.0
            crop = crops.get(symbol)
            image_html = (
                f'<img src="{_image_uri(crop)}" alt="Published answer cell for symbol {symbol}">'
                if crop is not None
                else ""
            )
            low = not proposed or (symbol not in confirmed and symbol not in clues and margin < 0.25)
            cells.append(
                f'<label class="solution-cell{" is-low" if low else ""}">{image_html}'
                f'<input maxlength="1" pattern="[A-Za-z]" value="{html.escape(proposed)}" data-symbol="{symbol}" aria-label="Solution letter for symbol {symbol}">'
                f'<small>{symbol} · {margin * 100:.0f}%</small></label>'
            )
        state = "confirmed" if len(confirmed) == 26 else "proposal"
        sections.append(
            f'<section class="solution-puzzle" data-puzzle="{puzzle_id}"><h2>Puzzle {puzzle_id}</h2>'
            f'<p>{state.title()}: inspect each published answer crop, correct the letter, then copy the TOML.</p>'
            f'<div class="solution-grid">{"".join(cells)}</div><div class="solution-actions">'
            f'<button type="button" class="prepare-solution">Prepare approved TOML</button><span></span></div>'
            f'<textarea class="solution-output" hidden aria-label="Approved solution TOML for puzzle {puzzle_id}"></textarea></section>'
        )
    return sections, len(templates)


_SOLUTION_SCRIPT = """<script>
document.querySelectorAll('.solution-puzzle').forEach(section => {
  const inputs = [...section.querySelectorAll('input')];
  const status = section.querySelector('.solution-actions span');
  const validate = () => {
    const letters = inputs.map(input => input.value.trim().toUpperCase());
    inputs.forEach((input, index) => input.value = letters[index]);
    const complete = letters.every(letter => /^[A-Z]$/.test(letter));
    const unique = new Set(letters).size === letters.length;
    status.textContent = complete && unique ? '26 unique letters — ready' : 'Correct blanks or duplicate letters';
    return complete && unique;
  };
  inputs.forEach(input => input.addEventListener('input', validate));
  section.querySelector('.prepare-solution').addEventListener('click', async () => {
    if (!validate()) return;
    const lines = ['[solution]', ...inputs.map(input => `"${input.dataset.symbol}" = "${input.value}"`)];
    const output = section.querySelector('.solution-output');
    output.value = lines.join('\n'); output.hidden = false; output.select();
    try { await navigator.clipboard.writeText(output.value); status.textContent = 'Approved TOML copied'; } catch (_) { status.textContent = 'Approved TOML selected — copy it'; }
  });
  validate();
});
</script>"""


def write_audit_reports(
    *,
    entries: Sequence[Any],
    results: Mapping[int, Mapping[str, Any]],
    work_root: Path,
    destination: Path,
    review_threshold: float,
    number_summary: Mapping[str, Any],
    clue_summary: Mapping[str, Any],
) -> Path:
    """Write separate, confidence-first number and clue OCR reports."""

    destination.mkdir(parents=True, exist_ok=True)
    number_cards, number_truth_puzzles = _number_priority_cards(
        entries=entries,
        results=results,
        work_root=work_root,
        review_threshold=review_threshold,
    )
    clue_cards, clue_truth_puzzles = _clue_priority_cards(entries=entries, results=results, work_root=work_root)
    solution_sections, solution_template_letters = _solution_review_sections(entries, results)
    number_body = (
        '<div class="summary">'
        + _accuracy_metrics(number_summary, "number")
        + _metric(len(number_cards), f"cells below {review_threshold:.0f}% or untrusted")
        + '</div><p class="legend">Confirmed errors appear first; each tier is ordered from least to most confident. Left: puzzle photograph. Right: published solution photograph, shown only as supporting evidence.</p><div class="cards">'
        + "".join(number_cards)
        + "</div>"
    )
    clue_body = (
        '<div class="summary">'
        + _accuracy_metrics(clue_summary, "clue-character")
        + _metric(len(clue_cards), "detected or known clue positions")
        + '</div><p class="legend">Confirmed errors appear first; each tier is ordered from least to most confident. This queue measures handwritten clue-letter OCR independently of puzzle-cell numbers.</p><div class="cards">'
        + "".join(clue_cards)
        + "</div>"
    )
    (destination / "numbers.html").write_text(
        _document(
            title="cdbr number OCR audit",
            header="Puzzle-cell number OCR",
            description="Confirmed errors first, followed by confidence-first review of numbered puzzle cells. Accuracy is scored only against independently reviewed number truth.",
            body=number_body,
        )
    )
    (destination / "clues.html").write_text(
        _document(
            title="cdbr clue OCR audit",
            header="Reference-grid clue OCR",
            description="Confirmed errors first in a separate assessment of handwritten clue letters, including misses and false positives when clue truth is available.",
            body=clue_body,
        )
    )
    solution_body = (
        '<p class="legend">The published answer photographs are authoritative; proposed letters are not. '
        "Review each crop and copy the approved TOML into that puzzle's truth fixture.</p>"
        + "".join(solution_sections)
        + _SOLUTION_SCRIPT
    )
    (destination / "solutions.html").write_text(
        _document(
            title="cdbr publisher solution approval",
            header="Publisher solution approval",
            description=f"Human confirmation gate for {len(solution_sections)} solution keys, proposed from {solution_template_letters} anchored letter templates.",
            body=solution_body,
        )
    )
    index = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>cdbr corpus audit</title><style>{_STYLE}</style></head><body><header><h1>Code Break OCR audit</h1><p>Independent recognition concerns. Confirmed errors lead each queue, then confidence determines review priority; only human-reviewed fixtures contribute to accuracy.</p></header><main><div class="queues"><section class="queue"><h2>Puzzle-cell numbers</h2><div class="summary">{_accuracy_metrics(number_summary, 'number')}</div><p>{len(number_cards)} cells need attention. {number_truth_puzzles} puzzles currently have reviewed number truth.</p><a href="numbers.html">Open error-first number queue →</a></section><section class="queue"><h2>Reference-grid clues</h2><div class="summary">{_accuracy_metrics(clue_summary, 'clue-character')}</div><p>{len(clue_cards)} detected or known clue positions. {clue_truth_puzzles} puzzles currently have reviewed clue truth.</p><a href="clues.html">Open error-first clue queue →</a></section><section class="queue"><h2>Publisher solutions</h2><div class="summary">{_metric(len(solution_sections), 'answer keys awaiting or carrying truth')}</div><p>Approve proposed symbol-to-letter mappings against the published answer crops before scoring the solver.</p><a href="solutions.html">Open solution approval gate →</a></section></div></main></body></html>"""
    target = destination / "index.html"
    target.write_text(index)
    return target.resolve()
