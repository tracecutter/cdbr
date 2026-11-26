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

The default scan path is shared by the CLI, the web app, and the corpus benchmark. Both the 13×13 Telegraph and the original 15×15 puzzles use the shared-vertex mesh, adaptive number crops, and Tesseract-first recognition.

**1. Decode, locate, and dewarp.** ImageMagick reads the photograph, applies its orientation metadata, and caps the longest side at 1,600 pixels without enlarging smaller images. OpenCV looks for the board outline and uses the internal rules to infer the grid size. If the reference strip is sideways, cdbr tries both quarter turns and looks for the board above the strip. The initial perspective warp preserves a margin around the board. Within that padded image, cdbr traces horizontal and vertical rules, using both dark lines and the edges of solid blocks. Their intersections form a mesh whose vertices are shared by neighbouring cells. The mesh remaps the board onto an evenly spaced 1,500-pixel square before slicing it into cells. This corrects local page curl that a four-corner transform alone leaves behind. The current mesh samples the padded perspective warp of the working image.

**2. Find the number ink.** cdbr first separates blocked and playable cells. It searches a bounded top-left region of each playable cell for digit ink. The adaptive crop suppresses horizontal and vertical rules, retains plausible components including a second digit or a broken leading 1, and fits the crop to the retained ink. It trims thin overhangs attached near the top and inserts a white gap when the ink distribution supports two digits. Tesseract receives the cleaned, enlarged glyphs on a white margin. The review interface shows the rectified source cell so the player can judge what was printed.

**3. Read and cross-check numbers.** Tesseract reads each cleaned cell as a single line (PSM 7) with a digit whitelist. A missing, out-of-range, or low-confidence reading gets retries in modes for a block (6), a word (8), a character (10), and a raw line (13). For wider cells with weak results, a further retry masks a narrow top strip. Values must be in 1–26, and the default trust threshold is 80 on Tesseract’s confidence scale. cdbr compares repeated numbers within the same scan using high-confidence crops as examples. Two close matches that favour another number can flag a confident reading for review or supply a suggestion for a weak reading. The reviewer decides whether to change the board. The older template-bank modes are explicit benchmark options. PaddleOCR was evaluated as an experiment.

**4. Read the starting clues.** The 2×13 reference strip is located and rectified separately. Its row and column identify the code number, and Tesseract looks for the large printed letter with an A–Z whitelist. Ink checks distinguish printed letters and suspicious blanks from clean empty squares. The web review asks the player to confirm the detected clues and inspect suspicious blanks, and enforces distinct letters across the clues.

**5. Review and accept.** The web app opens the rectified board with red outlines around queued cells. **Show scanned numbers** overlays the source numbers so the player can compare them with OCR, including unflagged readings. Selecting a number highlights matching cells. Click a blue match to preview its source crop and click it again to edit. Confirm each queued cell and any additional corrections before choosing **Accept Scan**. The browser requests a retake when it cannot prepare the board or reference strip, or when at least 20 numbers need review and those numbers exceed a quarter of the playable cells. The CLI writes a TOML observation and offers optional interactive review.

**6. Check solvability before Play.** After the web player accepts the scan, the lexical solver checks the reviewed board with an initial 10-second budget. After a timeout, **Keep searching** can start a fresh search with a 30-second budget and then a 120-second budget. When the search exhausts the current dictionary without a solution, **Check the scan?** prompts the player to verify the numbers and starting clues. An interrupted search with no further retry reports that it reached a limit. The player can return to review or choose **Play anyway** in either case. A complete mapping is certified only when the search is exhausted with exactly one solution. In Play, hints and reveals can use the player’s current entries after the entry check. The solver works on the approved numbers and clues.

.. graphviz:: ../../../psym/parts/diagrams/ocr_pipeline.dot
   :caption: The web scan starts with the shared recogniser and checks the reviewed board before play.
   :alt: A photograph branches into board-number OCR and reference-clue OCR. The results meet at scan review. Accepting the scan checks for a solution before play.
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

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle, scan a photograph into the playable board, or create a new puzzle. Uploaded photographs and game sessions are currently held only for the lifetime of the service; no database is required. A successful scan opens a board review. Accepting the scan checks for a complete solution before play, with the option to review again or play anyway if the search cannot finish. During play, select any numbered cell and type a letter to preview that entry everywhere the number occurs. Enter or selecting another number commits it, Escape cancels it, and Backspace clears a player-entered letter. The letter rails above and below the board cross out letters already assigned, with a compact vowel rail repeating the same state. The one-to-one code prevents a letter being entered for two numbers. The original reference clues remain visibly distinct and cannot be changed. Check highlights incorrect player entries throughout both the puzzle and reference grid without revealing replacements. On a narrow screen the puzzle, 2x13 reference grid, and an on-screen QWERTY keyboard form one compact play surface. Two-finger pinch gestures enlarge only the puzzle board, which can then be panned without losing the reference grid. In Play, choose a named puzzle from either collection or use **Pick one** to open a random board. Packaged puzzles start with their printed clues. Click the same reference cell twice to put a hint directly on both grids when a letter is available. Hint and reveal requests can search from checked player entries, and show progress over the board. A tentative hint carries a warning in the game panel.

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
