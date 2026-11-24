User Guide
==========

Using cdbr effectively.

Code Break (also called Codeword) puzzles replace every letter in a crossword-like grid with a number from 1 to 26. Equal numbers represent equal letters, different numbers represent different letters, and a small reference grid supplies the starting clues.

cdbr supports four related workflows:

- recognise and solve a photographed puzzle;
- preserve the recognised board as deterministic TOML for review or testing;
- render the solution in handwriting on the source photograph; and
- construct and independently certify new 15x15 puzzles.

The companion ``cdbrd`` executable serves the same solving and generation engine through a lightweight local web application. CLI solving does not require the web service to be running.

OCR, lexical solving, puzzle construction, and presentation are separate stages. A complete solution is reported as unique only when the configured search is exhausted and exactly one solution remains under the active lexicon.

OCR Pipeline
------------

The scan pipeline is deliberately a cascade rather than one all-powerful OCR call. Each stage either contributes evidence, lowers confidence, or hands a specific decision to a human. A weak measurement is never promoted merely because a later stage would prefer a convenient answer.

**Geometry and topology.** cdbr decodes the photograph, locates the puzzle and reference grid, corrects perspective, and normalises the board to a fixed working canvas. Grid dimensions are inferred from the page format rather than assuming every publisher uses 15x15. Each cell is then classified as blocked or playable before any number recognition begins. Bad geometry is therefore a different failure from bad character recognition.

**Whole-number recognition.** A playable cell is classified as one token from 1 through 26. The primary model uses compact, publisher-specific prototypes built from human-reviewed photographs. The numbered reference grid also supplies same-page digit exemplars under the photograph’s actual font, focus, lighting, and scale. Untrusted results alone pay for the slower reference and Tesseract fallback passes; agreement can raise confidence, while disagreement remains visible.

**Ambiguity specialists.** Known visual families receive narrow additional checks rather than global heuristics. The current specialist compares reviewed neighbours for ``{6, 8, 16, 18}`` and ``{9, 19}``, verifies whether independent segmentations agree on one versus two digits, and uses an extreme upper-right ink-mass test to veto implausibly confident 6/8 decisions. These measurements can revoke trust and request review; none is allowed to rewrite a cell alone.

**Reference clues and human review.** Printed numbers and supplied clue letters are measured separately. Supplied clues are always confirmed, faint apparent blanks are surfaced, and clean blank reference cells are accepted automatically. Every untrusted puzzle number is shown with its original crop. The approved board can proceed directly to Play even if lexical solving later fails.

**Solver boundary.** Scan does not require a solution. The lexical solver starts only for a hint or full reveal and includes the player’s current entries as constraints. Solver results are not presently allowed to silently rewrite OCR. A planned confidence-fusion pass may use crossing-word evidence only inside a small OCR candidate family and must retain HIL for close decisions.

Production audits rerun the same publisher-canon path used by Scan. The explicit leave-one-out mode excludes each puzzle’s own templates to measure unseen-puzzle generalisation; it must not be presented as current gameplay. New-publisher and adverse-photography suites remain sealed until their first-pass accuracy, trusted error rate, HIL load, time, and memory have been recorded.

.. graphviz:: ../../../psym/parts/diagrams/ocr_pipeline.dot
   :caption: OCR evidence flows toward an approved playable board; uncertain evidence flows to a human, not directly to the solver.
   :align: center

Taking a scan photo
~~~~~~~~~~~~~~~~~~~

Frame one puzzle and include every corner of the board and the complete reference
strip. Flatten the page, hold the camera directly above it, and tap to focus on
the numbers. Use even light and move the camera or light source to avoid glare
and hard shadows.

cdbr can correct moderate perspective distortion and can turn a sideways photo
when it can locate the reference strip. A small batch of uncertain numbers goes
to review. If cdbr cannot read the grid, or too many numbers need review, the
web scanner asks for a fresh photo and shows these capture tips.

Puzzle Creation
---------------

Puzzle construction is available through the existing secondary mode:

.. code:: bash

   cdbr create --include PERFECT --include PETERSFIELD \
       --clues 3 --output puzzle.toml --image puzzle.png

``--include WORD`` requires a themed answer word and may be repeated. ``--exclude WORD`` prevents unwanted filler. The generator fills a 15x15 topology, selects the requested number of reference clues, and independently certifies the result with the solver.

Use ``--best-of MINUTES`` with ``--output`` to keep searching and replace the output only when a certified candidate has fewer black cells. ``--keep-candidates DIR`` archives every certified candidate for later editorial review. Generation can be computationally expensive; reproducible searches should specify ``--seed``.

Run ``cdbr create --help`` for the complete set of construction limits.

Web Application
---------------

**Play at** `codebreak.foghub.com <https://codebreak.foghub.com>`__\ **.** Open a puzzle from the collection, scan one from your book, or create your own. The hosted app runs in your browser and needs no installation or account.

Run the web app locally
~~~~~~~~~~~~~~~~~~~~~~~

Start the local web application with:

.. code:: bash

   cdbrd --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle, scan a photograph into the playable board, or create a new puzzle. Uploaded photographs and game sessions are currently held only for the lifetime of the service; no database is required. Photograph recognition asks for human review of every detected clue and any apparently blank reference cell whose measured ink approaches handwriting; clean blank cells are accepted automatically. This keeps omitted clues visible without demanding 23 routine blank confirmations. The lexical solver runs only when a hint or solution reveal is requested. During play, select any numbered cell and type a letter to preview that entry everywhere the number occurs. Enter or selecting another number commits it, Escape cancels it, and Backspace clears a player-entered letter. The letter rails above and below the board cross out letters already assigned, with a compact vowel rail repeating the same state. The one-to-one code prevents a letter being entered for two numbers. The original reference clues remain visibly distinct and cannot be changed. Check highlights incorrect player entries throughout both the puzzle and reference grid without revealing replacements. On a narrow screen the puzzle, 2x13 reference grid, and an on-screen QWERTY keyboard form one compact play surface. Two-finger pinch gestures enlarge only the puzzle board, which can then be panned without losing the reference grid. Play can select a numbered corpus puzzle or ask cdbr to choose one at random. Hint and solution requests use the player’s current entries as solver constraints and show their progress over the board; an unsuccessful search returns to the unchanged game so play can continue.

``cdbrd --reload`` is intended for local development. Container deployments should set ``PORT`` and run a single service process.

Status
------

- Python 3.11+
- British English lexical policy
- JPEG, PNG, HEIC/HEIF, AVIF, TIFF, and WebP photo input
- CLI and lightweight web application
- Experimental OCR and puzzle generation
- MIT license

OCR quality still depends on the photograph. Perspective, shadows, handwriting, and damaged grid lines can leave cells unresolved. Puzzle generation is bounded search: it retains the best certified candidate found during the chosen time, although the limit can expire without producing a certified candidate.

Links
-----

- Documentation: https://tracecutter.github.io/cdbr/
- Source: https://github.com/tracecutter/cdbr
- Issues: https://github.com/tracecutter/cdbr/issues
- Author: https://github.com/tracecutter
