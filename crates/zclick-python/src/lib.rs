//! CPython object adaptation. Pure parsing/formatting lives in zclick-core.
use pyo3::{
    exceptions::{PyTypeError, PyValueError},
    prelude::*,
    types::{PyBytes, PyDict, PyList, PyTuple},
};
use zclick_core::{self as core, Spec};

fn encode(value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let bytes = value.call_method1("encode", ("utf-8", "surrogatepass"))?;
    Ok(bytes.cast::<PyBytes>()?.as_bytes().to_vec())
}
fn decode<'py>(py: Python<'py>, bytes: &[u8]) -> PyResult<Bound<'py, PyAny>> {
    PyBytes::new(py, bytes).call_method1("decode", ("utf-8", "surrogatepass"))
}
fn strings(values: &Bound<'_, PyAny>) -> PyResult<Vec<Vec<u8>>> {
    values.try_iter()?.map(|v| encode(&v?)).collect()
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
    let definitions: Vec<Spec> = specs
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
        .collect::<PyResult<_>>()?;
    let args = strings(argv)?;
    let parsed = core::parse(
        &definitions,
        &args,
        allow_interspersed_args,
        ignore_unknown_options,
    );
    let values = PyDict::new(py);
    for (id, occurrences) in parsed.values {
        let rows = PyList::empty(py);
        for occurrence in occurrences {
            let items = occurrence
                .iter()
                .map(|v| decode(py, v))
                .collect::<PyResult<Vec<_>>>()?;
            rows.append(PyTuple::new(py, items)?)?;
        }
        values.set_item(id, rows)?;
    }
    let leftovers = PyList::empty(py);
    for value in parsed.leftovers {
        leftovers.append(decode(py, &value)?)?;
    }
    let order = PyList::new(py, parsed.order)?;
    let error = if let Some(error) = parsed.error {
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
    };
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

#[pyfunction]
fn processing_order(eager: Vec<bool>, encounter_indices: Vec<usize>) -> Vec<usize> {
    core::processing_order(&eager, &encounter_indices)
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
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(processing_order, m)?)?;
    m.add_function(wrap_pyfunction!(strip_ansi, m)?)?;
    m.add_function(wrap_pyfunction!(text_width, m)?)?;
    m.add_function(wrap_pyfunction!(truncate_visible, m)?)?;
    m.add_function(wrap_pyfunction!(wrap_text, m)?)?;
    m.add_function(wrap_pyfunction!(join_options, m)?)?;
    m.add("ZCLAP_VERSION", "0.1.4")?;
    Ok(())
}
