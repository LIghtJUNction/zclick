//! Click argument semantics and terminal formatting over a zclap recognition kernel.
//! Inputs belong to each invocation. Owned immutable schemas may be reused by
//! their caller; every zclap borrow remains local and no global cache exists.
#![no_std]
#![forbid(unsafe_code)]
extern crate alloc;
mod parse;
mod text;
pub use parse::{
    EventResult, Normalizer, Occurrence, OccurrenceValues, ParseError, ParseResult, ParsedValue,
    Schema, Spec, parse, parse_with_normalizer, processing_order, select_parameter_value,
};
pub use text::{join_options, strip_ansi, text_width, truncate_visible, wrap_text};
