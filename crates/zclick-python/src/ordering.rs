//! Identity ordering is equivalent to Click's list.index only for plain objects.
//!
//! Everything with observable lookup, comparison or truthiness hooks is left to
//! the Python sorted/index implementation. No Python object is cached here.
use std::{
    collections::{HashMap, HashSet},
    ffi::c_void,
};

use pyo3::{
    exceptions::{PyAttributeError, PyRuntimeError},
    ffi,
    prelude::*,
    types::{PyBool, PyDict, PyIterator, PyList, PyString, PyTuple, PyType},
};

#[derive(Clone, Copy, PartialEq)]
struct Slots {
    getattro: *mut c_void,
    richcompare: *mut c_void,
}

fn slots(class: &Bound<'_, PyType>) -> Slots {
    // SAFETY: these are documented Stable ABI slot identifiers, queried on a
    // live type held by a PyO3 handle. We only compare the returned addresses;
    // no layout access, function-pointer call, or reference-count operation.
    unsafe {
        Slots {
            getattro: ffi::PyType_GetSlot(class.as_type_ptr(), ffi::Py_tp_getattro),
            richcompare: ffi::PyType_GetSlot(class.as_type_ptr(), ffi::Py_tp_richcompare),
        }
    }
}

fn instance_dict<'py>(object: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyDict>>> {
    // SAFETY: the documented generic getter accesses the instance dictionary,
    // bypassing user __dict__ descriptors. PyO3 immediately owns the returned
    // new reference and handles the NULL/error case. The closure argument is
    // documented as unused. There is no hand-written reference counting.
    let result = unsafe {
        Bound::from_owned_ptr_or_err(
            object.py(),
            ffi::PyObject_GenericGetDict(object.as_ptr(), std::ptr::null_mut()),
        )
    };
    match result {
        Ok(dict) if dict.is_exact_instance_of::<PyDict>() => Ok(Some(dict.cast_into()?)),
        Ok(_) => Ok(None),
        Err(error) if error.is_instance_of::<PyAttributeError>(object.py()) => Ok(None),
        Err(error) => Err(error),
    }
}

struct Class<'py> {
    class: Bound<'py, PyType>,
    mro: Bound<'py, PyTuple>,
    args: Bound<'py, PyTuple>,
}

fn same_list(list: &Bound<'_, PyList>, snapshot: &[Bound<'_, PyAny>]) -> bool {
    list.len() == snapshot.len()
        && list
            .iter()
            .zip(snapshot)
            .all(|(live, expected)| live.is(expected))
}

#[pyfunction]
pub(super) fn order_parameters<'py>(
    py: Python<'py>,
    invocation_order: &Bound<'py, PyAny>,
    declaration_order: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyList>>> {
    // PyPy's cpyext type/slot materialization can consult metaclass names and
    // does not preserve CPython's inherited-slot pointer identity. Do not
    // perform even the classification there: the Python fallback is exact.
    // Other non-CPython implementations use that same conservative policy.
    if cfg!(any(PyPy, GraalPy, RustPython)) {
        return Ok(None);
    }
    // In particular, do not iterate a custom iterable before falling back:
    // sorted() and list.index() must see its original, live behavior.
    if !invocation_order.is_exact_instance_of::<PyList>()
        || !declaration_order.is_exact_instance_of::<PyList>()
    {
        return Ok(None);
    }
    let invocation_list = invocation_order.cast::<PyList>()?;
    let declaration_list = declaration_order.cast::<PyList>()?;
    let object_slots = slots(&py.get_type::<PyAny>());
    let type_slots = slots(&py.get_type::<PyType>());
    let type_dict = py.get_type::<PyType>().getattr("__dict__")?;
    // These immutable builtin descriptors bypass metaclass attribute hooks,
    // including a metaclass descriptor also named __mro__ or __dict__.
    let mro_get = type_dict.get_item("__mro__")?.getattr("__get__")?;
    let dict_get = type_dict.get_item("__dict__")?.getattr("__get__")?;
    let eager_name = PyString::new(py, "is_eager");
    let invocation: Vec<_> = invocation_list.iter().collect();
    let declaration: Vec<_> = declaration_list.iter().collect();
    let mut classes = Vec::<Class<'py>>::new();
    let mut seen_classes = HashSet::new();
    let mut dictionaries = Vec::new();
    let mut seen_bases = HashSet::new();
    let mut objects = Vec::new();
    let mut seen_objects = HashSet::new();
    let mut instance_dicts = HashMap::new();

    for object in declaration.iter().chain(&invocation) {
        let pointer = object.as_ptr() as usize;
        if !seen_objects.insert(pointer) {
            continue;
        }
        let class = object.get_type();
        if slots(&class) != object_slots || slots(&class.get_type()) != type_slots {
            return Ok(None);
        }
        let class_pointer = class.as_ptr() as usize;
        if seen_classes.insert(class_pointer) {
            // Allocate all descriptor arguments and iterators before the final
            // guard. A GC callback during preparation may mutate any input.
            let args = PyTuple::new(py, [&class])?;
            let mro = mro_get.call1(&args)?.cast_into::<PyTuple>()?;
            for base in mro.iter() {
                let base_pointer = base.as_ptr() as usize;
                if seen_bases.insert(base_pointer) {
                    let dictionary = dict_get.call1((&base,))?;
                    let keys = PyIterator::from_object(&dictionary)?;
                    dictionaries.push(keys);
                }
            }
            classes.push(Class {
                class: class.clone(),
                mro,
                args,
            });
        }
        objects.push((object.clone(), class));
    }
    for object in &declaration {
        let pointer = object.as_ptr() as usize;
        if let std::collections::hash_map::Entry::Vacant(entry) = instance_dicts.entry(pointer) {
            let Some(dictionary) = instance_dict(object)? else {
                return Ok(None);
            };
            entry.insert(dictionary);
        }
    }
    // Even the result list is allocated before the final guard. After this
    // point the admitted path only reads existing builtin objects and performs
    // Rust allocations; there is no user callback or Python container creation.
    let result = PyList::new(py, &declaration)?;

    for record in &classes {
        if slots(&record.class) != object_slots
            || slots(&record.class.get_type()) != type_slots
            || !mro_get.call1(&record.args)?.is(&record.mro)
        {
            return Ok(None);
        }
    }
    for (object, class) in &objects {
        if !object.get_type().is(class) {
            return Ok(None);
        }
        if let Some(expected) = instance_dicts.get(&(object.as_ptr() as usize)) {
            // It was already materialized during preparation, so this read
            // cannot create a managed dict. A GC callback may have replaced
            // __dict__ while another object's metadata was being prepared.
            let Some(current) = instance_dict(object)? else {
                return Ok(None);
            };
            if !current.is(expected) {
                return Ok(None);
            }
        }
    }
    for keys in dictionaries {
        for key in keys {
            let key = match key {
                Ok(key) => key,
                // A preparation-time GC callback changed this class dictionary.
                Err(error) if error.is_instance_of::<PyRuntimeError>(py) => return Ok(None),
                Err(error) => return Err(error),
            };
            if !key.is_exact_instance_of::<PyString>() || key.eq(&eager_name)? {
                return Ok(None);
            }
        }
    }
    let mut eager_values = HashMap::with_capacity(instance_dicts.len());
    for (pointer, dictionary) in &instance_dicts {
        let mut eager = None;
        // Scan keys without dictionary lookup: foreign collision keys must
        // never have their __eq__ called merely to decide whether to fall back.
        for (key, value) in dictionary.iter() {
            if !key.is_exact_instance_of::<PyString>() {
                return Ok(None);
            }
            if key.eq(&eager_name)? {
                if !value.is_exact_instance_of::<PyBool>() {
                    return Ok(None);
                }
                eager = Some(value.is_truthy()?);
            }
        }
        let Some(eager) = eager else {
            return Ok(None);
        };
        eager_values.insert(*pointer, eager);
    }
    if !same_list(invocation_list, &invocation) || !same_list(declaration_list, &declaration) {
        return Ok(None);
    }
    let mut first = HashMap::with_capacity(invocation.len());
    for (index, parameter) in invocation.iter().enumerate() {
        first.entry(parameter.as_ptr() as usize).or_insert(index);
    }
    let mut order: Vec<_> = (0..declaration.len()).collect();
    order.sort_by_key(|&index| {
        let pointer = declaration[index].as_ptr() as usize;
        (
            !eager_values[&pointer],
            first.get(&pointer).copied().unwrap_or(usize::MAX),
        )
    });
    for (destination, source) in order.into_iter().enumerate() {
        result.set_item(destination, &declaration[source])?;
    }
    Ok(Some(result))
}
