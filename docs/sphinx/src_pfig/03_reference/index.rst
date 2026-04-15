Reference
=========

Command and option reference.


.. code-block:: text

   Usage:  [OPTIONS] COMMAND [ARGS]...

     Inspect and update Python project configuration.

     `pfig` works directly with pyproject.toml as the single source of truth. It
     provides conservative, diffable commands for dependency management,
     integrity validation, versioning, and documentation workflows.

     Run `pfig <command> --help` for command-specific help.

     See `man pfig add` or the user guide for full documentation.

     Full documentation: https://tracecutter.github.io/pfig/

   Options:
     -f, --file PATH       Project configuration file.  [default: pyproject.toml]
     -q, --quiet           Suppress output.
     -v, --verbose         Verbose output.
     --trace               Enable trace instrumentation.
     --telemetry           Enable telemetry instrumentation.
     --layout [1up|nup]    Output layout.  [default: 1up]
     --emoji / --no-emoji  Enable emoji prefixes in output. [default: true]
     --diff {2up|lines}    Diff output format.  [default: 2up]
     -V, --version         Show the version and exit.
     -h, --help            Show this message and exit.

   Commands:
     add      Append dependency or resource entries in pyproject.toml.
     bump     Increment the project version in pyproject.toml.
     docs     Generate documentation artifacts for the project.
     get      Retrieve dependency or resource entries from pyproject.toml.
     help     Display help for pfig or a named subcommand.
     lint     Audit project intent, environment, and release readiness.
     remove   Remove dependency or resource entries from pyproject.toml.
     restate  Normalize dependency version floors to current releases.


