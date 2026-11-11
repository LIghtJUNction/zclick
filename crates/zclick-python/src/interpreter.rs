//! Reject unsupported interpreters before initializing any Python-object caches.
use pyo3::PyResult;

#[cfg(not(any(PyPy, GraalPy, RustPython)))]
fn is_main_interpreter() -> bool {
    // CPython 3.10 through 3.15 assigns ID zero exclusively to its main
    // interpreter. Get/GetID are available in the stable ABI; the separate
    // PyInterpreterState_Main function is not available in the limited API.
    //
    // SAFETY: CPython calls the module's exec slot with the current thread
    // attached. Get therefore returns a valid interpreter for GetID. These
    // queries neither create Python references nor access PyO3 object caches.
    unsafe { pyo3::ffi::PyInterpreterState_GetID(pyo3::ffi::PyInterpreterState_Get()) == 0 }
}

#[cfg(not(any(PyPy, GraalPy, RustPython)))]
pub(super) fn check_main_interpreter() -> PyResult<()> {
    if !is_main_interpreter() {
        return Err(pyo3::exceptions::PyImportError::new_err(
            "zclick._native does not support subinterpreters; use the main interpreter",
        ));
    }
    Ok(())
}

// PyPy has no CPython subinterpreter API. Do not reference CPython-only symbols
// when building its extension; the other alternative runtimes use their own
// interpreter initialization model as well.
#[cfg(any(PyPy, GraalPy, RustPython))]
pub(super) fn check_main_interpreter() -> PyResult<()> {
    Ok(())
}
