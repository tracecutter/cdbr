Getting Started
===============

pfig helps you inspect and manage your project configuration from the command line.

Installation
------------

.. code:: bash

   pip install pfig    # or pipx

See the User Guide for installation options and tradeoffs.

Safe Exploration
----------------

Most pfig commands support –dry-run, which shows what would change without modifying your project. When exploring, it’s a good idea to start with –dry-run until you’re comfortable with the results.

First Command
-------------

To start:

.. code:: bash

   pfig --help

Sample Workflow
---------------

A typical workflow might look like this:

.. code:: bash

   pfig add --dry-run nifty-package
   pfig bump --dry-run minor
   pfig docs readme
   pfig --quiet lint

Next Steps
----------

See the User Guide for more detailed workflows.
