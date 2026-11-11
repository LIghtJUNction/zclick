"""Rust-backed command-line interfaces with a Click-compatible Python API."""
from __future__ import annotations

# Reject unsupported interpreters before importing Python modules that may
# initialize their own native state. This import also establishes the binding
# boundary before any public classes or decorators are constructed.
from . import _native as _native

from .core import Argument as Argument, Command as Command, CommandCollection as CommandCollection
from .core import Context as Context, Group as Group, Option as Option
from .core import Parameter as Parameter, ParameterSource as ParameterSource
from .decorators import argument as argument, command as command, group as group, option as option
from .decorators import confirmation_option as confirmation_option, custom_version_option as custom_version_option
from .decorators import help_option as help_option, make_pass_decorator as make_pass_decorator
from .decorators import pass_context as pass_context, pass_obj as pass_obj
from .decorators import password_option as password_option, version_option as version_option
from .exceptions import Abort as Abort, BadArgumentUsage as BadArgumentUsage, BadOptionUsage as BadOptionUsage
from .exceptions import BadParameter as BadParameter, ClickException as ClickException, FileError as FileError
from .exceptions import MissingParameter as MissingParameter, NoSuchCommand as NoSuchCommand
from .exceptions import NoSuchOption as NoSuchOption, UsageError as UsageError
from .formatting import HelpFormatter as HelpFormatter, wrap_text as wrap_text
from .globals import get_current_context as get_current_context
from .termui import clear as clear, confirm as confirm, echo_via_pager as echo_via_pager
from .termui import edit as edit, get_pager_file as get_pager_file, getchar as getchar, launch as launch
from .termui import pause as pause, progressbar as progressbar, prompt as prompt
from .termui import secho as secho, style as style, unstyle as unstyle
from .types import BOOL as BOOL, Choice as Choice, DateTime as DateTime, File as File
from .types import FLOAT as FLOAT, FloatRange as FloatRange, INT as INT, IntRange as IntRange
from .types import ParamType as ParamType, Path as Path, STRING as STRING, Tuple as Tuple
from .types import UNPROCESSED as UNPROCESSED, UUID as UUID
from .utils import echo as echo, format_filename as format_filename, get_app_dir as get_app_dir, open_file as open_file


def __getattr__(name: str) -> object:
    import warnings
    if name in ("BaseCommand", "MultiCommand"):
        from .core import _BaseCommand, _MultiCommand
        target = _BaseCommand if name == "BaseCommand" else _MultiCommand
        message = f"'{name}' is deprecated and will be removed in Click 9.0. Use '{target._target.__name__}' instead."
    elif name == "OptionParser":
        from .parser import _OptionParser
        target = _OptionParser
        message = "'OptionParser' is deprecated and will be removed in Click 9.0. The old parser is available in 'optparse'."
    elif name in ("get_binary_stream", "get_text_stream"):
        from .utils import _get_binary_stream, _get_text_stream
        target = _get_binary_stream if name == "get_binary_stream" else _get_text_stream
        message = f"'{name}' is deprecated and will be removed in Click 9.0."
    elif name == "__version__":
        from importlib.metadata import version
        target = version("zclick")
        message = "The '__version__' attribute is deprecated and will be removed in Click 9.1. Use feature detection or 'importlib.metadata.version(\"zclick\")' instead."
    else:
        raise AttributeError(name)
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    return target
