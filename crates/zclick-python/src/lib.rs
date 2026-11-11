//! CPython object adaptation. Pure parsing/formatting lives in zclick-core.
use pyo3::{
    exceptions::{PyTypeError, PyValueError},
    prelude::*,
    types::{PyBytes, PyDict, PyList, PyString, PyTuple},
};
use zclick_core::{self as core, Spec};
mod dispatch;

fn encode(value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let text = value.cast::<PyString>()?;
    if let Ok(valid) = text.to_str() {
        return Ok(valid.as_bytes().to_vec());
    }
    let bytes = value
        .py()
        .get_type::<PyString>()
        .call_method1("encode", (value, "utf-8", "surrogatepass"))?;
    Ok(bytes.cast::<PyBytes>()?.as_bytes().to_vec())
}
fn decode<'py>(py: Python<'py>, bytes: &[u8]) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(text) = std::str::from_utf8(bytes) {
        return Ok(PyString::new(py, text).into_any());
    }
    Ok(PyString::from_encoded_object(
        &PyBytes::new(py, bytes),
        Some(c"utf-8"),
        Some(c"surrogatepass"),
    )?
    .into_any())
}
fn strings(values: &Bound<'_, PyAny>) -> PyResult<Vec<Vec<u8>>> {
    values.try_iter()?.map(|v| encode(&v?)).collect()
}

fn read_specs(specs: &Bound<'_, PyAny>) -> PyResult<Vec<Spec>> {
    specs
        .try_iter()?
        .map(|item| {
            let item = item?;
            let count = item.len()?;
            if count != 4 && count != 5 {
                return Err(PyTypeError::new_err(
                    "a parser specification must have 4 or 5 fields",
                ));
            }
            Ok(Spec {
                id: item.get_item(0)?.extract()?,
                options: strings(&item.get_item(1)?)?,
                nargs: item.get_item(2)?.extract()?,
                is_flag: item.get_item(3)?.extract()?,
                optional_value: if count == 5 {
                    item.get_item(4)?.extract()?
                } else {
                    false
                },
            })
        })
        .collect::<PyResult<_>>()
}

struct Inputs<'py> {
    originals: Vec<Bound<'py, PyAny>>,
    bytes: Vec<Vec<u8>>,
    index: std::collections::HashMap<(usize, usize), usize>,
}
impl<'py> Inputs<'py> {
    fn new(argv: &Bound<'py, PyAny>) -> PyResult<Self> {
        let originals = argv.try_iter()?.collect::<PyResult<Vec<_>>>()?;
        let mut bytes = originals.iter().map(encode).collect::<PyResult<Vec<_>>>()?;
        // Empty Vecs otherwise share a dangling pointer; unique storage retains
        // the identity of distinct empty str subclasses passed as argv values.
        for value in &mut bytes {
            if value.is_empty() {
                value.reserve_exact(1);
            }
        }
        let index = bytes
            .iter()
            .enumerate()
            .map(|(i, s)| ((s.as_ptr() as usize, s.len()), i))
            .collect();
        Ok(Self {
            originals,
            bytes,
            index,
        })
    }
    fn restore(&self, py: Python<'py>, bytes: &[u8]) -> PyResult<Bound<'py, PyAny>> {
        if let Some(&index) = self.index.get(&(bytes.as_ptr() as usize, bytes.len())) {
            Ok(self.originals[index].clone())
        } else {
            decode(py, bytes)
        }
    }
}
fn native_error<'py>(
    py: Python<'py>,
    error: Option<core::ParseError>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok(if let Some(error) = error {
        let details = PyDict::new(py);
        details.set_item("kind", error.kind)?;
        details.set_item("option", decode(py, &error.option)?)?;
        details.set_item("id", error.id)?;
        details.set_item("nargs", error.nargs)?;
        let spelling = decode(py, &error.option)?.repr()?.to_str()?.to_owned();
        let message = match error.kind {
            "missing_value" if error.nargs == 1 => {
                format!("Option {spelling} requires an argument.")
            }
            "missing_value" => format!("Option {spelling} requires {} arguments.", error.nargs),
            "unexpected_value" => format!("Option {spelling} does not take a value."),
            _ => error.message,
        };
        details.set_item("message", message)?;
        details.into_any()
    } else {
        py.None().into_bound(py)
    })
}

#[pyfunction]
#[pyo3(signature=(specs,argv,allow_interspersed_args=true,ignore_unknown_options=false))]
fn parse<'py>(
    py: Python<'py>,
    specs: &Bound<'py, PyAny>,
    argv: &Bound<'py, PyAny>,
    allow_interspersed_args: bool,
    ignore_unknown_options: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let definitions = read_specs(specs)?;
    let input = Inputs::new(argv)?;
    let parsed = core::parse(
        &definitions,
        &input.bytes,
        allow_interspersed_args,
        ignore_unknown_options,
    );
    let values = PyDict::new(py);
    for (id, occurrences) in parsed.values {
        let rows = PyList::empty(py);
        for occurrence in occurrences {
            let items = occurrence
                .iter()
                .map(|v| input.restore(py, v))
                .collect::<PyResult<Vec<_>>>()?;
            rows.append(PyTuple::new(py, items)?)?;
        }
        values.set_item(id, rows)?;
    }
    let leftovers = PyList::empty(py);
    for value in parsed.leftovers {
        leftovers.append(input.restore(py, &value)?)?;
    }
    let order = PyList::new(py, parsed.order)?;
    let error = native_error(py, parsed.error)?;
    PyTuple::new(
        py,
        [
            values.into_any(),
            leftovers.into_any(),
            order.into_any(),
            error,
        ],
    )
}

/// Apply parser actions through each live Python definition's process hook.
/// There is no retained mutable borrow or shared state across these callbacks.
#[pyfunction]
#[pyo3(signature=(specs,argv,definitions,state,unset,flag_needs_value,allow_interspersed_args=true,ignore_unknown_options=false))]
#[allow(clippy::too_many_arguments)]
fn parse_into<'py>(
    py: Python<'py>,
    specs: &Bound<'py, PyAny>,
    argv: &Bound<'py, PyAny>,
    definitions: &Bound<'py, PyAny>,
    state: &Bound<'py, PyAny>,
    unset: &Bound<'py, PyAny>,
    flag_needs_value: &Bound<'py, PyAny>,
    allow_interspersed_args: bool,
    ignore_unknown_options: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let specs = read_specs(specs)?;
    if specs.iter().enumerate().any(|(i, s)| s.id != i as i64) {
        return Err(PyValueError::new_err(
            "parse_into specification ids must match definition indices",
        ));
    }
    let input = Inputs::new(argv)?;
    let parsed = core::parse(
        &specs,
        &input.bytes,
        allow_interspersed_args,
        ignore_unknown_options,
    );
    let mut seen = vec![0; specs.len()];
    for &id in &parsed.order {
        let index = id as usize;
        let spec = &specs[index];
        let row = &parsed.values[&id][seen[index]];
        seen[index] += 1;
        let definition = definitions.get_item(index)?;
        let count: i64 = definition.getattr("nargs")?.extract()?;
        let option = !spec.options.is_empty();
        let value = if option
            && row.is_empty()
            && count != 0
            && definition.getattr("takes_value")?.is_truthy()?
        {
            flag_needs_value.clone()
        } else if count == 1 && !row.is_empty() {
            input.restore(py, &row[0])?
        } else if option || !row.is_empty() || count < 0 {
            PyTuple::new(
                py,
                row.iter()
                    .map(|v| input.restore(py, v))
                    .collect::<PyResult<Vec<_>>>()?,
            )?
            .into_any()
        } else {
            unset.clone()
        };
        definition.call_method1("process", (value, state))?;
    }
    let leftovers = PyList::empty(py);
    for value in parsed.leftovers {
        leftovers.append(input.restore(py, &value)?)?;
    }
    PyTuple::new(py, [leftovers.into_any(), native_error(py, parsed.error)?])
}

#[pyfunction]
fn processing_order(eager: Vec<bool>, encounter_indices: Vec<usize>) -> Vec<usize> {
    core::processing_order(&eager, &encounter_indices)
}
#[pyfunction]
fn select_parameter_value(
    existing_missing: bool,
    existing_source: Option<u8>,
    incoming_source: u8,
    existing_explicit: bool,
    incoming_explicit: bool,
) -> bool {
    core::select_parameter_value(
        existing_missing,
        existing_source,
        incoming_source,
        existing_explicit,
        incoming_explicit,
    )
}
#[pyfunction]
fn strip_ansi<'py>(py: Python<'py>, text: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    decode(py, &core::strip_ansi(&encode(text)?))
}
#[pyfunction]
fn text_width(text: &Bound<'_, PyAny>) -> PyResult<usize> {
    Ok(core::text_width(&encode(text)?))
}
#[pyfunction]
fn truncate_visible<'py>(
    py: Python<'py>,
    text: &Bound<'py, PyAny>,
    n: i64,
) -> PyResult<Bound<'py, PyAny>> {
    decode(
        py,
        &core::truncate_visible(&encode(text)?, n.max(0) as usize),
    )
}
#[pyfunction]
#[pyo3(signature=(text,width=78,initial_indent=None,subsequent_indent=None,preserve_paragraphs=false))]
fn wrap_text<'py>(
    py: Python<'py>,
    text: &Bound<'py, PyAny>,
    width: i64,
    initial_indent: Option<&Bound<'py, PyAny>>,
    subsequent_indent: Option<&Bound<'py, PyAny>>,
    preserve_paragraphs: bool,
) -> PyResult<Bound<'py, PyAny>> {
    if width <= 0 {
        return Err(PyValueError::new_err(format!(
            "invalid width {width} (must be > 0)"
        )));
    }
    let initial = initial_indent.map(encode).transpose()?.unwrap_or_default();
    let subsequent = subsequent_indent
        .map(encode)
        .transpose()?
        .unwrap_or_default();
    let result = core::wrap_text(
        &encode(text)?,
        width as usize,
        &initial,
        &subsequent,
        preserve_paragraphs,
    )
    .map_err(PyValueError::new_err)?;
    decode(py, &result)
}
#[pyfunction]
fn join_options<'py>(
    py: Python<'py>,
    options: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let (text, slash) = core::join_options(&strings(options)?);
    PyTuple::new(
        py,
        [
            decode(py, &text)?,
            slash.into_pyobject(py)?.to_owned().into_any(),
        ],
    )
}
#[pymodule(gil_used = false)]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(dispatch::invoke_group, m)?)?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(parse_into, m)?)?;
    m.add_function(wrap_pyfunction!(processing_order, m)?)?;
    m.add_function(wrap_pyfunction!(select_parameter_value, m)?)?;
    m.add_function(wrap_pyfunction!(strip_ansi, m)?)?;
    m.add_function(wrap_pyfunction!(text_width, m)?)?;
    m.add_function(wrap_pyfunction!(truncate_visible, m)?)?;
    m.add_function(wrap_pyfunction!(wrap_text, m)?)?;
    m.add_function(wrap_pyfunction!(join_options, m)?)?;
    m.add("ZCLAP_VERSION", "0.1.4")?;
    Ok(())
}
