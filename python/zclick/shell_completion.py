"""Shell wire protocols and completion context traversal.

Completion resolves contexts with resilient parsing and never invokes a command's
business callback. Completion providers themselves remain ordinary Python hooks.
"""
from __future__ import annotations

import contextlib
import os
import re
import shlex
import subprocess
import typing as t

from .utils import echo

V = t.TypeVar("V", covariant=True)


class CompletionItem(t.Generic[V]):
    __slots__ = ("value", "type", "help", "_info")

    def __init__(self, value: V, type: str = "plain", help: str | None = None, **kwargs: t.Any) -> None:
        self.value, self.type, self.help, self._info = value, type, help, kwargs

    def __getattr__(self, name: str) -> t.Any:
        return self._info.get(name)


def split_arg_string(string: str) -> list[str]:
    lexer = shlex.shlex(string, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words: list[str] = []
    try:
        for word in lexer:
            words.append(word)
    except ValueError:
        if lexer.token:
            words.append(lexer.token)
    return words


def _resolve_context(cli: t.Any, ctx_args: dict[str, t.Any], prog_name: str, args: list[str], stack: contextlib.ExitStack) -> t.Any:
    from .core import Group
    current_args = list(args)
    ctx = cli.make_context(prog_name, current_args, **{**ctx_args, "resilient_parsing": True})
    stack.callback(ctx.close)
    ctx._completion_args = list(args)
    while isinstance(ctx.command, Group):
        remainder = ctx._protected_args + ctx.args
        if not remainder:
            break
        group_ctx = ctx
        if not ctx.command.chain:
            name, child, remaining = ctx.command.resolve_command(ctx, remainder)
            if child is None:
                break
            completion_args = list(remaining)
            ctx = child.make_context(name, remaining, parent=ctx, resilient_parsing=True)
            stack.callback(ctx.close)
            ctx._completion_args = completion_args
            continue
        used: list[str] = []
        while remainder:
            name, child, remaining = group_ctx.command.resolve_command(group_ctx, remainder)
            if child is None:
                remainder = []
                break
            used.append(name)
            completion_args = list(remaining)
            ctx = child.make_context(name, remaining, parent=group_ctx, resilient_parsing=True, allow_extra_args=True, allow_interspersed_args=False)
            stack.callback(ctx.close)
            ctx._completion_args = completion_args
            remainder = ctx.args
            if isinstance(child, Group):
                break
        group_ctx._completion_used_commands = used
        if ctx is group_ctx:
            break
    return ctx


def _resolve_incomplete(ctx: t.Any, incomplete: str) -> t.Any:
    from .core import Argument, Option
    args = getattr(ctx, "_completion_args", [])
    params = ctx.command.get_params(ctx)
    options = {name: p for p in params if isinstance(p, Option) for name in p.opts + p.secondary_opts}
    if "--" not in args and incomplete and any(incomplete.startswith(prefix) for prefix in ctx._opt_prefixes):
        return ctx.command
    pending = None
    needed = 0
    positional = 0
    terminated = False
    for arg in args:
        if needed:
            if pending._flag_needs_value and arg in options:
                needed = 0
            else:
                needed -= 1
                continue
        if arg == "--" and not terminated:
            terminated = True
            continue
        option_name, eq, attached = arg.partition("=")
        option = None if terminated else options.get(option_name)
        if option is not None:
            if not option.is_flag and not option.count:
                pending = option
                needed = option.nargs - int(bool(eq))
            continue
        if not terminated and len(arg) > 2 and arg[:2] in options:
            option = options[arg[:2]]
            if not option.is_flag and not option.count:
                pending, needed = option, max(0, option.nargs - 1)
            continue
        if not terminated and arg and any(arg.startswith(p) for p in ctx._opt_prefixes):
            continue
        positional += 1
    if needed and pending is not None:
        return pending
    for parameter in params:
        if isinstance(parameter, Argument):
            if parameter.nargs == -1 or positional < parameter.nargs:
                return parameter
            positional -= parameter.nargs
    return ctx.command


class ShellComplete:
    name = ""
    source_template = ""

    def __init__(self, cli: t.Any, ctx_args: t.MutableMapping[str, t.Any], prog_name: str, complete_var: str) -> None:
        self.cli, self.ctx_args, self.prog_name, self.complete_var = cli, ctx_args, prog_name, complete_var

    def source_vars(self) -> dict[str, str]:
        return {"complete_func": self.func_name, "prog_name": self.prog_name, "complete_var": self.complete_var}

    @property
    def func_name(self) -> str:
        return "_" + re.sub(r"[^a-zA-Z0-9_]", "", self.prog_name.replace("-", "_")) + "_completion"

    def source(self) -> str:
        return self.source_template % self.source_vars()

    def get_completion_args(self) -> tuple[list[str], str]:
        raise NotImplementedError()

    def get_completions(self, args: list[str], incomplete: str) -> list[CompletionItem[str]]:
        with contextlib.ExitStack() as resources:
            ctx = _resolve_context(self.cli, dict(self.ctx_args), self.prog_name, args, resources)
            target = _resolve_incomplete(ctx, incomplete)
            with ctx.scope(cleanup=False):
                return target.shell_complete(ctx, incomplete)

    def format_completion(self, item: CompletionItem[str]) -> str:
        raise NotImplementedError()

    def complete(self) -> str:
        args, incomplete = self.get_completion_args()
        return "\n".join(self.format_completion(item) for item in self.get_completions(args, incomplete))


class BashComplete(ShellComplete):
    name = "bash"
    source_template = r'''%(complete_func)s() {
    local type value completion
    COMPREPLY=()
    while IFS=, read -r type value; do
        case "$type" in
            dir)
                compopt -o filenames
                while IFS= read -r completion; do
                    COMPREPLY+=( "$completion" )
                done < <(compgen -d -- "$value")
                ;;
            file)
                compopt -o filenames
                while IFS= read -r completion; do
                    COMPREPLY+=( "$completion" )
                done < <(compgen -f -- "$value")
                ;;
            plain) COMPREPLY+=( "$value" ) ;;
        esac
    done < <(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD="$COMP_CWORD" %(complete_var)s=bash_complete %(prog_name)s)
}
complete -o nosort -F %(complete_func)s %(prog_name)s
'''

    def _check_version(self) -> bool:
        try:
            version = subprocess.check_output(["bash", "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"], text=True).strip()
            return tuple(map(int, version.split("."))) >= (4, 4)
        except (OSError, ValueError, subprocess.CalledProcessError):
            return False

    def source(self) -> str:
        if not self._check_version():
            echo("Shell completion is not supported for Bash versions older than 4.4.", err=True)
            return ""
        return super().source()

    def get_completion_args(self) -> tuple[list[str], str]:
        words = split_arg_string(os.environ.get("COMP_WORDS", ""))
        cursor = int(os.environ.get("COMP_CWORD", "0"))
        return words[1:cursor], words[cursor] if cursor < len(words) else ""

    def format_completion(self, item: CompletionItem[t.Any]) -> str:
        return f"{item.type},{item.value}"


class ZshComplete(BashComplete):
    name = "zsh"
    source_template = r'''#compdef %(prog_name)s
%(complete_func)s() {
    local -a response values descriptions
    local type value description
    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) %(complete_var)s=zsh_complete %(prog_name)s)}")
    while (( ${#response} )); do
        type=$response[1]; value=$response[2]; description=$response[3]
        shift 3 response
        case "$type" in
            dir) _path_files -/ ;;
            file) _path_files ;;
            plain) if [[ "$description" == _ ]]; then compadd -- "$value"; else values+=("$value:$description"); fi ;;
        esac
    done
    (( ${#values} )) && _describe values values
}
compdef %(complete_func)s %(prog_name)s
'''

    def source(self) -> str:
        return ShellComplete.source(self)

    def format_completion(self, item: CompletionItem[str]) -> str:
        value = item.value.replace(":", "\\:") if item.help else item.value
        return f"{item.type}\n{value}\n{item.help or '_'}"


class FishComplete(ShellComplete):
    name = "fish"
    source_template = r'''function %(complete_func)s
    set -l response (env %(complete_var)s=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -ct) %(prog_name)s)
    for line in $response
        set -l item (string split -m 1 , -- $line)
        switch $item[1]
            case dir
                __fish_complete_directories $item[2]
            case file
                __fish_complete_path $item[2]
            case plain
                echo $item[2]
        end
    end
end
complete -c %(prog_name)s -f -a '(%(complete_func)s)'
'''

    def get_completion_args(self) -> tuple[list[str], str]:
        words = split_arg_string(os.environ.get("COMP_WORDS", ""))
        incomplete_parts = split_arg_string(os.environ.get("COMP_CWORD", ""))
        incomplete = incomplete_parts[0] if incomplete_parts else ""
        args = words[1:]
        if incomplete and args:
            args.pop()
        return args, incomplete

    def format_completion(self, item: CompletionItem[str]) -> str:
        suffix = "\t" + item.help.replace("\n", "\\n").replace("\t", " ") if item.help else ""
        return f"{item.type},{item.value}{suffix}"


class PowerShellComplete(BashComplete):
    name = "powershell"
    source_template = r'''Register-ArgumentCompleter -Native -CommandName %(prog_name)s -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $oldMode = $env:%(complete_var)s
    $oldWords = $env:COMP_WORDS
    $oldWord = $env:COMP_CWORD
    try {
        $env:%(complete_var)s = 'powershell_complete'
        $env:COMP_WORDS = $commandAst.Extent.Text.Substring(0, $cursorPosition)
        $env:COMP_CWORD = [string]($commandAst.CommandElements.Count - [int]([bool]$wordToComplete))
        $items = @(& %(prog_name)s)
        for ($i = 0; $i + 2 -lt $items.Count; $i += 3) {
            $value = $items[$i + 1]
            $help = $items[$i + 2]
            if ($help -eq '_') { $help = $value }
            if ($items[$i] -eq 'file' -or $items[$i] -eq 'dir') {
                $paths = Get-ChildItem -Path ($value + '*') -ErrorAction SilentlyContinue
                if ($items[$i] -eq 'dir') { $paths = $paths | Where-Object { $_.PSIsContainer } }
                $paths | ForEach-Object {
                    [System.Management.Automation.CompletionResult]::new($_.FullName, $_.Name, 'ProviderItem', $_.FullName)
                }
            } else {
                [System.Management.Automation.CompletionResult]::new($value, $value, 'ParameterValue', $help)
            }
        }
    } finally {
        $env:%(complete_var)s = $oldMode
        $env:COMP_WORDS = $oldWords
        $env:COMP_CWORD = $oldWord
    }
}
'''

    def source(self) -> str:
        return ShellComplete.source(self)

    def format_completion(self, item: CompletionItem[str]) -> str:
        help = item.help.replace("\n", " ").replace("\r", " ") if item.help else "_"
        return f"{item.type}\n{item.value}\n{help}"


_available_shells: dict[str, type[ShellComplete]] = {cls.name: cls for cls in (BashComplete, ZshComplete, FishComplete, PowerShellComplete)}


def add_completion_class(cls: type[V], name: str | None = None) -> type[V]:
    _available_shells[cls.name if name is None else name] = cls
    return cls


def get_completion_class(shell: str) -> type[ShellComplete] | None:
    return _available_shells.get(shell)


def shell_complete(cli: t.Any, ctx_args: t.MutableMapping[str, t.Any], prog_name: str, complete_var: str, instruction: str) -> t.Literal[0, 1]:
    shell, separator, action = instruction.partition("_")
    cls = get_completion_class(shell)
    if not separator or cls is None or action not in ("source", "complete"):
        return 1
    completion = cls(cli, ctx_args, prog_name, complete_var)
    output = completion.source() if action == "source" else completion.complete()
    echo(output.encode("utf-8") if action == "source" else output)
    return 0
