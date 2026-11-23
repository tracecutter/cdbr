# psym feature requests

## Generated visual documentation without drift

### Summary

Extend psym so documentation can include diagrams, images, and application
screenshots generated from the program as part of the normal documentation
build.

The governing requirement is the same as for textual psym symbols: **the
documentation must not drift from the implementation**. A visual should be a
projection of program state, configuration, or an executable fixture—not a
separate hand-maintained description of the program.

### Motivation

psym already separates semantic truth from presentation. Documentation facts
live close to the code and each backend presents them in an appropriate voice:

- command help is terse and operational;
- manpages are formal reference material;
- README files provide orientation and quick-start workflows; and
- Sphinx provides expansive explanation and theory of operation.

Visual material should follow the same model. A flow diagram or screenshot can
communicate relationships that prose cannot, but manually produced assets
reintroduce exactly the drift that psym exists to prevent.

Useful examples include:

- CLI and subcommand topology;
- application state and workflow diagrams;
- processing pipelines;
- package and service dependency graphs;
- release and deployment flows;
- generated examples and output images; and
- deterministic browser screenshots of important application states.

### Proposed model

A visual asset should have three distinct layers:

1. **Source** — program metadata, configuration, structured psym symbols, or an
   executable documentation fixture.
2. **Generator** — a declared, reproducible operation that produces an SVG,
   PNG, or other supported artifact.
3. **Projection** — backend-specific presentation of that artifact.

The visual's identity and meaning should be represented in the psym symbol
universe. Backends may then make different editorial choices without duplicating
the source:

- Sphinx may embed an SVG Graphviz diagram with a caption and surrounding
  explanation;
- README may include a selected PNG or SVG at a constrained width;
- a manpage may omit the image and render a compact textual equivalent from the
  same source symbols; and
- command help should normally omit visual material entirely.

The system should distinguish between a visual's semantic source and its
rendered files. Generated files are build artifacts, even when selected outputs
are checked into the repository for GitHub or package-distribution purposes.

### Graphviz diagrams

Graphviz is a sensible first implementation because it is deterministic,
well-supported by Sphinx, and naturally represents graphs and state
transitions.

psym could support a visual declaration that identifies:

- a stable asset name;
- a generator or structured data source;
- output formats required by each backend;
- optional caption and alternative-text symbols; and
- the backends in which the visual may appear.

The important constraint is that the DOT graph should itself be derived from
authoritative structures wherever practical. For example:

- CLI diagrams should derive from the inspected `CLISpec`;
- package graphs should derive from `pyproject.toml` dependency metadata;
- deployment graphs should derive from npkg web configuration and workflow
  policy; and
- application-state diagrams should derive from a declared state model rather
  than a second informal drawing of that model.

Hand-authored DOT may remain useful for genuinely conceptual diagrams, but it
should be identified as authored documentation rather than implementation-derived
evidence.

### Deterministic screenshots

Browser screenshots are a valuable second milestone. They should be generated
from executable documentation fixtures rather than from an author's current
session.

A deterministic screenshot requires control of at least:

- application input and seed data;
- URL and application state;
- browser engine and viewport dimensions;
- fonts and device scale factor;
- time, locale, and timezone where visible;
- animation and transition state;
- random identifiers and network-dependent content; and
- capture timing and readiness criteria.

Applications may need a documentation-only fixture or route that establishes a
named state without performing expensive or nondeterministic work. Such a
fixture must exercise the real presentation code and should not become a second
implementation of the UI.

Screenshot generation should support multiple named viewports—for example,
desktop and mobile—without implying that every backend must publish every
capture.

### Build integration

Visual generation should participate in the existing psym lifecycle:

```text
authoritative program/configuration state
    -> psym symbol collection
    -> visual generators
    -> backend projection
    -> README, manpage, and Sphinx artifacts
```

`make docs` should generate required visual assets before rendering templates.
`make docs-sync` should promote only the outputs intended to live in the
repository. The documentation audit should detect:

- missing declared assets;
- unresolved visual symbols;
- generator failures;
- references to stale or undeclared files; and
- differences between regenerated assets and checked-in projections.

Exact byte comparison may be unsuitable for formats containing unstable
metadata. psym should either normalise such output or provide a semantic/pixel
comparison policy with an explicit tolerance. Deterministic SVG should normally
be compared as normalised text.

Generated assets should be cached by a digest of their declared inputs,
generator version, and relevant environment. Expensive screenshot capture should
not rerun when none of those inputs changed.

### Possible symbol interface

The precise interface needs experimentation, but a visual symbol should be able
to expose at least:

- stable name;
- title or caption;
- alternative text;
- provenance (`derived`, `fixture`, or `authored`);
- generator identity;
- source/input digest;
- available output formats;
- output paths; and
- backend suitability.

Templates should refer to the logical visual rather than hard-code a generated
path. A backend can then choose the correct format and markup.

### Incremental delivery

1. Generate one SVG Graphviz asset from structured psym data and embed it in
   Sphinx.
2. Add README projection and a textual manpage fallback from the same symbols.
3. Add asset manifests, caching, and stale-output auditing.
4. Add a deterministic browser-screenshot generator with one fixed viewport.
5. Add named application fixtures and multiple viewport projections.
6. Add optional pixel/semantic regression reporting for changed screenshots.

### Acceptance criteria

- A clean checkout can build all declared visuals through the normal docs
  command.
- Rebuilding unchanged documentation produces no asset differences.
- Changing authoritative source data changes the corresponding visual or fails
  the documentation audit.
- Templates refer to logical visual symbols rather than backend-specific file
  paths.
- Sphinx, README, manpage, and help backends may use different presentations of
  the same semantic source.
- Missing tools produce an actionable dependency error rather than silently
  omitting a visual.
- Expensive captures are cached without allowing stale artifacts to pass the
  audit.

## pfig: project metadata with multiple entry points

### Problem

`pfig get project.version` and related project metadata queries need a clear,
stable interpretation when `[project.scripts]` contains multiple entry points.

A Python distribution has one `[project]` table and one project version,
regardless of how many console scripts it exports. The presence of both `cdbr`
and `cdbrd`, for example, should not make `project.version` ambiguous or require
pfig to select a canonical executable before returning distribution metadata.

Entry-point selection is relevant to CLI inspection and executable-specific
documentation, but it is orthogonal to distribution-level keys such as:

- `project.name`;
- `project.version`;
- `project.description`;
- `project.license`; and
- dependency metadata.

### Desired behaviour

```bash
pfig get project.version
```

should read and return `[project].version` directly, whether the project defines
zero, one, or many scripts.

Executable-specific queries should require or accept an explicit invocation
only when the requested value actually depends on an entry point. Possible
interfaces include:

```bash
pfig get project.scripts
pfig get project.scripts.cdbrd
pfig get invocation --script cdbrd
```

The exact spelling is less important than maintaining the distinction between:

- **distribution metadata**, which is singular and comes from `[project]`; and
- **entry-point metadata**, which may be plural and must not be resolved
  implicitly when ambiguity matters.

If a legacy command genuinely requires one canonical invocation, pfig should
either use a declared project policy or report an actionable ambiguity. It
should not let that ambiguity leak into unrelated `pfig get` operations.

### Acceptance criteria

- `pfig get project.version` returns the same value for projects with zero, one,
  or multiple `[project.scripts]` entries.
- General dotted-key lookup does not initialise CLI inspection unnecessarily.
- Script-specific inspection can select an entry point explicitly.
- Ambiguous executable-specific requests fail with a useful message listing the
  available entry points.
- Existing single-entry-point projects remain compatible.
