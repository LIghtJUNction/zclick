//! Avoid a Python iterator allocation for exact lists without freezing length.
use pyo3::{
    exceptions::PyIndexError,
    prelude::*,
    types::{PyIterator, PyList},
};

pub(super) enum LiveIterator<'a, 'py> {
    List {
        list: &'a Bound<'py, PyList>,
        index: usize,
        exhausted: bool,
    },
    Other(Bound<'py, PyIterator>),
}

impl<'a, 'py> LiveIterator<'a, 'py> {
    pub(super) fn new(value: &'a Bound<'py, PyAny>) -> PyResult<Self> {
        if value.is_exact_instance_of::<PyList>() {
            Ok(Self::List {
                list: value.cast()?,
                index: 0,
                exhausted: false,
            })
        } else {
            // A subclass can override __iter__. Do not replace that protocol
            // with indexing or an initial-length snapshot.
            Ok(Self::Other(value.try_iter()?))
        }
    }
}

impl<'py> Iterator for LiveIterator<'_, 'py> {
    type Item = PyResult<Bound<'py, PyAny>>;

    fn next(&mut self) -> Option<Self::Item> {
        match self {
            Self::Other(iterator) => iterator.next(),
            Self::List {
                list,
                index,
                exhausted,
            } => {
                if *exhausted || *index >= list.len() {
                    *exhausted = true;
                    return None;
                }
                match list.get_item(*index) {
                    Ok(value) => {
                        *index += 1;
                        Some(Ok(value))
                    }
                    // In a free-threaded interpreter another thread may
                    // shrink the list between len and get_item. Like Python's
                    // list iterator, treat that boundary as exhaustion.
                    Err(error) if error.is_instance_of::<PyIndexError>(list.py()) => {
                        *exhausted = true;
                        None
                    }
                    Err(error) => Some(Err(error)),
                }
            }
        }
    }
}
