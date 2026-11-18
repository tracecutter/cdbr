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

Regenerate README, manpage, and Sphinx projections from their canonical sources:

.. code:: bash

   make docs docs-sync

Run the web application during development:

.. code:: bash

   cdbrd --reload

The generated ``README.md``, manpages, and files under ``docs/sphinx/src/`` must not be edited directly. Update structured source docstrings, ``docs/psym/parts/``, or ``docs/psym/templates/``, then regenerate the projections.

System tests require ImageMagick and Tesseract. The project configuration in ``pyproject.toml`` is authoritative for Python dependencies and tool settings.
