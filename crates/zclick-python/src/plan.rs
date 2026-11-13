//! Immutable, owned parsing plans. No Python application objects are retained.
use super::*;
use std::sync::Arc;

#[pyclass(frozen, module = "zclick._native")]
pub(super) struct ParserPlan {
    pub(super) schema: Arc<core::Schema>,
}

fn same_text(value: &Bound<'_, PyAny>, expected: &[u8]) -> PyResult<bool> {
    let text = value.cast::<PyString>()?;
    if let Ok(text) = text.to_str() {
        Ok(text.as_bytes() == expected)
    } else {
        Ok(encode(value)? == expected)
    }
}

/// None means equality; otherwise return a complete replacement assembled
/// without evaluating an input iterator twice.
fn changed_options(
    options: &Bound<'_, PyAny>,
    previous: Option<&[Vec<u8>]>,
) -> PyResult<Option<Vec<Vec<u8>>>> {
    let old = previous.unwrap_or(&[]);
    let mut changed = previous.is_none().then(Vec::new);
    let mut count = 0;
    for value in iteration::LiveIterator::new(options)? {
        let value = value?;
        if changed.is_none()
            && let Some(expected) = old.get(count)
            && same_text(&value, expected)?
        {
            count += 1;
            continue;
        }
        let output = changed.get_or_insert_with(|| old[..count].to_vec());
        output.push(encode(&value)?);
        count += 1;
    }
    if changed.is_none() && count != old.len() {
        changed = Some(old[..count].to_vec());
    }
    Ok(changed)
}

fn changed_definitions(
    definitions: &Bound<'_, PyAny>,
    option_type: &Bound<'_, PyAny>,
    previous: Option<&[Spec]>,
) -> PyResult<Option<Vec<Spec>>> {
    let old = previous.unwrap_or(&[]);
    let mut changed = previous.is_none().then(Vec::new);
    let py = definitions.py();
    let opts_name = pyo3::intern!(py, "opts");
    let nargs_name = pyo3::intern!(py, "nargs");
    let takes_value_name = pyo3::intern!(py, "takes_value");
    let obj_name = pyo3::intern!(py, "obj");
    let flag_name = pyo3::intern!(py, "_flag_needs_value");
    let mut count = 0;
    for definition in iteration::LiveIterator::new(definitions)? {
        let definition = definition?;
        let expected = old.get(count);
        let option = definition.is_instance(option_type)?;
        let options = if option {
            changed_options(
                &definition.getattr(opts_name)?,
                expected.map(|s| s.options.as_slice()),
            )?
        } else if expected.is_some_and(|s| s.options.is_empty()) {
            None
        } else {
            Some(Vec::new())
        };
        let nargs = definition.getattr(nargs_name)?.extract()?;
        let is_flag = option && !definition.getattr(takes_value_name)?.is_truthy()?;
        let optional_value = match definition.getattr(obj_name)?.getattr(flag_name) {
            Ok(value) => value.is_truthy()?,
            Err(error) if error.is_instance_of::<PyAttributeError>(py) => false,
            Err(error) => return Err(error),
        };
        let equal = options.is_none()
            && expected.is_some_and(|s| {
                s.id == count as i64
                    && s.nargs == nargs
                    && s.is_flag == is_flag
                    && s.optional_value == optional_value
            });
        if changed.is_some() || !equal {
            let output = changed.get_or_insert_with(|| old[..count].to_vec());
            output.push(Spec {
                id: count as i64,
                options: options.unwrap_or_else(|| {
                    expected
                        .expect("unchanged options have a prior spec")
                        .options
                        .clone()
                }),
                nargs,
                is_flag,
                optional_value,
            });
        }
        count += 1;
    }
    if changed.is_none() && count != old.len() {
        changed = Some(old[..count].to_vec());
    }
    Ok(changed)
}

#[pymethods]
impl ParserPlan {
    #[new]
    fn new(specs: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            schema: Arc::new(core::Schema::new(read_specs(specs)?)),
        })
    }

    fn __reduce__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        // Commands may be copied or pickled after warming their parsing plan.
        // Serialize only owned structural fields; contexts, callbacks and
        // dynamic default results never belong to this object.
        let specs = PyList::empty(py);
        for spec in self.schema.specs() {
            let names = spec
                .options
                .iter()
                .map(|name| decode(py, name))
                .collect::<PyResult<Vec<_>>>()?;
            specs.append(PyTuple::new(
                py,
                [
                    spec.id.into_pyobject(py)?.into_any(),
                    PyList::new(py, names)?.into_any(),
                    spec.nargs.into_pyobject(py)?.into_any(),
                    spec.is_flag.into_pyobject(py)?.to_owned().into_any(),
                    spec.optional_value.into_pyobject(py)?.to_owned().into_any(),
                ],
            )?)?;
        }
        let args = PyTuple::new(py, [specs])?;
        PyTuple::new(py, [py.get_type::<Self>().into_any(), args.into_any()])
    }

    #[staticmethod]
    #[pyo3(signature=(definitions, option_type, previous=None))]
    pub(super) fn from_definitions<'py>(
        py: Python<'py>,
        definitions: &Bound<'py, PyAny>,
        option_type: &Bound<'py, PyAny>,
        previous: Option<&Bound<'py, Self>>,
    ) -> PyResult<Py<Self>> {
        // Own a pure Rust Arc before evaluating any Python getter. Reentrant
        // calls have independent execution state and cannot mutate this schema.
        let prior = previous.map(|plan| Arc::clone(&plan.get().schema));
        let changed =
            changed_definitions(definitions, option_type, prior.as_ref().map(|s| s.specs()))?;
        match changed {
            None => Ok(previous
                .expect("equality requires a previous plan")
                .clone()
                .unbind()),
            Some(specs) => Py::new(
                py,
                Self {
                    schema: Arc::new(core::Schema::new(specs)),
                },
            ),
        }
    }

    fn matches_definitions(
        &self,
        definitions: &Bound<'_, PyAny>,
        option_type: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        Ok(changed_definitions(definitions, option_type, Some(self.schema.specs()))?.is_none())
    }

    #[pyo3(signature=(argv,allow_interspersed_args=true,ignore_unknown_options=false,normalizer=None,original_args=None))]
    #[allow(clippy::too_many_arguments)]
    fn parse<'py>(
        &self,
        py: Python<'py>,
        argv: &Bound<'py, PyAny>,
        allow_interspersed_args: bool,
        ignore_unknown_options: bool,
        normalizer: Option<&Bound<'py, PyAny>>,
        original_args: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        parse_with_schema(
            py,
            &self.schema,
            argv,
            allow_interspersed_args,
            ignore_unknown_options,
            normalizer,
            original_args,
        )
    }

    #[pyo3(signature=(argv,definitions,state,unset,flag_needs_value,allow_interspersed_args=true,ignore_unknown_options=false,normalizer=None,original_args=None))]
    #[allow(clippy::too_many_arguments)]
    fn parse_into<'py>(
        &self,
        py: Python<'py>,
        argv: &Bound<'py, PyAny>,
        definitions: &Bound<'py, PyAny>,
        state: &Bound<'py, PyAny>,
        unset: &Bound<'py, PyAny>,
        flag_needs_value: &Bound<'py, PyAny>,
        allow_interspersed_args: bool,
        ignore_unknown_options: bool,
        normalizer: Option<&Bound<'py, PyAny>>,
        original_args: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        parse_into_with_schema(
            py,
            &self.schema,
            argv,
            definitions,
            state,
            unset,
            flag_needs_value,
            allow_interspersed_args,
            ignore_unknown_options,
            normalizer,
            original_args,
        )
    }
}
