Developer Guide
===============

Contributing to pfig.

Overview
--------

Some applications bundle non-Python artifacts such as command wrappers, man pages, examples, or templates. These artifacts are delivered to user directories using the **Distribution-to-Destination (d2d)** mechanism.

Artifacts bundled inside a package are stored under:

::

   <package>/_assets/

and routed into user directories according to a personal policy defined in:

::

   ~/.config/d2d/routes.toml

Example configuration:

.. code:: toml

   [routes]
   bin = "~/.local/bin"
   man = "~/.local/share/man"

On first run, the application will explain how to create this configuration file if it does not already exist.

Once configured, artifact delivery happens automatically and silently.

d2d installs non-Python artifacts bundled inside a Python package into appropriate user directories according to a routing policy.

Typical artifacts include:

- command wrappers
- man pages
- examples
- templates

Artifacts are packaged inside the distribution under:

::

   <package>/_assets/

and declared in:

::

   _assets/manifest.toml

Manifest
--------

Artifacts are declared in:

::

   _assets/manifest.toml

Each artifact entry defines:

- kind — destination namespace (e.g. bin, man)
- path — relative path inside \_assets

Example:

::

   [[artifacts]]
   kind = "man"
   path  = "man/man1/pfig.1"

Artifact paths must begin with the artifact kind.

Routes
------

Artifact kinds are routed to destination directories according to a user-defined routing policy.

Routes are defined in:

::

   ~/.config/d2d/routes.toml

Example:

::

   [routes]
   bin = "~/.local/bin"
   man = "~/.local/share/man"

Each route defines the destination root for that artifact kind.

Delivery
--------

During delivery, artifacts are copied from the distribution into the destination directory while preserving their internal structure.

Example:

::

   _assets/man/man1/pfig.1
       ↓
   ~/.local/share/man/man1/pfig.1

This ensures compatibility with standard filesystem conventions such as the man directory layout.

Integration
-----------

Applications ensure artifacts are present by calling:

::

   d2d.ready("<package>")

during program startup.

If artifacts are missing or stale, d2d performs delivery automatically.

Environment
-----------

d2d behaviour may be controlled using environment variables:

- D2D_DISABLE — disable d2d entirely
- D2D_DRYRUN — preview delivery without modifying the filesystem
- D2D_ROUTES — override routes configuration location
