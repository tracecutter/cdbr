Reference
=========

Command and option reference.


.. code-block:: text

   Usage:  [OPTIONS] PHOTO

     Read and solve a Code Break puzzle from PHOTO.

     PHOTO must include the complete puzzle grid and reference grid. By default
     cdbr prints the best text solution to standard output.

   Options:
     -q, --quiet           Suppress non-error output.
     -v, --verbose         Enable diagnostic output.
     --trace               Enable trace instrumentation.
     --telemetry           Enable telemetry instrumentation.
     --emoji / --no-emoji  Enable emoji prefixes in output.
     --review              Interactively review uncertain cells.
     --solve               Print the text solution (the default).
     -o, --orig            Print the recognised original puzzle as TOML.
     -i, --image           Also write the solved photograph; optionally pass
                           PATH.
     -f, --force           Overwrite an existing solution image.
     -V, --version         Show the version and exit.
     --help                Show this message and exit.

     Create puzzles with 'cdbr create --help'. Run the web app with 'cdbrd
     --help'.


The existing secondary command is documented separately because the current
CLI preserves direct ``cdbr PHOTO`` compatibility.

.. code-block:: text

   cdbr create --help

The companion web-service executable provides its own live help:

.. code-block:: text

   cdbrd --help

