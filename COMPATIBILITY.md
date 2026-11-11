# Click compatibility

The fixed target is **Click 8.5.1**, released 2026-11-06, at commit `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1`. The target was verified on 2026-11-11 against PyPI and the upstream Git tag.

The contract covers public object names, call parameters and defaults, return annotations, class members, properties, deprecated imports, exception behavior, CLI output and terminal tools. The generated [API inventory](compatibility/api-reference.json) records each declaration and associated upstream test source. The `.pyi` declarations describe this same fixed target.

## Evidence and scope

| Evidence | Result |
| --- | --- |
| Public object and member signature audit | Passed; 196 public objects |
| Upstream normal suite on the local interpreter | 2434 passed, 24 skipped, 1 xfailed |
| Upstream stress suite | 31000 cases tracked separately; passing stress reports must cover every case before release |
| Cross platform validation | See the [CI runs](https://github.com/LIghtJUNction/zclick/actions/workflows/ci.yml); a configured runner is not a passing result |

The normal run preserves the upstream `not stress` development selection. The release workflow runs all four original stress functions with their original parameter counts, then checks the union of test IDs. It rejects failures, collection errors, missing tests and extra skips. Upstream platform skips and expected failures retain their original conditions; they are reported separately.

Tests are copied only into `.cache/click-migrated`, outside the runtime package. The migration changes package imports, module references, monkeypatch import paths, subprocess imports, distribution metadata lookup and four module-qualified object repr patterns. The complete edit log is `.cache/click-migrated/namespace-migration.json`. Assertions, argument values, expected behavior and skip markers remain intact.

## Behavior checklist

Each row names the original tests that verify its observable behavior. The API inventory below adds the exact call and member contract for every public object.

| Area | Covered behavior | Upstream test sources |
| --- | --- | --- |
| Command construction | Decorators, arbitrary classes, subclass overrides, direct invocation | `test_command_decorators.py`, `test_custom_classes.py`, `test_commands.py` |
| Command groups | Nested and chained groups, invocation without subcommand, result callbacks, dynamic and lazy lookup | `test_commands.py`, `test_chain.py`, `test_custom_classes.py` |
| Context | Parent propagation, objects, metadata, resources, invoke/forward, resilient parsing | `test_context.py`, `test_commands.py` |
| Options | Aliases, prefixes, clusters, attached values, optional values, count, dual flags, multiple/nargs, shared flag destinations | `test_options.py`, `test_parser.py` |
| Arguments | Fixed and variadic arity, negative tokens, `--`, positional allocation, missing and extra arguments | `test_arguments.py`, `test_parser.py` |
| Defaults and sources | Callable defaults, default maps, environment variables, automatic prefixes, prompts and ParameterSource | `test_defaults.py`, `test_options.py`, `test_context.py` |
| Conversion | Unbounded Python integers, floats, ranges, enum choices, tuples, UUID, dates, paths, files, custom types | `test_types/`, `test_basic.py` |
| Control flow | Eager options, callbacks, abort, EOF, KeyboardInterrupt, usage exceptions, standalone/nonstandalone exits | `test_abort_interrupt.py`, `test_basic.py`, `test_exceptions/` |
| Help | Usage/metavars, command/option ordering, defaults/envvars, hidden/deprecated items, ANSI wrapping and widths | `test_formatting.py`, `test_options.py`, `test_commands.py` |
| Terminal tools | Echo, styles, prompting, progress bars, pager lifecycle, editor, launcher, streams and file helpers | `test_termui.py`, `test_utils/`, `test_compat.py` |
| Completion | Bash, Zsh, Fish, PowerShell, custom classes, protocol output, context resolution without command callbacks | `test_shell_completion.py` |
| Testing tools | Result output streams, simulated input, isolated environment/filesystem, exceptions and return values | `test_testing.py`, `test_stream_lifecycle.py` |
| Deprecations | Available deprecated names, warning categories and triggering attribute access | `test_deprecations.py` |
| Typing | Decorator inference, prompts, generic types, paths, callbacks and callable return values | `tests/typing/` (12 files) |
| Resource stress | 10,000 thread-pool, 10,000 logging, 10,000 GC, 1,000 pager cleanup cases | `test_stream_lifecycle.py`, `test_utils/test_echo_via_pager.py` |

## Migration and dynamic behavior

Use `import zclick as click` and replace `from click.module` with `from zclick.module`. The distribution installs only the `zclick` namespace and never rewrites `sys.modules['click']`. An extension that internally imports original Click still uses original Click: module aliasing does not merge class identities across packages. Such extensions need their own import migration and tests.

Command callbacks, parameter objects and type converters remain Python extension points. Invocation observes changes to `command.params`, registered commands, callbacks and option attributes. Per-invocation defaults, environment values and context state are not cached. The native parser receives the current definition and does not retain borrowed schema references.

`CliRunner` temporarily changes interpreter-wide streams, environment and working directory, matching Click's isolation model. Concurrent runner invocations in the same process are not a supported thread-safe isolation boundary. Native parsing state is per call; this does not make the testing tools thread-safe.

## zclap adaptation

| zclap contract | Click requirement | Adaptation |
| --- | --- | --- |
| Runtime definitions are borrowed | Python can create and mutate parameter tables | Build owned call-local storage and borrow it while parsing; no leaked strings or fake static lifetimes |
| Option names and values have kernel conventions | Multiple prefixes, aliases, combined shorts, negative and dash-prefixed values | Translate current option spellings and use zclap event parsing for recognition; retain original values and error spelling |
| Parent/child parsing scope and final validation differ | Click controls interspersed arguments, chain groups and deferred validation | A Rust semantic layer controls boundaries and event sequencing around zclap |
| Kernel help output has its own layout | Exact Click help and terminal formatting | Rust wrapping/ANSI primitives feed the Click-compatible formatter |
| Kernel arity rules are lower-level | Variadics, optional values, callbacks and source precedence | Rust semantic operations and Python extension hooks preserve target ordering |

The core directly depends only on registry `zclap = 0.1.4` and builds with `no_std + alloc`. The Python extension also depends on PyO3, uses std, creates Python objects and allocates memory. The published Python package has no third-party Python runtime requirements. Click, pytest, Maturin and type-checking tools are development dependencies.

## Public API checklist

`Contract passed` means availability, positional/keyword parameters and defaults, member availability, member signatures, property mutability and deprecation categories passed introspection. Observable behavior is measured by the associated tests and platform runs above.

| Public object | Declaration source | Contract | Behavior test sources |
| --- | --- | --- | --- |
| `click.Abort` | official-api-reference, top-level-export | Contract passed | `test_abort_interrupt.py`, `test_prompt.py` |
| `click.Argument` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_shell_completion.py`, `test_options.py`; +5 in JSON |
| `click.BOOL` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.BadArgumentUsage` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.BadOptionUsage` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.BadParameter` | official-api-reference, top-level-export | Contract passed | `test_arguments.py`, `test_options.py`, `test_termui.py`, `test_Path.py`; +5 in JSON |
| `click.BaseCommand` | official-api-reference | Contract passed | `test_deprecations.py` |
| `click.Choice` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_normalization.py`, `test_commands.py`; +5 in JSON |
| `click.ClickException` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_termui.py`, `test_abort_interrupt.py`, `test_style.py` |
| `click.Command` | official-api-reference, top-level-export | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_arguments.py`; +12 in JSON |
| `click.CommandCollection` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.Context` | official-api-reference, top-level-export | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_arguments.py`; +8 in JSON |
| `click.DateTime` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_basic.py` |
| `click.FLOAT` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.File` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_arguments.py`, `test_shell_completion.py`; +5 in JSON |
| `click.FileError` | official-api-reference, top-level-export | Contract passed | `test_FileError.py` |
| `click.FloatRange` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_FloatRange.py` |
| `click.Group` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_context.py`, `test_commands.py`, `test_shell_completion.py`; +3 in JSON |
| `click.HelpFormatter` | official-api-reference, top-level-export | Contract passed | `test_formatting.py`, `test_custom_classes.py` |
| `click.INT` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_commands.py`, `test_defaults.py`; +4 in JSON |
| `click.IntRange` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_options.py`, `test_termui.py`, `test_prompt.py`; +1 in JSON |
| `click.MissingParameter` | top-level-export | Contract passed | `test_arguments.py`, `test_options.py`, `test_termui.py` |
| `click.MultiCommand` | official-api-reference | Contract passed | `test_deprecations.py` |
| `click.NoSuchCommand` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.NoSuchOption` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.Option` | official-api-reference, top-level-export | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_commands.py`; +8 in JSON |
| `click.OptionParser` | official-api-reference | Contract passed | `test_commands.py`, `test_deprecations.py` |
| `click.ParamType` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_defaults.py`, `test_options.py`, `test_formatting.py`; +4 in JSON |
| `click.Parameter` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_context.py`, `test_defaults.py`, `test_options.py`; +3 in JSON |
| `click.ParameterSource` | top-level-export | Contract passed | `test_context.py`, `test_defaults.py` |
| `click.Path` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_arguments.py`, `test_commands.py`; +7 in JSON |
| `click.STRING` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_commands.py`, `test_defaults.py`; +2 in JSON |
| `click.Tuple` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.UNPROCESSED` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py` |
| `click.UUID` | official-api-reference, top-level-export | Contract passed | `test_info_dict.py`, `test_basic.py`, `test_convert_type.py` |
| `click.UsageError` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.__version__` | deprecated-public-export | Contract passed | `test_deprecations.py` |
| `click.argument` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +13 in JSON |
| `click.clear` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_compat.py`, `test_shell_completion.py` |
| `click.command` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +16 in JSON |
| `click.confirm` | official-api-reference, top-level-export | Contract passed | `test_termui.py`, `test_confirm.py`, `test_echo.py`, `test_prompt.py` |
| `click.confirmation_option` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.core.Argument` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_shell_completion.py`, `test_options.py`; +5 in JSON |
| `click.core.BaseCommand` | deprecated-public-export | Contract passed | `test_deprecations.py` |
| `click.core.Command` | public-submodule-definition | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_arguments.py`; +12 in JSON |
| `click.core.CommandCollection` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.core.Context` | public-submodule-definition | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_arguments.py`; +8 in JSON |
| `click.core.F` | public-submodule-definition | Contract passed | `test_arguments.py`, `test_basic.py` |
| `click.core.Group` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_context.py`, `test_commands.py`, `test_shell_completion.py`; +3 in JSON |
| `click.core.MultiCommand` | deprecated-public-export | Contract passed | `test_deprecations.py` |
| `click.core.Option` | public-submodule-definition | Contract passed | `test_parser.py`, `test_info_dict.py`, `test_context.py`, `test_commands.py`; +8 in JSON |
| `click.core.Parameter` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_context.py`, `test_defaults.py`, `test_options.py`; +3 in JSON |
| `click.core.ParameterSource` | official-api-reference, public-submodule-definition | Contract passed | `test_context.py`, `test_defaults.py` |
| `click.core.V` | public-submodule-definition | Contract passed | `test_basic.py` |
| `click.core.augment_usage_errors` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.core.batch` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.core.iter_params_for_processing` | public-submodule-definition | Contract passed | `test_commands.py` |
| `click.custom_version_option` | official-api-reference, top-level-export | Contract passed | `test_basic.py` |
| `click.decorators.CmdType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.decorators.FC` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.decorators.GrpType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.decorators.R` | public-submodule-definition | Contract passed | `test_termui.py` |
| `click.decorators.T` | public-submodule-definition | Contract passed | `test_options.py` |
| `click.decorators.argument` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +13 in JSON |
| `click.decorators.command` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +16 in JSON |
| `click.decorators.confirmation_option` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.decorators.custom_version_option` | public-submodule-definition | Contract passed | `test_basic.py` |
| `click.decorators.group` | public-submodule-definition | Contract passed | `test_context.py`, `test_arguments.py`, `test_normalization.py`, `test_commands.py`; +8 in JSON |
| `click.decorators.help_option` | public-submodule-definition | Contract passed | `test_context.py`, `test_options.py`, `test_formatting.py`, `test_basic.py` |
| `click.decorators.make_pass_decorator` | public-submodule-definition | Contract passed | `test_context.py` |
| `click.decorators.option` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +13 in JSON |
| `click.decorators.pass_context` | public-submodule-definition | Contract passed | `test_testing.py`, `test_context.py`, `test_arguments.py`, `test_commands.py`; +5 in JSON |
| `click.decorators.pass_meta_key` | official-api-reference, public-submodule-definition | Contract passed | `test_context.py` |
| `click.decorators.pass_obj` | public-submodule-definition | Contract passed | `test_context.py`, `test_arguments.py` |
| `click.decorators.password_option` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.decorators.version_option` | public-submodule-definition | Contract passed | `test_basic.py` |
| `click.echo` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_context.py`, `test_stream_lifecycle.py`, `test_arguments.py`; +16 in JSON |
| `click.echo_via_pager` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_termui.py`, `test_echo_via_pager.py` |
| `click.edit` | official-api-reference, top-level-export | Contract passed | `test_termui.py` |
| `click.exceptions.Abort` | public-submodule-definition | Contract passed | `test_abort_interrupt.py`, `test_prompt.py` |
| `click.exceptions.BadArgumentUsage` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.exceptions.BadOptionUsage` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.exceptions.BadParameter` | public-submodule-definition | Contract passed | `test_arguments.py`, `test_options.py`, `test_termui.py`, `test_Path.py`; +5 in JSON |
| `click.exceptions.ClickException` | public-submodule-definition | Contract passed | `test_testing.py`, `test_termui.py`, `test_abort_interrupt.py`, `test_style.py` |
| `click.exceptions.Exit` | public-submodule-definition | Contract passed | `test_abort_interrupt.py` |
| `click.exceptions.FileError` | public-submodule-definition | Contract passed | `test_FileError.py` |
| `click.exceptions.MissingParameter` | public-submodule-definition | Contract passed | `test_arguments.py`, `test_options.py`, `test_termui.py` |
| `click.exceptions.NoArgsIsHelpError` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.exceptions.NoSuchCommand` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.exceptions.NoSuchOption` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.exceptions.UsageError` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.format_filename` | official-api-reference, top-level-export | Contract passed | `test_format_filename.py` |
| `click.formatting.HelpFormatter` | public-submodule-definition | Contract passed | `test_formatting.py`, `test_custom_classes.py` |
| `click.formatting.iter_rows` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.formatting.join_options` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.formatting.measure_table` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.formatting.wrap_text` | public-submodule-definition | Contract passed | `test_formatting.py` |
| `click.get_app_dir` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.get_binary_stream` | official-api-reference | Contract passed | `test_deprecations.py` |
| `click.get_current_context` | official-api-reference, top-level-export | Contract passed | `test_context.py`, `test_defaults.py`, `test_chain.py` |
| `click.get_pager_file` | official-api-reference, top-level-export | Contract passed | `test_termui.py` |
| `click.get_text_stream` | official-api-reference | Contract passed | `test_deprecations.py` |
| `click.getchar` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_termui.py`, `test_echo.py` |
| `click.globals.get_current_context` | public-submodule-definition | Contract passed | `test_context.py`, `test_defaults.py`, `test_chain.py` |
| `click.globals.pop_context` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.globals.push_context` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.globals.resolve_color_default` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.group` | official-api-reference, top-level-export | Contract passed | `test_context.py`, `test_arguments.py`, `test_normalization.py`, `test_commands.py`; +8 in JSON |
| `click.help_option` | official-api-reference, top-level-export | Contract passed | `test_context.py`, `test_options.py`, `test_formatting.py`, `test_basic.py` |
| `click.launch` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.make_pass_decorator` | official-api-reference, top-level-export | Contract passed | `test_context.py` |
| `click.open_file` | official-api-reference, top-level-export | Contract passed | `test_open_file.py` |
| `click.option` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_context.py`, `test_stream_lifecycle.py`; +13 in JSON |
| `click.parser.V` | public-submodule-definition | Contract passed | `test_basic.py` |
| `click.parser.split_arg_string` | deprecated-public-export | Contract passed | `test_parser.py`, `test_deprecations.py` |
| `click.pass_context` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_context.py`, `test_arguments.py`, `test_commands.py`; +5 in JSON |
| `click.pass_obj` | official-api-reference, top-level-export | Contract passed | `test_context.py`, `test_arguments.py` |
| `click.password_option` | official-api-reference, top-level-export | Contract passed | Inventory contract; see related public class tests |
| `click.pause` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_commands.py`, `test_echo.py` |
| `click.progressbar` | official-api-reference, top-level-export | Contract passed | `test_termui.py` |
| `click.prompt` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_stream_lifecycle.py`, `test_options.py`; +5 in JSON |
| `click.secho` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_options.py`, `test_termui.py` |
| `click.shell_completion.BashComplete` | public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.CompletionItem` | official-api-reference, public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.FishComplete` | public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.PowerShellComplete` | public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.ShellComplete` | official-api-reference, public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.ZshComplete` | public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.add_completion_class` | official-api-reference, public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.get_completion_class` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.shell_completion.shell_complete` | public-submodule-definition | Contract passed | `test_shell_completion.py` |
| `click.shell_completion.split_arg_string` | public-submodule-definition | Contract passed | `test_parser.py`, `test_deprecations.py` |
| `click.style` | official-api-reference, top-level-export | Contract passed | `test_testing.py`, `test_compat.py`, `test_custom_classes.py`, `test_termui.py`; +2 in JSON |
| `click.termui.V` | public-submodule-definition | Contract passed | `test_basic.py` |
| `click.termui.clear` | public-submodule-definition | Contract passed | `test_testing.py`, `test_compat.py`, `test_shell_completion.py` |
| `click.termui.confirm` | public-submodule-definition | Contract passed | `test_termui.py`, `test_confirm.py`, `test_echo.py`, `test_prompt.py` |
| `click.termui.echo_via_pager` | public-submodule-definition | Contract passed | `test_testing.py`, `test_termui.py`, `test_echo_via_pager.py` |
| `click.termui.edit` | public-submodule-definition | Contract passed | `test_termui.py` |
| `click.termui.get_pager_file` | public-submodule-definition | Contract passed | `test_termui.py` |
| `click.termui.getchar` | public-submodule-definition | Contract passed | `test_testing.py`, `test_termui.py`, `test_echo.py` |
| `click.termui.hidden_prompt_func` | public-submodule-definition | Contract passed | `test_prompt.py` |
| `click.termui.launch` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.termui.pause` | public-submodule-definition | Contract passed | `test_testing.py`, `test_commands.py`, `test_echo.py` |
| `click.termui.progressbar` | public-submodule-definition | Contract passed | `test_termui.py` |
| `click.termui.prompt` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_stream_lifecycle.py`, `test_options.py`; +5 in JSON |
| `click.termui.raw_terminal` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.termui.secho` | public-submodule-definition | Contract passed | `test_testing.py`, `test_options.py`, `test_termui.py` |
| `click.termui.style` | public-submodule-definition | Contract passed | `test_testing.py`, `test_compat.py`, `test_custom_classes.py`, `test_termui.py`; +2 in JSON |
| `click.termui.unstyle` | public-submodule-definition | Contract passed | `test_style.py` |
| `click.testing.BytesIOCopy` | public-submodule-definition | Contract passed | `test_stream_lifecycle.py` |
| `click.testing.CliRunner` | official-api-reference, public-submodule-definition | Contract passed | `test_testing.py`, `test_context.py`, `test_stream_lifecycle.py`, `test_options.py`; +1 in JSON |
| `click.testing.EchoingStdin` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.testing.Result` | official-api-reference, public-submodule-definition | Contract passed | `test_options.py` |
| `click.testing.StreamMixer` | public-submodule-definition | Contract passed | `test_stream_lifecycle.py` |
| `click.testing.make_input_stream` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.BOOL` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.types.BoolParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.Choice` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_normalization.py`, `test_commands.py`; +5 in JSON |
| `click.types.ChoiceInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.CompositeParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.DateTime` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_basic.py` |
| `click.types.DateTimeInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.FLOAT` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.types.File` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_arguments.py`, `test_shell_completion.py`; +5 in JSON |
| `click.types.FileInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.FloatParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.FloatRange` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_FloatRange.py` |
| `click.types.FuncParamType` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_convert_type.py`, `test_FuncParamType.py` |
| `click.types.FuncParamTypeInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.INT` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_commands.py`, `test_defaults.py`; +4 in JSON |
| `click.types.IntParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.IntRange` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_options.py`, `test_termui.py`, `test_prompt.py`; +1 in JSON |
| `click.types.NumberRangeInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.OptionHelpExtra` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.ParamType` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_defaults.py`, `test_options.py`, `test_formatting.py`; +4 in JSON |
| `click.types.ParamTypeInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.Path` | public-submodule-definition | Contract passed | `test_testing.py`, `test_info_dict.py`, `test_arguments.py`, `test_commands.py`; +7 in JSON |
| `click.types.PathInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.STRING` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_commands.py`, `test_defaults.py`; +2 in JSON |
| `click.types.StringParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.Tuple` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_arguments.py`, `test_defaults.py`, `test_options.py`; +1 in JSON |
| `click.types.TupleInfoDict` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.UNPROCESSED` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_commands.py`, `test_defaults.py`, `test_options.py` |
| `click.types.UUID` | public-submodule-definition | Contract passed | `test_info_dict.py`, `test_basic.py`, `test_convert_type.py` |
| `click.types.UUIDParameterType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.UnprocessedParamType` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.types.convert_type` | public-submodule-definition | Contract passed | `test_convert_type.py` |
| `click.unstyle` | official-api-reference, top-level-export | Contract passed | `test_style.py` |
| `click.utils.R` | public-submodule-definition | Contract passed | `test_termui.py` |
| `click.utils.echo` | public-submodule-definition | Contract passed | `test_testing.py`, `test_context.py`, `test_stream_lifecycle.py`, `test_arguments.py`; +16 in JSON |
| `click.utils.format_filename` | public-submodule-definition | Contract passed | `test_format_filename.py` |
| `click.utils.get_app_dir` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.utils.make_str` | public-submodule-definition | Contract passed | Inventory contract; see related public class tests |
| `click.utils.open_file` | public-submodule-definition | Contract passed | `test_open_file.py` |
| `click.version_option` | official-api-reference, top-level-export | Contract passed | `test_basic.py` |
| `click.wrap_text` | official-api-reference, top-level-export | Contract passed | `test_formatting.py` |

## Reproduction

```sh
python -m pip install -r requirements-dev.txt
maturin build --release --locked --out dist
python -m pip install --no-deps --force-reinstall dist/*.whl
python scripts/run_compatibility.py
python scripts/api_inventory.py --compare compatibility/api-reference.json --output reports/api.json
python -m mypy .cache/click-migrated/tests/typing --no-incremental
python benchmarks/compare.py
```
