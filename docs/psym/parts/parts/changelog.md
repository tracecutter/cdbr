### 0.2.1 — 2026-11-24

- Recover more small, foreshortened, and sideways puzzle grids by checking the internal grid lines after perspective correction.
- Use the sideways reference strip to orient the photo and select the board above it in a two-page shot.
- Ask for a retake when scan quality would leave an unusually large number of cells to review. Show tips for framing, angle, focus, and lighting.
- Retain conflicting clue readings for review and continue when the reference strip cannot supply a complete set of digit templates.
- Add repeatable geometry and lighting stress tests for photographed puzzles.
- Require releases to be made from `main`.

### 0.2.0 — 2026-11-24

- Expand the playable book corpus through puzzle 100 and separate zero-padded puzzle photos, solution photos, audit truth, and playable answer keys.
- Improve whole-number OCR for the 6/8, 16/18, and 9/19 confusions and send uncertain readings to review.
- Run fresh OCR and solver passes in the corpus audit, report progress, and cap each solve attempt at two minutes.
- Improve gameplay navigation with abandon confirmation and a fresh scanner when starting another scan.
- Restore two-click reference hints, warn when a hint comes from a partial result, and use current player entries when solving again.
- Reduce unnecessary blank-clue confirmations and allow revealed entries to be erased.

### 0.1.4

- Added sparse publisher-puzzle packaging and direct book-number selection
- Added human approval of publisher solution keys before solver scoring
- Separated puzzle-number, reference-clue, and publisher-solution OCR audits
- Improved mobile play with a QWERTY keyboard and board-only pinch zoom
- Added the independently generated `cdbrd(1)` service manual

### 0.1.3 — 2026-11-23

- Expanded the photographed 15x15 corpus with matching publisher solutions
- Added error-first, confidence-ordered OCR audit reports
- Added corpus solve inventory and reviewed ground-truth correction support

### 0.1.2 — 2026-11-22

- Added release-driven DigitalOcean App Platform deployment
- Measured OCR accuracy, throughput, review load, and peak memory separately
- Added focused digit-classification benchmarks and 5/6/8 counter adjudication
- Kept expensive corpus benchmarks out of routine deployment verification

### 0.1.1 — 2026-11-20

- Made release CI independent of private npkg development packages
- Installed ImageMagick and Tesseract explicitly in release CI
- Limited Tesseract threading for predictable hosted execution

### 0.1.0 — 2026-11-20

- Recognised photographed puzzles with perspective correction and conservative OCR
- Solved against a British English lexicon with partial-result reporting
- Produced text, TOML, and handwriting-on-photo output
- Generated and independently certified themed 15x15 puzzles
- Added the lightweight scan, create, and play web application
