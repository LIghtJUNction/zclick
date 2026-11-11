//! Click argument semantics and terminal formatting over a zclap recognition kernel.
//! All input and definition storage belongs to the invocation. No global cache exists.
#![no_std]
#![forbid(unsafe_code)]
extern crate alloc;
mod parse;
mod text;
pub use parse::{ParseError, ParseResult, Spec, parse, processing_order, select_parameter_value};
pub use text::{join_options, strip_ansi, text_width, truncate_visible, wrap_text};
