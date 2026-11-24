Getting Started
===============

**Play at** `codebreak.foghub.com <https://codebreak.foghub.com>`__\ **.** Open a puzzle from the collection, scan one from your book, or create your own. The hosted app runs in your browser and needs no installation or account.

Local tools
-----------

Use `cdbr` to solve and export puzzles from the terminal, or `cdbrd` to
run the web app on your own machine.

Install the command from the public Git repository into an isolated environment:

.. code:: bash

   pipx install git+https://github.com/tracecutter/cdbr.git

Image recognition also requires ImageMagick and Tesseract to be available on the host system. Developers should use the repository’s documented editable virtual-environment workflow.

Safe Exploration
----------------

cdbr never overwrites an existing solution image or puzzle file unless ``--force`` is supplied. OCR uncertainty is reported rather than silently inventing a cell value, and ``--review`` can be used to correct uncertain cells before solving.

First Command
-------------

Give cdbr a clear photograph containing the complete square puzzle and its reference grid. It detects supported 13x13 and 15x15 boards, corrects perspective, reads the numbered cells and supplied letters, then solves the substitution puzzle using a British English lexicon.

.. code:: bash

   cdbr puzzle.jpg

This prints the solved grid. Use ``--orig`` to print the recognised puzzle instead, or ``--image`` to also write ``puzzle_solved.jpg`` beside the input.

Sample Workflow
---------------

.. code:: bash

   # Solve to text
   cdbr puzzle.heic

   # Inspect the recognised puzzle as TOML
   cdbr --orig puzzle.heic

   # Review uncertain cells and write on the original photograph
   cdbr --review --image puzzle.heic

Next Steps
----------

Use ``cdbr create --help`` to construct a new puzzle, or ``cdbrd --help`` to run the local web application.
