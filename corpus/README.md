# Puzzle corpus

Source photos use `puzzle_NNN.jpg`, where `NNN` is the zero-padded book number.
The benchmark manifest points to the numbered photos it covers. Playable
number grids and starting clues are packaged under `cdbr/assets/puzzles/`.

Solution photos and audit truth live in the separate `solutions/` directory
at the repository root. The manifest records their paths.
OCR can run from the public photos alone. Publisher comparisons and approval
workflows require the local solution files.

To override the server's answer keys, set `CDBR_SOLUTIONS_DIR` to a directory of
answer TOMLs named after the packaged puzzle files. Local development defaults
to `solutions/playable/` relative to the working directory. Without a key,
the app uses the solver for checks and reveals.
