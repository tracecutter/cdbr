# cdbr backlog

## OCR

- Reorder number recognition into a confidence-gated cascade. First classify
  each whole puzzle-cell number against the sequentially labelled `1-26`
  exemplars cropped from that photograph's reference grid. If ambiguous, add
  reviewed templates from the same publisher/font family with small alignment,
  blur, and threshold variations; then consult digit classification, Tesseract,
  and structural features such as enclosed-counter counts. Fuse independent
  evidence rather than allowing any single stage to overwrite the others, and
  retain human review when the final margin remains small. Benchmark this
  whole-token-first design against the current pipeline for accuracy, latency,
  and review volume.
- Fix systematic `E → F` recognition in publisher solution grids. Human review
  corrected 17 of 19 proposed solution-key errors across the 39-puzzle corpus;
  retain these crops as the focused regression set and verify that improving `F`
  recall does not reduce `E` precision.
- Add a constrained lexical adjudication pass for established OCR confusion
  families, initially `6/8` and therefore `16/18`. Deliberately widen the visual
  ambiguity band rather than forcing an early OCR decision: preserve both
  readings with their visual likelihoods, then combine those likelihoods with
  the ordinary-word support each receives from every crossing slot. Promote a
  reading only when the fused evidence crosses a conservative threshold and is
  materially stronger than its alternative; otherwise leave the cell for human
  review. Never use an unconstrained solver result to silently rewrite arbitrary
  OCR.
