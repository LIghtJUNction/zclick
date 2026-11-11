//! Group dispatch keeps Python hooks dynamic while Rust owns the invocation plan.
//! The supplied scope function executes Python's `with` statement so handled
//! exceptions, context-manager suppression, and interpreter state stay exact.
use pyo3::{
    class::{PyTraverseError, PyVisit},
    exceptions::{PyAssertionError, PyRuntimeError},
    prelude::*,
    types::{PyDict, PyList, PyTuple},
};

#[derive(Clone, Copy)]
enum Phase {
    Empty,
    Single,
    Chain,
    LeafSingle,
    LeafChain,
}

struct FrameState {
    group: Py<PyAny>,
    root_ctx: Py<PyAny>,
    active_ctx: Py<PyAny>,
    base: Py<PyAny>,
    scope: Py<PyAny>,
    args: Py<PyAny>,
    phase: Phase,
}
impl FrameState {
    fn copy(&self, py: Python<'_>, phase: Phase, active_ctx: &Bound<'_, PyAny>) -> Self {
        Self {
            group: self.group.clone_ref(py),
            root_ctx: self.root_ctx.clone_ref(py),
            active_ctx: active_ctx.clone().unbind(),
            base: self.base.clone_ref(py),
            scope: self.scope.clone_ref(py),
            args: self.args.clone_ref(py),
            phase,
        }
    }
}

// A GC-visible callable is used instead of an opaque closure capsule. A user
// hook may retain the callable through Python frame introspection; every
// captured Python reference therefore participates in cycle collection.
#[pyclass(module = "zclick._native")]
struct DispatchFrame {
    state: Option<FrameState>,
}
#[pymethods]
impl DispatchFrame {
    fn __call__(slf: &Bound<'_, Self>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let state = {
            let borrowed = slf.borrow();
            let state = borrowed
                .state
                .as_ref()
                .ok_or_else(|| PyRuntimeError::new_err("dispatch frame has been cleared"))?;
            state.copy(py, state.phase, state.active_ctx.bind(py))
        };
        // No PyRef, mutable borrow, or lock crosses the call to Python.
        let result = run_phase(py, &state)?;
        Ok(result.into_python(py)?.unbind().into_any())
    }
    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        if let Some(state) = &self.state {
            visit.call(&state.group)?;
            visit.call(&state.root_ctx)?;
            visit.call(&state.active_ctx)?;
            visit.call(&state.base)?;
            visit.call(&state.scope)?;
            visit.call(&state.args)?;
        }
        Ok(())
    }
    fn __clear__(slf: &Bound<'_, Self>) {
        let state = slf.borrow_mut().state.take();
        drop(state);
    }
}

struct Flow<'py> {
    returned: bool,
    value: Bound<'py, PyAny>,
}
impl<'py> Flow<'py> {
    fn returned(value: Bound<'py, PyAny>) -> Self {
        Self {
            returned: true,
            value,
        }
    }
    fn continued(py: Python<'py>) -> Self {
        Self {
            returned: false,
            value: py.None().into_bound(py),
        }
    }
    fn into_python(self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            [
                self.returned.into_pyobject(py)?.to_owned().into_any(),
                self.value,
            ],
        )
    }
}

fn scoped<'py>(
    py: Python<'py>,
    state: &FrameState,
    phase: Phase,
    context: &Bound<'py, PyAny>,
) -> PyResult<Flow<'py>> {
    let callback = Py::new(
        py,
        DispatchFrame {
            state: Some(state.copy(py, phase, context)),
        },
    )?;
    let output = state.scope.bind(py).call1((context, callback))?;
    let (completed, value): (bool, Bound<'py, PyAny>) = output.extract()?;
    if !completed {
        return Ok(Flow::continued(py));
    }
    let (returned, value): (bool, Bound<'py, PyAny>) = value.extract()?;
    Ok(Flow { returned, value })
}

fn finish<'py>(
    py: Python<'py>,
    state: &FrameState,
    value: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let group = state.group.bind(py);
    let ctx = state.root_ctx.bind(py);
    let callback = group.getattr("_result_callback")?;
    if callback.is_none() {
        return Ok(value);
    }
    let params = ctx.getattr("params")?;
    ctx.call_method("invoke", (callback, value), Some(params.cast::<PyDict>()?))
}
fn resolve<'py>(
    py: Python<'py>,
    state: &FrameState,
    args: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let result = state
        .group
        .bind(py)
        .call_method1("resolve_command", (state.root_ctx.bind(py), args))?;
    let resolved: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>) = result.extract()?;
    if resolved.1.is_none() {
        return Err(PyAssertionError::new_err(()));
    }
    Ok(resolved)
}
fn make_context<'py>(
    py: Python<'py>,
    state: &FrameState,
    command: &Bound<'py, PyAny>,
    name: Bound<'py, PyAny>,
    args: Bound<'py, PyAny>,
    chain: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("parent", state.root_ctx.bind(py))?;
    if chain {
        kwargs.set_item("allow_extra_args", true)?;
        kwargs.set_item("allow_interspersed_args", false)?;
    }
    command.call_method("make_context", (name, args), Some(&kwargs))
}
fn run_phase<'py>(py: Python<'py>, state: &FrameState) -> PyResult<Flow<'py>> {
    let group = state.group.bind(py);
    let ctx = state.root_ctx.bind(py);
    match state.phase {
        Phase::Empty => {
            let value = state.base.bind(py).call1((ctx,))?;
            let value = if group.getattr("chain")?.is_truthy()? {
                PyList::empty(py).into_any()
            } else {
                value
            };
            Ok(Flow::returned(finish(py, state, value)?))
        }
        Phase::Single => {
            let (name, command, remaining) = resolve(py, state, state.args.bind(py))?;
            ctx.setattr("invoked_subcommand", &name)?;
            state.base.bind(py).call1((ctx,))?;
            let child = make_context(py, state, &command, name, remaining, false)?;
            scoped(py, state, Phase::LeafSingle, &child)
        }
        Phase::Chain => {
            let mut args = state.args.clone_ref(py).into_bound(py);
            let invoked = if args.is_truthy()? {
                "*".into_pyobject(py)?.into_any()
            } else {
                py.None().into_bound(py)
            };
            ctx.setattr("invoked_subcommand", invoked)?;
            state.base.bind(py).call1((ctx,))?;
            let mut contexts = Vec::new();
            while args.is_truthy()? {
                let (name, command, remaining) = resolve(py, state, &args)?;
                let child = make_context(py, state, &command, name, remaining, true)?;
                args = child.getattr("args")?;
                child.setattr("args", PyList::empty(py))?;
                contexts.push(child);
            }
            let values = PyList::empty(py);
            for child in contexts {
                let result = scoped(py, state, Phase::LeafChain, &child)?;
                if result.returned {
                    values.append(result.value)?;
                }
            }
            Ok(Flow::returned(finish(py, state, values.into_any())?))
        }
        Phase::LeafSingle | Phase::LeafChain => {
            let child = state.active_ctx.bind(py);
            let value = child.getattr("command")?.call_method1("invoke", (child,))?;
            let value = if matches!(state.phase, Phase::LeafSingle) {
                finish(py, state, value)?
            } else {
                value
            };
            Ok(Flow::returned(value))
        }
    }
}

#[pyfunction]
pub fn invoke_group<'py>(
    py: Python<'py>,
    group: &Bound<'py, PyAny>,
    ctx: &Bound<'py, PyAny>,
    base_invoke: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut state = FrameState {
        group: group.clone().unbind(),
        root_ctx: ctx.clone().unbind(),
        active_ctx: ctx.clone().unbind(),
        base: base_invoke.clone().unbind(),
        scope: scope.clone().unbind(),
        args: py.None(),
        phase: Phase::Empty,
    };
    if !ctx.getattr("_protected_args")?.is_truthy()? {
        if group.getattr("invoke_without_command")?.is_truthy()? {
            let result = scoped(py, &state, Phase::Empty, ctx)?;
            if result.returned {
                return Ok(result.value);
            }
        }
        ctx.call_method1("fail", ("Missing command.",))?;
    }
    let args = PyList::empty(py);
    for item in ctx.getattr("_protected_args")?.try_iter()? {
        args.append(item?)?;
    }
    for item in ctx.getattr("args")?.try_iter()? {
        args.append(item?)?;
    }
    ctx.setattr("args", PyList::empty(py))?;
    ctx.setattr("_protected_args", PyList::empty(py))?;
    state.args = args.unbind().into_any();
    if !group.getattr("chain")?.is_truthy()? {
        let result = scoped(py, &state, Phase::Single, ctx)?;
        if result.returned {
            return Ok(result.value);
        }
    }
    Ok(scoped(py, &state, Phase::Chain, ctx)?.value)
}
