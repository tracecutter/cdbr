"""
pkit.core.d2d

Distribution-to-Destination (d2d) management of non-Python artifacts for
a user environment according to a personal routing policy.

[[d2d.summary]]

Some applications bundle non-Python artifacts such as command wrappers,
man pages, examples, or templates. These artifacts are delivered to user
directories using the **Distribution-to-Destination (d2d)** mechanism.

Artifacts bundled inside a package are stored under:

    <package>/_assets/

and routed into user directories according to a personal policy defined in:

    ~/.config/d2d/routes.toml

Example configuration:

```toml
[routes]
bin = "~/.local/bin"
man = "~/.local/share/man"
```

On first run, the application will explain how to create this configuration
file if it does not already exist.

Once configured, artifact delivery happens automatically and silently.

[[d2d.overview]]

d2d installs non-Python artifacts bundled inside a Python package into
appropriate user directories according to a routing policy.

Typical artifacts include:

-   command wrappers
-   man pages
-   examples
-   templates

Artifacts are packaged inside the distribution under:

    <package>/_assets/

and declared in:

    _assets/manifest.toml

[[d2d.manifest]]

Artifacts are declared in:

    _assets/manifest.toml

Each artifact entry defines:

-   kind — destination namespace (e.g. bin, man)
-   path — relative path inside _assets

Example:

    [[artifacts]]
    kind = "man"
    path  = "man/man1/pkit.1"

Artifact paths must begin with the artifact kind.

[[d2d.routes]]

Artifact kinds are routed to destination directories according to a
user-defined routing policy.

Routes are defined in:

    ~/.config/d2d/routes.toml

Example:

    [routes]
    bin = "~/.local/bin"
    man = "~/.local/share/man"

Each route defines the destination root for that artifact kind.

[[d2d.delivery]]

During delivery, artifacts are copied from the distribution into the
destination directory while preserving their internal structure.

Example:

    _assets/man/man1/pkit.1
        ↓
    ~/.local/share/man/man1/pkit.1

This ensures compatibility with standard filesystem conventions such as
the man directory layout.

[[d2d.integration]]

Applications ensure artifacts are present by calling:

    d2d.ready("<package>")

during program startup.

If artifacts are missing or stale, d2d performs delivery automatically.

[[d2d.environment]]

d2d behaviour may be controlled using environment variables:

-   D2D_DISABLE — disable d2d entirely
-   D2D_DRYRUN — preview delivery without modifying the filesystem
-   D2D_ROUTES — override routes configuration location

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

import os
import sys
import shutil
import tomllib
import importlib
import datetime
import site
from npkglib import mark
from npkglib.mark import Marks, MarkContext

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Protocol
from collections.abc import Mapping
from textwrap import dedent

D2D_INTRO = dedent(
    """\
d2d — distribution-to-destination asset delivery

This package includes non-Python artifacts bundled inside its distribution
(such as man pages or example files). These assets need to be routed into
user directories according to a routing policy.

Assets are stored inside:

    <package>/_assets/

and declared in:

    _assets/manifest.toml

Artifact kinds are routed to destination directories. Example:

    [routes]
    bin = "~/.local/bin"
    man = "~/.local/share/man"

Routes are configured in:

    {d2d_routes_path}

You may override this location by setting:

    export D2D_ROUTES=/path/to/routes.toml

After creating routes.toml, run the package command once to perform
initial delivery. d2d will then operate silently for this package:

    {invocation} -V

To preview what d2d would install without modifying your system,
run the command again with the environment variable D2D_DRYRUN=1:

    D2D_DRYRUN=1 {invocation} -V

To disable d2d functionality entirely (including this message):

    export D2D_DISABLE=1

Environment variables:

    D2D_DISABLE    disable d2d entirely
    D2D_DRYRUN     preview delivery
    D2D_ROUTES     override routes file location

See the d2d documentation for details.
"""
)

DEFAULT_ROUTES = """\
[routes]
bin = "~/.local/bin"
man = "~/.local/share/man"
"""


# ---------------------------------------------------------------------------
# Delivery Policy
# ---------------------------------------------------------------------------


class D2DMode(Enum):
    DISABLED = auto()  # editable install safety: do nothing
    PREVIEW = auto()  # dry-run delivery
    LIVE = auto()  # real delivery


# ---------------------------------------------------------------------------
# Delivery Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    kind: str
    path: Path


class D2DEmitter(Protocol):
    marks: Marks

    def mkdir(self, path: Path) -> None: ...
    def copy(self, src: Path, kind: str, dst: Path) -> None: ...
    def log(self, kind: str, dst: Path) -> None: ...
    def changed(self) -> bool: ...
    def summarize(self) -> None: ...
    def emit(self) -> None: ...


@dataclass(frozen=True)
class D2DContext:
    pkg: str
    mode: D2DMode
    dist_root: Path
    routes: Mapping[str, str]
    artifacts: list[Artifact]
    emitter: D2DEmitter

    @property
    def dry_run(self) -> bool:
        return self.mode is D2DMode.PREVIEW

    @property
    def disabled(self) -> bool:
        return self.mode is D2DMode.DISABLED


class RoutesFileMissing(RuntimeError):
    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"d2d: routes file not found: {path}")


class RouteMissing(RuntimeError):
    def __init__(self, kind: str):
        self.kind = kind
        routes_path = _display_path(_routes_path())

        message = (
            f"d2d: no route defined for artifact kind '{kind}'.\n\n"
            f"Add the following line to your {routes_path}:\n\n"
            f"    {kind} = \"<destination-directory>\"  # e.g. ~/.local/share/{kind}"
        )

        super().__init__(message)


class _BaseEmitter:
    def __init__(self, pkg: str, marks: Marks) -> None:
        self.pkg = pkg
        self.marks = marks
        self.installed = 0

    def changed(self) -> bool:
        return self.installed > 0

    def summarize(self) -> None:
        if self.installed:
            stem = "" if self.installed == 1 else "s"
            self.marks.infos.append(f"d2d: installed {self.installed} artifact{stem}")

    def emit(self) -> None:
        if self.changed():
            self.summarize()
        self.marks.render()


class RealEmitter(_BaseEmitter):
    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def copy(self, src: Path, kind: str, dst: Path) -> None:
        shutil.copy2(src, dst)
        self.installed += 1

    def log(self, kind: str, dst: Path) -> None:
        _log_append(self.pkg, kind, dst)


class DryRunEmitter(_BaseEmitter):
    def mkdir(self, path: Path) -> None:
        self.marks.infos.append(f"[dry-run] mkdir -p {path}")

    def copy(self, src: Path, kind: str, dst: Path) -> None:
        self.marks.infos.append(f"[dry-run] copy {kind}: {src} → {dst}")
        self.installed += 1

    def log(self, kind: str, dst: Path) -> None:
        self.marks.infos.append(f"[dry-run] log {self.pkg} {kind}: {dst}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _display_path(path: Path) -> str:
    return str(path).replace(str(Path.home()), "~", 1)


def _introduce_d2d() -> None:
    d2d_routes_path = _display_path(_routes_path())
    invocation = Path(sys.argv[0]).name
    mark.configure(MarkContext(emoji=False))

    intro = D2D_INTRO.format(invocation=invocation, d2d_routes_path=d2d_routes_path)

    for line in intro.splitlines():
        if line:
            mark.info(line, no_wrap=True)
        else:
            print()


def _log_append(pkg: str, kind: str, destination: Path) -> None:
    """
    Append delivery record to install log.

    Format:
        2026-02-25T10:21:03Z pkg kind /full/path/to/file
    """

    log_path = Path.home() / ".config" / "d2d" / "install.log"
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{timestamp} {pkg} {kind} {destination}\n"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    except Exception:
        # logging must never break installation
        pass


def _editable_detect(pkg: str) -> bool:
    """
    Detect editable installs by checking whether the module
    lives outside site-packages.
    """

    mod = importlib.import_module(pkg)
    mod_file = mod.__file__

    if mod_file is None:
        raise RuntimeError(f"module '{pkg}' has no __file__")

    mod_path = Path(mod_file).resolve()

    site_paths: list[Path] = []

    try:
        site_paths.extend(Path(p).resolve() for p in site.getsitepackages())
    except Exception:
        pass

    try:
        usersite = site.getusersitepackages()
        if usersite:
            site_paths.append(Path(usersite).resolve())
    except Exception:
        pass

    for root in site_paths:
        if root == mod_path or root in mod_path.parents:
            return False  # installed

    return True  # editable / source


def _mode_resolve(pkg: str, *, dry_run: bool = False) -> D2DMode:
    if os.getenv("D2D_DISABLE") == "1":
        return D2DMode.DISABLED

    env_dry = os.getenv("D2D_DRYRUN")

    if env_dry is not None:
        return D2DMode.PREVIEW if env_dry == "1" else D2DMode.LIVE

    if dry_run:
        return D2DMode.PREVIEW

    return D2DMode.LIVE


def _context(pkg: str, mode: D2DMode, dist_root: Path) -> D2DContext:
    marks = Marks()
    emitter: D2DEmitter

    if mode is D2DMode.PREVIEW:
        emitter = DryRunEmitter(pkg, marks)
    else:
        emitter = RealEmitter(pkg, marks)

    if mode is D2DMode.DISABLED:
        return D2DContext(pkg=pkg, mode=mode, dist_root=Path(), routes={}, artifacts=[], emitter=emitter)

    artifacts = _manifest_load(dist_root)
    routes = _routes_load()

    return D2DContext(pkg=pkg, mode=mode, dist_root=dist_root, routes=routes, artifacts=artifacts, emitter=emitter)


def _routes_path() -> Path:
    env_path = os.getenv("D2D_ROUTES")

    if env_path:
        return Path(env_path).expanduser()

    return Path.home() / ".config" / "d2d" / "routes.toml"


def _dist_root(pkg: str) -> Path | None:
    """
    Locate the installed package distribution root containing _assets.

    Returns:
        Path to _assets if present, otherwise None.
    """

    mod = importlib.import_module(pkg)
    mod_file = mod.__file__

    if mod_file is None:
        raise RuntimeError(f"module '{pkg}' has no __file__")

    pkg_root = Path(mod_file).resolve().parent
    dist_root = pkg_root / "_assets"

    if not dist_root.exists():
        return None  # if operating in a cloned repository (for instance)

    return dist_root


def _dest_root(routes: Mapping[str, str], kind: str) -> Path:
    """
    Resolve destination root for an artifact kind.
    """

    dest = routes.get(kind)

    if dest is None:
        raise RouteMissing(kind)

    return Path(dest).expanduser().resolve()


def _routes_load() -> Mapping[str, str]:
    """
    Load routing configuration.

    Search order:
        1. ENV override (D2D_ROUTES)
        2. ~/.config/d2d/routes.toml
    """

    path = _routes_path()

    if not path.exists():
        raise RoutesFileMissing(path)

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise RuntimeError(f"d2d: failed to parse routes file {path} ({e})") from e

    routes = data.get("routes")

    if not isinstance(routes, dict):
        raise RuntimeError(f"d2d: invalid routes structure in {path}")

    return routes


def _manifest_load(dist_root: Path) -> list[Artifact]:
    manifest_path = dist_root / "manifest.toml"

    if not manifest_path.exists():
        raise RuntimeError(f"manifest not found: {manifest_path}")

    try:
        with manifest_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise RuntimeError(f"failed to parse manifest {manifest_path} ({e})") from e

    artifacts = data.get("artifacts")

    if not isinstance(artifacts, list):
        raise RuntimeError(f"invalid manifest structure in {manifest_path}")

    validated: list[Artifact] = []

    for entry in artifacts:

        if not isinstance(entry, dict):
            continue

        kind = entry.get("kind")
        path = entry.get("path")

        if not kind or not path:
            continue

        validated.append(
            Artifact(
                kind=kind,
                path=Path(path),
            )
        )

    if not validated:
        raise RuntimeError("manifest contains no valid artifacts")

    return validated


def _dist2dest(ctx: D2DContext) -> None:
    """
    Ferry artifacts from dist_root → routed destinations.
    """

    marks = ctx.emitter.marks

    for a in ctx.artifacts:
        try:
            src = ctx.dist_root / a.path

            if not src.exists():
                raise FileNotFoundError(f"Missing source artifact: {src}")

            dest_root = _dest_root(ctx.routes, a.kind)

            rel_path = a.path

            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise RuntimeError(f"d2d: unsafe artifact path '{rel_path}'")

            rel = a.path.relative_to(a.kind)
            dst = dest_root / rel

            ctx.emitter.mkdir(dst.parent)
            ctx.emitter.copy(src, a.kind, dst)
            ctx.emitter.log(a.kind, dst)

        except (RouteMissing, FileNotFoundError) as e:
            marks.errs.append(str(e))

        except Exception as e:
            marks.errs.append(f"Failed to deliver {a.path} ({e})")


def _operational(ctx: D2DContext) -> bool:
    """
    Return True if all artifacts exist at their routed destinations.
    """

    for a in ctx.artifacts:

        src = ctx.dist_root / a.path

        try:
            rel = a.path.relative_to(a.kind)
            dst = _dest_root(ctx.routes, a.kind) / rel
        except RouteMissing:
            return False

        if not src.exists() or not dst.exists():
            return False

    return True


def _stale(ctx: D2DContext) -> bool:
    """
    Return True if any artifact is newer than its destination.
    """

    for a in ctx.artifacts:

        src = ctx.dist_root / a.path

        try:
            rel = a.path.relative_to(a.kind)
            dst = _dest_root(ctx.routes, a.kind) / rel
        except RouteMissing:
            return False

        if not dst.exists():
            return True

        if src.stat().st_mtime > dst.stat().st_mtime:
            return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ready(pkg: str, *, dry_run: bool = False) -> None:
    """
    This function verifies and delivers distribution artifacts when available.

    If no distribution assets are present (e.g. source checkout), this function is a no-op.

    This function verifies that all artifacts declared in the package's
    ``_assets/manifest.toml`` have been delivered to their routed destinations.
    If artifacts are missing or stale, delivery is performed automatically.

    When delivery occurs, a brief summary of changes is emitted.

    If artifact delivery fails, a summary of errors is printed and the process
    aborts with ``SystemExit(1)``.

    This function enforces a runtime invariant for CLI tools using d2d and is
    intended to be called during program startup.

    Args:
        pkg:
            Top-level package name owning the distribution assets.

        dry_run:
            If True, simulate delivery without modifying the filesystem.
    """

    mode = _mode_resolve(pkg, dry_run=dry_run)

    if mode is D2DMode.DISABLED:
        return

    dist_root = _dist_root(pkg)
    if dist_root is None:
        return  # no distribution assets available → no-op

    if mode is not D2DMode.PREVIEW and _editable_detect(pkg):
        return

    try:
        ctx = _context(pkg, mode, dist_root)
    except RoutesFileMissing:
        _introduce_d2d()
        raise SystemExit(1) from None

    if _operational(ctx) and not _stale(ctx):
        return

    _dist2dest(ctx)

    ctx.emitter.emit()

    if not ctx.emitter.marks.ok():
        raise SystemExit(1)
