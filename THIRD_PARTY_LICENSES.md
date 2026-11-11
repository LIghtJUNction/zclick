# Third-party licenses and notices

zclick's own implementation is licensed under the MIT license in [LICENSE](LICENSE).
The native extension is built from Rust crates whose unmodified license and
copyright notices are included below. Both alternatives of dual-license notices
are retained. SPDX expressions, exact registry versions, archive checksums, and
copied-file checksums are recorded in [licenses/manifest.json](licenses/manifest.json).

## Locked Rust crates

This inventory covers every registry crate resolved by `cargo metadata --locked`,
including host build dependencies and procedural macros. Inclusion of a notice
does not imply that every listed crate contributes executable code to every wheel.
The semantic core directly depends on zclap; the Python binding depends on PyO3.
These native/build dependencies are distinct from Python installation dependencies.

| Package | Upstream SPDX expression | Unmodified notices |
| --- | --- | --- |
| [heck 0.5.0](https://crates.io/crates/heck/0.5.0) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/heck-0.5.0/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/heck-0.5.0/LICENSE-MIT) |
| [libc 0.2.191](https://crates.io/crates/libc/0.2.191) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/libc-0.2.191/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/libc-0.2.191/LICENSE-MIT) |
| [once_cell 1.21.4](https://crates.io/crates/once_cell/1.21.4) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/once_cell-1.21.4/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/once_cell-1.21.4/LICENSE-MIT) |
| [portable-atomic 1.15.0](https://crates.io/crates/portable-atomic/1.15.0) | `Apache-2.0 OR MIT` | [LICENSE-APACHE](licenses/rust/portable-atomic-1.15.0/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/portable-atomic-1.15.0/LICENSE-MIT) |
| [proc-macro2 1.0.107](https://crates.io/crates/proc-macro2/1.0.107) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/proc-macro2-1.0.107/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/proc-macro2-1.0.107/LICENSE-MIT) |
| [pyo3 0.30.1](https://crates.io/crates/pyo3/0.30.1) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/pyo3-0.30.1/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-0.30.1/LICENSE-MIT), [LICENSE-APACHE](licenses/rust/pyo3-0.30.1/pyo3-runtime/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-0.30.1/pyo3-runtime/LICENSE-MIT) |
| [pyo3-build-config 0.30.1](https://crates.io/crates/pyo3-build-config/0.30.1) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/pyo3-build-config-0.30.1/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-build-config-0.30.1/LICENSE-MIT) |
| [pyo3-ffi 0.30.1](https://crates.io/crates/pyo3-ffi/0.30.1) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/pyo3-ffi-0.30.1/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-ffi-0.30.1/LICENSE-MIT) |
| [pyo3-macros 0.30.1](https://crates.io/crates/pyo3-macros/0.30.1) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/pyo3-macros-0.30.1/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-macros-0.30.1/LICENSE-MIT) |
| [pyo3-macros-backend 0.30.1](https://crates.io/crates/pyo3-macros-backend/0.30.1) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/pyo3-macros-backend-0.30.1/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/pyo3-macros-backend-0.30.1/LICENSE-MIT) |
| [quote 1.0.47](https://crates.io/crates/quote/1.0.47) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/quote-1.0.47/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/quote-1.0.47/LICENSE-MIT) |
| [syn 3.0.10](https://crates.io/crates/syn/3.0.10) | `MIT OR Apache-2.0` | [LICENSE-APACHE](licenses/rust/syn-3.0.10/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/syn-3.0.10/LICENSE-MIT) |
| [target-lexicon 0.13.5](https://crates.io/crates/target-lexicon/0.13.5) | `Apache-2.0 WITH LLVM-exception` | [LICENSE](licenses/rust/target-lexicon-0.13.5/LICENSE) |
| [unicode-ident 1.0.27](https://crates.io/crates/unicode-ident/1.0.27) | `(MIT OR Apache-2.0) AND Unicode-3.0` | [LICENSE-APACHE](licenses/rust/unicode-ident-1.0.27/LICENSE-APACHE), [LICENSE-MIT](licenses/rust/unicode-ident-1.0.27/LICENSE-MIT), [LICENSE-UNICODE](licenses/rust/unicode-ident-1.0.27/LICENSE-UNICODE) |
| [zclap 0.1.4](https://crates.io/crates/zclap/0.1.4) | `MIT` | [LICENSE](licenses/rust/zclap-0.1.4/LICENSE) |

## Rust standard library 1.99.1

Native wheels can contain statically linked parts of Rust's standard library.
The pinned compiler is built from commit `58cf8f9c35b355199727627d07ae34a4e2846d67`.
The complete [standard-library copyright inventory](licenses/rust-standard-library/1.99.1/COPYRIGHT-library.html)
is retained, including its in-tree and third-party notices. The upstream
[MIT license](licenses/rust-standard-library/1.99.1/LICENSE-MIT),
[Apache 2.0 license](licenses/rust-standard-library/1.99.1/LICENSE-APACHE), and
[copyright overview](licenses/rust-standard-library/1.99.1/COPYRIGHT) are also included.
The inventory is deliberately broader than one platform's linked symbol set.

## Click interface declarations and comparison material

The `.pyi` interface declarations are extracted from the fixed Click 8.5.1 public
interface. Their source project's BSD-3-Clause notice is distributed at
[compatibility/CLICK_LICENSE.txt](compatibility/CLICK_LICENSE.txt).
The Python runtime implementation is independent; original Click is not a runtime
dependency and is not embedded as a fallback. Vendored comparison source used by
development tests is excluded from the wheel.

## Python dependency boundary

The default distribution declares zero third-party Python runtime dependencies.
Click, pytest, Hypothesis, Maturin, type-checking tools, and optional extension-test
packages belong to development environments. Optional test extras remain explicitly
marked in distribution metadata and are not installed by `pip install zclick`.

## Maintenance and verification

Run `python scripts/vendor_licenses.py --check` after fetching the pinned Cargo
dependencies. To refresh generated notices, run the script without `--check`.
It uses locked metadata and refuses changes to `Cargo.lock`; it adds no dependency.
When the Rust toolchain changes, fetch the three indicated upstream license files
for that release before regeneration. Wheel verification checks that every notice
recorded in the manifest is present with the same checksum.
