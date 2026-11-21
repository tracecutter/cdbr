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

Start the local web application with:

.. code:: bash

   cdbrd --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle, scan a photograph into the playable board, or create a new puzzle. Uploaded photographs and game sessions are currently held only for the lifetime of the service; no database is required. Photograph recognition enters play after human review; the lexical solver runs only when a hint or solution reveal is requested. During play, select any numbered cell and type a letter to preview that entry everywhere the number occurs. Enter or selecting another number commits it, Escape cancels it, and Backspace clears a player-entered letter. The original reference clues remain visibly distinct and cannot be changed.

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
