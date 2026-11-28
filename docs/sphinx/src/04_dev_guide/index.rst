Developer Guide
===============

Contributing to cdbr.

Clone and install in editable mode:

.. code:: bash

   git clone https://github.com/tracecutter/cdbr.git
   cd cdbr
   python -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'

Run the complete validation suite:

.. code:: bash

   make check
   pytest

``make check`` validates system dependencies, generated documentation, Ruff, Black, mypy, and version lineage. ``make test`` is the equivalent short form for the default pytest run. Use ``make help`` to list the complete inherited npkg target set.

Preview the web application directly from the active development environment:

.. code:: bash

   make preview

This starts the configured ``cdbrd`` service at http://127.0.0.1:8000/ without building or running a container. It remains in the foreground until interrupted.

Run the OCR corpus benchmark, optionally limiting an experiment to a single puzzle. Benchmark targets always start again from the source photograph; cached recognition is for explicit debugging commands, never benchmark evidence:

.. code:: bash

   make benchmark
   make benchmark BENCHMARK_ARGS="--puzzle 48"
   make benchmark-audit
   make benchmark-audit BENCHMARK_ARGS="--manifest corpus/telegraph.toml --audit-dir build/telegraph-audit --summary-output build/telegraph-audit/summary.json"

``make benchmark-audit`` reruns OCR and independent search, then regenerates the error-first number, reference-clue, publisher-validation, and search-outcome pages beneath ``build/corpus-audit/``. Corpus benchmarks are engineering tools and are intentionally outside the quick ``make check`` gate. The same directory retains ``summary.json`` for before-and-after comparisons. Add ``BENCHMARK_ARGS="--no-solve"`` when collecting OCR review data alone. Use ``--solve-timeout`` to change the default 120-second budget per puzzle in each search lane. The terminal reports progress through those lanes.

The default benchmark calls the same recogniser as the web scanner. For a geometry diagnosis, call ``recognize_photo(photo, work_dir, geometry_debug=True)`` to save the corner warp, padding, traced vertex mesh, and final rectified board. Keep the source-cell crop and the actual cleaned OCR input distinct when comparing reads. Some diagnostic paths reuse the cleaned-input filename for the source crop after an untrusted read. Use the web scan endpoint when measuring production recognition. The web scanner defaults to Helvetica-first, while the standalone recognizer defaults to Tesseract-first. ``--ocr-pipeline legacy``, ``--ocr-pipeline whole-token``, and ``--no-grid-mesh`` support explicit comparisons with earlier recognition or geometry paths.

Approved publisher answer keys provide an independent number check. cdbr classifies each printed answer letter using templates built from the other puzzles, converts that letter through the approved symbol mapping, and compares the resulting number with fresh puzzle OCR. These publisher-derived measurements remain separate from sparse hand-reviewed truth; they may correct the simulated HIL lane only when that fresh scan actually requested human review. Reports call this **oracle-assisted review**: it proves that correct answers at the offered review gates are sufficient, not that a player will necessarily make them.

Regenerate README, manpage, and Sphinx projections from their canonical sources:

.. code:: bash

   make docs docs-sync

Build and exercise the same container used by the hosted service:

.. code:: bash

   make container-check
   make container-run

``make container-check`` builds the image and probes its configured health endpoint. ``make container-run`` rebuilds and serves it in the foreground at http://127.0.0.1:8000/.

Merge the intended changes into ``main``, bump the version, and commit the release tree there:

.. code:: bash

   make release

The release target is deliberately interactive in the human sense: it must be invoked by the maintainer. It runs the full preflight, creates and pushes the version tag, publishes the GitHub release, and triggers release-driven web deployment when configured in ``pyproject.toml``.

Photo geometry stress tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the grid detector on a repeatable set of 625 combinations of rotation, perspective skew, page curl, and scale:

.. code:: bash

   python -m cdbr.geometry_stress corpus/puzzle_047.jpg > stress.csv

Use ``--quick`` for a short geometry sweep or ``--lighting`` for 25 combinations of exposure and a soft shadow. Each row records the transform and whether the recovered grid has the same size and block layout as the original scan. The stress test measures geometry independently of number and clue OCR.

DigitalOcean App Platform example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

cdbr uses DigitalOcean App Platform as its first hosted deployment. The app is connected to the public GitHub repository and builds the repository ``Dockerfile``. Its HTTP service runs ``cdbrd``, listens on the platform-supplied ``PORT``, and exposes ``/health`` for container and platform health checks.

Initial platform setup is deliberately separate from normal releases:

1. Create an App Platform application from the GitHub repository and select the repository ``Dockerfile`` as the build source.
2. Disable App Platform automatic deployment on ordinary source pushes. A push to the development branch should not silently become a production release.
3. Record the application identifier as the GitHub Actions repository secret ``DIGITALOCEAN_APP_ID``.
4. Create a dedicated, least-privilege DigitalOcean API token for this release workflow and store it as ``DIGITALOCEAN_ACCESS_TOKEN``. Do not reuse a general account token.
5. Configure the production domain and any platform environment settings in App Platform. ``PORT`` is supplied by the platform and need not be committed.

The deployment boundary is a published GitHub release—not a routine Git push:

.. code:: text

   make release
       -> preflight, tests, documentation, and distribution build
       -> push the release commit and annotated version tag
       -> publish the GitHub release
       -> run .github/workflows/release.yml for that tag
       -> verify public installation, tests, container build, and /health
       -> request a forced App Platform rebuild and wait for deployment

The workflow reads ``tool.npkg.web.deploy-on`` from ``pyproject.toml``; the DigitalOcean job runs only for a published GitHub release when that value is ``release``. A manually dispatched workflow performs verification but does not deploy. Production deployments are serialized, and a failed verification never calls DigitalOcean.

The GitHub workflow builds and health-checks the production container as an independent release gate. It does not push that verification image to DigitalOcean. Instead, ``doctl apps create-deployment`` tells App Platform to rebuild its configured source with the same checked-in ``Dockerfile``. Because ``make release`` pushes the release commit before publishing the tag, the tracked production branch and released commit are aligned.

Next steps and future directions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Operate the current release.** In DigitalOcean App Platform, verify the HTTP readiness check for ``/health`` on the service port and enable a liveness probe with enough consecutive failures to tolerate brief OCR or solver load. Readiness controls traffic and liveness can restart a stuck instance. Enable failed deployment and restart-count alerts. Use the Insights graphs for memory and request duration when investigating scans that slow down. After deployment, open a corpus puzzle and run one real scan through review and play to exercise the workflow behind the health endpoint.

Send ``X-CDBR-Scan-Timing: 1`` on a ``POST /api/scan-jobs`` request to receive a ``Server-Timing`` response header on success.

.. code:: sh

   curl -sS -D - -o /dev/null -H 'X-CDBR-Scan-Timing: 1' \
     -F 'photo=@corpus/puzzle_056.jpg' https://codebreak.foghub.com/api/scan-jobs

Durations are wall-clock milliseconds. The ``scan`` total starts after the framework has parsed the multipart upload. It covers preparation, recognition, and review payload construction. The ``recognition`` and ``classify`` metrics include their sub-stages. The scan timing does not include the later solve request. Timings are emitted on the response without retaining samples or adding log entries. Omit the request header to leave timing off.

The web scanner defaults to Helvetica-first number recognition with a maximum distance of 0.16 and a minimum runner-up margin of 0.015. Set the runtime variable ``CDBR_SCAN_OCR=tesseract`` to roll back without publishing another release. Unset the variable to restore the default. The ``X-CDBR-Scan-OCR`` request header overrides the runtime setting. Use ``helvetica-deferred`` for within-scan matching only on cells deferred by the Helvetica bank. High-confidence reads still serve as comparison anchors. On Linux containers with readable cgroup counters, the same request returns ``X-CDBR-Scan-Memory`` with starting usage, sampled peak, and the finite limit when available, in bytes. The 20 ms samples cover scan preparation through review-image preparation and include other work and file cache charged to the same cgroup. For a controlled Tesseract comparison, try ``OMP_THREAD_LIMIT=1`` as a separate runtime change and repeat the same uploads.

**Make game and corpus state durable.** Active games, pending scan jobs, and newly created puzzles currently live in the server process. A restart or redeploy can interrupt that work. The packaged corpus ships with the image. Plan to store game progress, puzzle metadata, and answer keys in SQL, with source photos and derived images in Spaces. Define stable puzzle identifiers and publisher provenance before migrating the file corpus. Keep publisher and book numbers available for lookup. Add an admin review and import workflow when the storage model is ready.

**Measure scan quality from capture to play.** Keep the difficult Puzzle 47 photos as real-world regressions and use the synthetic sweeps to isolate changes in perspective, curl, and lighting. Strong curl is the next dewarping target. Score grid recovery, number and clue accuracy, review burden, retake decisions, and time separately. Check new thresholds on held-out photos and a second publisher before treating them as general. Use fresh OCR and solver passes when measuring the end-to-end experience.

The generated ``README.md``, manpages, and files under ``docs/sphinx/src/`` must not be edited directly. Update structured source docstrings, ``docs/psym/parts/``, or ``docs/psym/templates/``, then regenerate the projections.

System tests require ImageMagick and Tesseract. The project configuration in ``pyproject.toml`` is authoritative for Python dependencies and tool settings.
