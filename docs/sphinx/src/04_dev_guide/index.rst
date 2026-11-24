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

``make benchmark-audit`` reruns OCR and independent search, then regenerates the error-first number, reference-clue, publisher-validation, and search-outcome pages beneath ``build/corpus-audit/``. Corpus benchmarks are engineering tools and are intentionally not part of the quick ``make check`` gate. The same directory retains ``summary.json`` for before-and-after comparisons.

Approved publisher answer keys provide an independent number check. cdbr classifies each printed answer letter using templates built from the other puzzles, converts that letter through the approved symbol mapping, and compares the resulting number with fresh puzzle OCR. These publisher-derived measurements remain separate from sparse hand-reviewed truth; they may correct the simulated HIL lane only when that fresh scan actually requested human review.

Regenerate README, manpage, and Sphinx projections from their canonical sources:

.. code:: bash

   make docs docs-sync

Build and exercise the same container used by the hosted service:

.. code:: bash

   make container-check
   make container-run

``make container-check`` builds the image and probes its configured health endpoint. ``make container-run`` rebuilds and serves it in the foreground at http://127.0.0.1:8000/.

Prepare a release only after committing the intended tree and bumping the version:

.. code:: bash

   make release

The release target is deliberately interactive in the human sense: it must be invoked by the maintainer. It runs the full preflight, creates and pushes the version tag, publishes the GitHub release, and triggers release-driven web deployment when configured in ``pyproject.toml``.

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

The generated ``README.md``, manpages, and files under ``docs/sphinx/src/`` must not be edited directly. Update structured source docstrings, ``docs/psym/parts/``, or ``docs/psym/templates/``, then regenerate the projections.

System tests require ImageMagick and Tesseract. The project configuration in ``pyproject.toml`` is authoritative for Python dependencies and tool settings.
