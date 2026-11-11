# Shell 补全与实际执行验证

zclick 提供与 Click 8.5.1 对应的 Bash、Zsh、Fish 和 PowerShell 补全协议。补全请求通过专用环境变量进入解析与补全接口；测试中的业务回调会写入标记文件，实际执行补全后确认该文件没有生成。这个检查针对命令业务回调，不承诺用户自定义参数回调或补全提供者没有自身的副作用。

## 启用补全

下面以已安装到 `PATH` 的命令 `my-app` 为例，其默认补全环境变量为 `_MY_APP_COMPLETE`。如果应用显式指定了 `complete_var`，请使用应用配置的名称。

```bash
# Bash
eval "$(_MY_APP_COMPLETE=bash_source my-app)"

# Zsh
eval "$(_MY_APP_COMPLETE=zsh_source my-app)"
```

```fish
# Fish
env _MY_APP_COMPLETE=fish_source my-app | source
```

```powershell
# PowerShell
$previousComplete = $env:_MY_APP_COMPLETE
try {
    $env:_MY_APP_COMPLETE = 'powershell_source'
    my-app | Out-String | Invoke-Expression
} finally {
    $env:_MY_APP_COMPLETE = $previousComplete
}
```

生成的代码由相应 Shell 执行，所以应用及其自定义补全提供者应当来自可信来源。加载后可以补全命令、选项、类型提供的候选值及文件路径；应用可以通过 `shell_complete` 和 `CompletionItem` 提供自己的候选与描述。

## 实测范围

[`tests/test_surface_shell.py`](../tests/test_surface_shell.py) 在真实 Shell 进程中执行生成的脚本。0.1.1a1 发布时的 Linux 本地实验使用系统 Bash 和 Zsh，以及从官方发布资产获取、校验 SHA-256 的 Fish 4.9.3 与 PowerShell 7.7.0。后续 CI 为避免 Ubuntu 软件源连续 DNS 故障阻断验证，改为从固定官方源码构建相同的 Zsh 5.9。每次实际执行使用的路径和版本仍单独写入报告；版本与下载来源记录在 [`compatibility/shell-runtime-lock.json`](../compatibility/shell-runtime-lock.json)。

| Shell | 执行方式 | 已检查的结果 | 边界 |
| --- | --- | --- | --- |
| Bash | 加载生成代码，调用补全函数，执行真实 `compgen`。 | 包含空格的两个文件名分别保留为一个候选；业务回调不执行。 | `compopt` 依赖交互式 Readline 状态，测试用一个检查参数的函数代替该终端钩子；未模拟真实按键。 |
| Zsh | 在真实 Zsh 中调用生成的补全函数和应用子进程。 | 选项候选 `alpha`、`alpine` 正确返回；业务回调不执行。 | `compdef`、`compadd` 是非交互测试的记录钩子，未模拟完整 ZLE 界面。 |
| Fish | 通过真实 `complete -C` 补全引擎运行生成代码。 | 选项候选正确返回，业务回调不执行。 | 未覆盖所有终端主题、键位和用户配置；使用 `--no-config` 隔离配置。 |
| PowerShell | 通过真实 `CommandCompletion.CompleteInput` 补全引擎执行注册的回调。 | 选项候选正确；文件候选保留路径空格；目录候选排除普通文件；业务回调不执行。 | Linux 本地结果与 Windows CI 结果分别记录，不能相互替代平台证据。 |

PowerShell 的目录过滤曾在实际执行对照中发现差异：zclick 返回了目录和普通文件，而固定版本 Click 只返回目录。实现已修正，并保留独立的文件与目录回归测试。PowerShell 对含空格的文件路径返回的 `CompletionText` 保持目标 Click 的形式；本项目没有为追求更理想的行为而擅自改变固定目标的协议。

固定版本官方补全测试另外覆盖协议文本、自定义补全、参数数量、链式命令和上下文定位。官方协议测试与真实 Shell 测试回答不同的问题：前者比较库返回什么，后者检查生成的脚本能否在 Shell 中消费这些返回值。

## 复现实际 Shell 测试

先构建并安装当前 zclick。在 Linux x86_64 上，安装脚本可以准备固定版本的 Zsh、Fish 和 PowerShell；Bash 使用系统提供的可执行文件：

```sh
python scripts/install_test_shells.py
export PATH="$PWD/.cache/test-shells/zsh/bin:$PWD/.cache/test-shells/fish:$PWD/.cache/test-shells/pwsh:$PATH"
```

Zsh 构建需要 C 编译器、`make`、`dpkg-deb` 和宿主的 `libtinfo.so.6`。开发头文件来自固定 SHA-256 的官方 Debian ncurses 6.5 开发包，只解包到临时目录，安装器不修改系统软件包状态。脚本使用 Zsh 发布包自带的 `configure`，按该版本支持的 GNU C89 模式编译，保留编译诊断；这使旧版 feature probe 不受新版 GCC 默认 C 标准改变的影响。构建只编译可执行文件与动态模块，再安装补全所需的 autoload 函数；完成或失败时均清理临时源码和开发头文件，保留构建日志。安装后会加载 ZLE、completion 模块及 `compinit` 定义，检查二进制和补全资源能一起使用。安装来源、编译配置、压缩包 SHA-256 和可执行文件 SHA-256 写入 `reports/shells/install.json`。

Zsh 的固定包为官方 [`zsh-5.9.tar.xz`](https://www.zsh.org/pub/old/zsh-5.9.tar.xz)，SHA-256 为 `9b8d1ecedd5b5e81fbf1918e876752a7dd948e05c1a0dba10ab863842d45acd5`。固定版本时已用官方 HTTPS keyring 验证该包的 detached signature，签名指纹为 `7CA7ECAAF06216B90F894146ACF8146CAE8CBBC4`；这不包含额外 Web-of-Trust 身份认证。后续安装按已固定的 SHA-256 检查每次下载的内容。

然后确认四种 Shell 都已进入当前进程的 `PATH` 并执行检查：

```sh
command -v bash
command -v zsh
command -v fish
command -v pwsh
python scripts/check_shells.py
```

检查脚本要求四种 Shell 全部可执行，并在发生任何跳过或失败时返回非零状态。它把运行时版本、逐项结果和来源哈希写到 `reports/shells/`。直接运行 `pytest tests/test_surface_shell.py` 时，缺少 Shell 会明确显示跳过；这种结果不构成四种 Shell 全部已执行的证据。Bash 低于 4.4 的情况遵守目标 Click 的支持边界。

## 来源与证据自审

- [Fish `complete` 官方文档](https://fishshell.com/docs/current/cmds/complete.html)定义 `complete -C` 的执行方式；本项目使用该接口调用实际补全引擎。
- [PowerShell `CommandCompletion` 官方 API](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.commandcompletion)定义补全结果和 `CompleteInput`；本项目检查返回的候选内容。
- Bash 和 Zsh 的记录钩子限制在表格中明确给出，未把非交互测试宣称为完整终端按键验证。
- 六项独立实际执行检查、三项链式补全回归检查与固定版本官方补全用例分别记录，结论均可以映射到具体测试断言。
- 本轮没有从这些功能测试推断补全启动延迟、所有 Shell 版本兼容或用户自定义补全逻辑的正确性。
