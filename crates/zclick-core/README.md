# zclick-core

The Rust argument semantics and terminal formatting library used by zclick.
It builds with `no_std` plus `alloc`, forbids unsafe Rust, and uses
[zclap](https://crates.io/crates/zclap) for argument recognition.

```toml
[dependencies]
zclick-core = "=0.1.1-alpha.3"
```

The public API includes `Schema`, `Spec`, `parse`, `parse_with_normalizer`,
parameter occurrence and value types, processing-order helpers, and terminal
text functions such as `strip_ansi`, `text_width`, `wrap_text`, and
`truncate_visible`. Invocation inputs and parser borrows remain local to each
call; callers may reuse their own immutable schemas.

This crate supplies the Rust kernel. Python decorators, command objects,
interpreter integration, and the Python `click` compatibility layer live in
the separately distributed [zclick package](https://github.com/LIghtJUNction/zclick).
The Rust version is a prerelease API and should be pinned when integrating it.

## Verification and publication

From a clean checkout of the repository:

```sh
python3 scripts/publish_core.py
```

This runs the Rust core tests, a WebAssembly `no_std` compile, strict Clippy,
and Cargo's packaged-source build. To publish a tested main revision with
existing Cargo registry credentials:

```sh
python3 scripts/publish_core.py --publish
```

Publication requires the clean candidate to match origin/main. It uploads only
`zclick-core` and records the source under `zclick-core-v<VERSION>`.
The Python release workflow and versioning remain separate.

MIT license; see LICENSE.
