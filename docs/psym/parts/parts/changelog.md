### 0.2.11 — 2026-11-27

- Add an opt-in Helvetica mode that checks within-scan agreement only for cells the bank deferred.

### 0.2.10 — 2026-11-27

- Add an opt-in Helvetica-first scan path with Tesseract fallback.

### 0.2.9 — 2026-11-27

- Report the first OCR pass, retries, and within-scan digit matching separately.
- Include sampled Linux container memory in opted-in scan responses.

### 0.2.8 — 2026-11-27

- Add opt-in scan stage timings to help diagnose hosted OCR latency.

### 0.2.7 — 2026-11-27

- Preserve printed crossbars, including the Telegraph 7s, during grid-line cleanup.
- Skip manual confirmation for valid grid numbers above 90% OCR confidence.
- If a scan cannot be solved, ask the player to compare the board with the photo or retake it.

### 0.2.6 — 2026-11-26

- Retry the trailing glyph in `14` and `24` when a clean gap isolates a narrow, low-ink candidate. Suggest a confident `11` or `21` for the player to confirm.
- Keep dictionary selection and loading in the same dialog, with the loading button visible until the selected workspace opens.

### 0.2.5 — 2026-11-26

- Batch reference-clue OCR by Tesseract mode to reduce scan time.
- Flag borderline `6` and `9` reads when the block-mode retry confidently disagrees.
- Flag narrow `4` reads with little crossbar ink. Retry low-ink candidates after trimming the left side of the glyph and suggest a confident `1` for the player to confirm.

### 0.2.4 — 2026-11-26

- Batch board-number OCR by Tesseract mode to reduce process startup overhead during scan review.
- Offer explicit **Load Dictionary** when Play, Scan, or Create needs the British English dictionary. Reuse the loaded dictionary across all three modes and start the scan's solve timer after loading.
- Reveal hints and complete puzzles from certified solutions without flashing the solving overlay. Show progress for longer searches.
- Show the installed version and active dictionary in the **Codewords Breaker** footer.

### 0.2.3 — 2026-11-26

- Add Telegraph puzzles 1–10 to Play alongside the original collection. Choose a puzzle by name or use **Pick one**. Restore the three printed starting clues to original puzzles 71–100.
- Use a shared-vertex mesh and adaptive number crops on both 13×13 and 15×15 scans. Preserve the second digit, remove thin grid-rule remnants, and separate joined digits when the ink supports a split.
- Read both publishers with Tesseract first. Retry weak reads and flag disagreements using repeated numbers from the current photo. Keep historical template banks available for explicit benchmark comparisons.
- Review OCR on the playable board with source numbers, matching-number previews, and a queue for confirmed edits. Inspect any numbered cell, including readings the scanner did not flag.
- Check for a solution when accepting a scan. Distinguish a timeout from a completed search with no solution. Review again, keep searching when more time is available, or play anyway. During play, a second click on a reference cell reveals an available hint directly in both grids.
- Update the OCR guide and pipeline diagram to reflect the shared scan path and the pre-play solution check.

### 0.2.2 — 2026-11-24

- Use JPEG fixtures for Puzzle 47 geometry regression tests so release CI can run them without decoding HEIC.
- Lead the README and user docs with the hosted app at `codebreak.foghub.com` and a gameplay screenshot.

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
