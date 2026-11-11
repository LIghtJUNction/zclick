# zclick 0.1.1a1 交付记录

## 结论与当前边界

本轮在 [LIghtJUNction/zclick](https://github.com/LIghtJUNction/zclick) 中实现了可构建、可安装的 Python/Rust 命令行库，提供 `zclick` 公开命名空间及对应子模块，原生解析使用发布到 registry 的 zclap。代码、测试、示例、类型声明、性能测量、跨平台构建和自动发布流程已分阶段提交。

**当前版本为预发布 `0.1.1a1`，完整兼容验收尚未达成。** 已确认的兼容缺口是 CPython 子解释器：原版 Click 可以在已验证的主解释器先初始化场景中使用，当前 zclick 会明确拒绝子解释器导入。固定官方测试集通过不能消除这一差异；仓库保持 `UNFINISHED` 记录，并阻止带有未解决兼容项的稳定版本发布。[兼容性清单](../COMPATIBILITY.md)和[机器可读缺口记录](../compatibility/known-gaps.json)给出了范围与复现入口。

本轮的运行时代码冻结于 `86bab2a8de3092155a912a4028382aba8188e6db`。本地基准记录该提交，首轮独立 CI 记录 `a8bc735a3df168b62b2e11d99b34e7ab40530ba7`，最终发布 CI 记录 `3281e18f215dec976c3ce0c4b5dd933ad4d62616`。这三次测量之间没有更改运行时代码；后续提交只更新发布说明、测试证据规范化和构建编排。三份原始数据均保留，实际发布结果列在本记录末尾。

## 固定目标和依赖

| 项目 | 本轮固定值 | 证据 |
| --- | --- | --- |
| Click 兼容目标 | **8.5.1**，2026-11-06 发布，2026-11-11 核验 | [target.json](../compatibility/target.json) |
| Click 源码 | `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1` | 同一提交的文档、公开 API 与官方测试，不混用移动中的文档版本 |
| zclap | registry 精确版本 **0.1.4** | [zclap.json](../compatibility/zclap.json)、Cargo.lock 校验和 |
| zclap 对应源码 | `4d87f3ae3743e81509d5ac5500909955667c860f` | 已对照发布包的 VCS 信息与当前源码、测试 |
| 原生绑定 | **PyO3 0.30.1** | Cargo.lock，包含必要的传递与构建依赖 |
| Rust / MSRV | 实际验证的 **1.99.1**，Edition **2024** | rust-toolchain.toml、CI 编译与 no_std 检查 |
| Python | 声明最低 **3.10** | pyproject.toml 与各解释器 CI |
| Python 默认运行时依赖 | 空 | wheel 元数据检查；原版 Click 仅属于开发、对照测试环境 |

发行包只安装 `zclick`，不覆盖原版 `click`，不通过 `sys.modules` 改写其他库的导入。Maturin、pytest、Hypothesis、mypy 和 Click 对照环境与默认运行时依赖分开管理。[依赖审计脚本](../scripts/audit_dependencies.py)与[发行包检查脚本](../scripts/check_wheel.py)分别检查源码依赖边界和实际包内容。

## 使用和实现

应用迁移的基本改动是：

```python
import zclick as click
from zclick.testing import CliRunner
from zclick.types import ParamType
from zclick.core import Command, Group, Context
```

原有 `from click.xxx` 导入应对应改为 `from zclick.xxx`。公开类型声明和 `py.typed` 随包提供。三个可执行示例分别覆盖问候与提示、链式命令与结果回调、以及自定义类型、上下文资源和超过 64 位的整数；README 中的三个执行命令已实际运行，输出分别为两行 `Hello, Ada!`、`HELLO Rust` 和 `demo: 18446744073709551616`。[示例入口](../README.md#examples)

### 代码分层

| 层 | 当前实现职责 |
| --- | --- |
| Python 公开层 | 类与装饰器、Context 生命周期、可覆盖的参数钩子、默认值与环境读取、Python 类型转换、帮助组装、终端工具、补全和 testing |
| Rust/PyO3 绑定层 | 解析动作编排、组命令分发、Python 对象所有权和安全回调 |
| Rust 语义核心 | token 与 arity 处理、位置参数分配、参数执行顺序、值来源选择、ANSI 与文本换行 |
| zclap | 通过真实事件解析识别选项，执行 `finish()` 最终检查，参与消费后参数值的字节解析 |

这是具有较多 Python 职责的混合实现，不能称为整个库都由 Rust 执行。公开对象和任意用户方法仍然遵守 Python 的动态规则；Rust 负责上述集中计算和编排路径。核心 crate 使用 `no_std + alloc`，直接第三方依赖只有 zclap；Python 扩展使用 `std`、PyO3，并会创建和分配 Python 对象。[架构与源码说明](architecture.md)

调用开始时会从当前参数对象重新建立解析计划。这样，修改 `command.params`、选项属性、类型转换方法或 callback 后，下一次调用能观察到变化。默认值函数、环境变量、提示输入和 Context 状态不会作为执行结果缓存。代价是每次调用都有结构转换和分配成本，性能表包含这些成本。

zclap 只借用当前调用拥有的字符串和参数表，没有 `Box::leak`、永久字符串驻留或伪造 `'static`。回调期间不持有会阻止重入的原生可变借用；原生分发对象参与 GC，并在整个 Python scope 返回或抛出后释放捕获引用。Python 整数转换保留任意精度，带 surrogate 的字符串采用可逆表示，库内部不调用 Rust `process::exit` 杀死宿主。[动态语义测试](../tests/test_dynamic_semantics.py)、[原生分发测试](../tests/test_native_dispatch.py)

## 测试方法与已取得证据

兼容清单来自固定版本的官方 API 和源码，包含 **196 项公开 API**及其成员、签名、默认值、属性和弃用行为。官方测试库存包含 **33,459 个唯一用例 ID**，其中 **31,000 个为压力用例**；清单和排序后哈希固定在 [test-manifest.json](../compatibility/test-manifest.json)。

迁移测试只修改包名、模块引用、monkeypatch 路径、子进程导入、发行元数据查找及必要的模块限定 repr。没有修改行为断言、输入参数、预期结果或原版 skip/xfail 条件。每轮保存迁移日志、逐例结果、实现提交和源码哈希，发布门禁验证精确的 ID 集合。

冻结快照 `86bab2a8` 的 [CI 43028777836](https://github.com/LIghtJUNction/zclick/actions/runs/43028777836) 已全部成功：Linux CPython 3.10–3.15、3.14t/3.15t、PyPy 3.11/3.12，macOS 与 Windows CPython 3.14，以及 Rust、四 Shell 和子解释器安全诊断。各平台保留不同的原版平台跳过条件，不能把它们写成实际执行通过的用例。

在本地冻结快照的最后一次压力对照中，**Click 与 zclick 各 31,000 passed，双方 0 failed、0 skipped、0 xfailed，缺失和额外用例均为 0**。31,000 个唯一 ID 的 SHA-256 为 `41721cdd2cdc8245395eb046937570a7d9ce8c8e5945c306ef6e98d7ce8a048a`；该次原生模块 SHA-256 为 `87f1d9d65e88eb08bea9b31afaf35fe9ae45cd3a3976f28919e5e01f1c958bea`。原始结果保留在 `reports/final-stress-fixed`，未将后来的 Git 提交号覆盖到旧报告中。

首轮 [Release 43029689108](https://github.com/LIghtJUNction/zclick/actions/runs/43029689108) 的各平台普通、压力、API、typing、Shell 和安全测试均成功，证据汇总发现了 Python 3.10 的五个枚举参数 ID 显示差异。修复只规范这五个完整 ID，并新增同份报告内的碰撞拒绝；重放真实报告后，33,459 项及原清单 SHA-256 均完全一致，未修改行为断言。最终发布仍要求新提交重新通过完整验收与实际安装包执行检查，结果和平台计数列在本记录末尾。

## 性能结果

比值统一定义为 **Click 耗时 / zclick 耗时**；大于 1 表示该场景下 zclick 更快，小于 1 表示性能回退。两个环境均使用 release 构建、9 轮样本，并保存原始 wall/CPU 时间与源码哈希。以下不是对任意 CLI 应用的统一加速承诺。[完整方法、每项时间和内存表](performance.md)

| 场景 | 本地 CPython 3.12 | 最终发布 CI CPython 3.14 |
| --- | ---: | ---: |
| 热调用，1 个选项 | 0.694× | 1.058× |
| 热调用，10 个选项 | 0.822× | 1.151× |
| 热调用，100 个选项 | 1.148× | 1.169× |
| 热调用，1,000 个选项 | **1.706×** | **1.997×** |
| 复用底层 parser，1 个选项 | 0.403× | 0.520× |
| 复用底层 parser，1,000 个选项 | 0.660× | 0.435× |
| 嵌套命令 | 0.970× | 0.889× |
| Unicode/ANSI 文本换行 | **7.344×** | **8.724×** |
| 全新进程，1,000 选项命令 | 1.183× | 1.148× |
| 全新进程，1,000 选项 `--help` | 1.288× | 1.017× |

1,000 选项热调用在本地从 **11.176 ms 降到 6.553 ms**，在最终发布 CI 从 **11.149 ms 降到 5.582 ms**。该边界复用已经定义的 Command，但包含新 Context、解析计划、参数处理、转换和回调。全新进程测量另行包含 Python 启动、导入、Option/Command 构造、执行、输出捕获和进程退出。

冷启动帮助收益没有稳定复现：1,000 选项命令在最终 CI 从 **63.205 ms 到 55.066 ms**，比值为 1.148×；同规模帮助仅从 **63.471 ms 到 62.415 ms**，比值为 1.017×。保留的首轮 CI 对照还记录到帮助从 **73.347 ms 到 76.995 ms**，比值为 0.953×。因此不能把本地 1.288× 的冷启动帮助结果当成普遍结论，也不能宣传小命令必然提速。

从执行成本看，Rust 省下的是解释循环、参数编排和文本处理中的一部分工作；跨 Python/Rust 边界、读取可变对象、建立当前调用的数据结构和返回 Python 对象仍要耗时。小任务里，这些固定成本可能超过计算本身；较大的命令和文本处理才在两台主机上都表现出明确收益。测量没有把每一种成本单独隔离，因此这是一种结合代码路径的解释，不是独立的分项性能归因实验。

两个环境都按 Click 再 zclick 的固定顺序运行，没有绑定 CPU 或锁定频率，主机、解释器和缓存状态也不同。小幅差异不能解释为统计显著结果。Python `tracemalloc` 不包含所有 Rust 分配；本地进程峰值 RSS 分别约为 **22.78 MiB 与 23.82 MiB**。本项目没有零分配或内存全面减少的结论。

## 尚未完成和需要单独处理的场景

**CPython 子解释器兼容仍未完成。** PyO3 0.30.1 中部分 Python 对象缓存不按解释器隔离，直接放行可能让一个解释器调用另一个解释器保存的对象。因此当前模块在初始化最早阶段检查解释器身份，对子解释器抛出 ImportError，同时验证主解释器随后仍可调用。这个保护解决的是错误共享对象的风险，没有实现 Click 的子解释器行为。

诊断分别记录安全拒绝和兼容是否通过，也保留原版的环境问题：本地 CPython 3.12 在部分 child-first 导入/销毁顺序下，原版 Click 和独立的 datetime 对照均出现 teardown 崩溃，报告保留返回码而没有预热导入来隐藏它。能够稳定工作的 main-first 原版场景仍足以表明 zclick 存在差异。[解释器边界说明](development.md#interpreter-compatibility-boundary)

**第三方扩展的内部导入需要单独迁移。** 实测的 `click-didyoumean==0.3.1`、`click-plugins==1.1.1.2` 和 `click-repl==0.4.1` 仍然导入原版 Click，分别涉及原版类继承、`isinstance` 检查或上下文栈差异。应用里的别名只改变该模块的名字绑定，不会改写扩展文件自己的导入。这些诊断测试通过不代表扩展已经兼容。[完整扩展报告](extensions.md)

**CliRunner 仍有解释器和进程状态边界。** 它会替换流、环境和工作目录，不应作为同一进程中多个线程并发隔离的工具。free-threaded 构建成功与其线程安全是两件不同的事；本轮没有借此宣称并行加速。

平台结论仅覆盖列出的解释器、操作系统和实际执行路径。Windows 宽字符缓冲区回归包含系统 API 边界模拟，四 Shell 补全则实际执行生成的 shell source；不把两者统称为每一种终端设备都已验证。

## 构建和发布机制

发布前固定不可变提交，完整兼容性与安全验证和 wheel/sdist 构建并行执行；只有两方面全部成功才进入发布。wheel 在源码目录之外安装并执行，musllinux 包在固定摘要的 Alpine 镜像中验证；sdist 会重新构建 wheel 后再执行。类型声明、项目许可证、Click API 声明许可和 Rust 依赖通知随发行包提供，并核对 notice 原始字节的哈希。[构建与发布指南](development.md)

版本脚本同时更新 Python、Cargo 工作区和 lockfile，支持 prerelease、patch、minor、major 和显式版本。标签必须与项目版本一致；本次使用 `release: 0.1.1a1` 提交触发同一套完整门禁。GitHub Release 和 PyPI 上传是两个独立任务，前者成功并不自动代表后者已认证并发布。[发布工作流](../.github/workflows/release.yml)

## 主要文件

| 内容 | 文件 |
| --- | --- |
| 入门、导入迁移与示例 | [README.md](../README.md) |
| 公开 API、行为、平台与测试映射 | [COMPATIBILITY.md](../COMPATIBILITY.md) |
| 固定目标、完整测试 ID、未完成项 | [compatibility/](../compatibility/) |
| 实现与依赖边界 | [architecture.md](architecture.md) |
| 两台主机的性能与内存原始结果 | [performance.md](performance.md)、[benchmarks/results/](../benchmarks/results/) |
| 开发、完整验证、版本和发布 | [development.md](development.md) |
| 扩展与补全 | [extensions.md](extensions.md)、[shell-completion.md](shell-completion.md) |
| 本次版本变化 | [CHANGELOG.md](../CHANGELOG.md) |

## 最终发布结果

**GitHub 预发布和 PyPI 发布均已成功。** [Release v0.1.1a1](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a1) 的实际 Git 标签指向 `3281e18f215dec976c3ce0c4b5dd933ad4d62616`。GitHub 发布页包含 12 个 wheel、1 个 sdist、原始基准 JSON、完整兼容性证据 ZIP 和发布说明，共 16 个文件；这些公开下载文件均已逐个验证与 GitHub 资产元数据的 SHA-256 一致。[PyPI 的同版本页面](https://pypi.org/project/zclick/0.1.1a1/)提供同一批 13 个发行包，其 SHA-256 与 GitHub 已验证文件逐个一致。

公开下载的 Linux x86_64 wheel 还在未安装原版 Click 的全新虚拟环境中再次安装执行，原生解析、组命令、Unicode 输出、大整数和帮助均通过，未出现 `click` 模块注入。这项检查使用公开 Release 的实际文件，与 CI 原生模块烟测分开记录。

| 发布任务 | 实际结果 |
| --- | --- |
| 固定源码完整验收与证据门禁 | [成功](https://github.com/LIghtJUNction/zclick/actions/runs/43031862640/job/130565817963)，33,459 个原始 ID 与固定哈希一致 |
| 12 个 wheel | 全部构建、检查并实际安装执行成功 |
| sdist | 从源码包重新构建 wheel，安装执行成功 |
| GitHub Release | [成功](https://github.com/LIghtJUNction/zclick/actions/runs/43031862640/job/130565922406)，明确标记 prerelease |
| PyPI 上传 | [第二次尝试成功](https://github.com/LIghtJUNction/zclick/actions/runs/43031862640/job/130584511741)，2026-11-11 14:28:58 UTC 完成；13 个发行包已公开 |

首次 Release workflow 为 60 个任务成功、1 个任务失败，唯一失败任务是 PyPI 上传返回 `invalid-publisher`。配置发布者后，仅重跑失败的上传任务，第二次尝试于 **2026-11-11 14:28:58 UTC** 成功，workflow 当前结论为 `success`。本次重试使用已验证的相同发行文件，没有重写旧报告或替换软件版本；[PyPI 元数据与制品哈希核验](../compatibility/releases/0.1.1a1-pypi.json)保留独立确认结果。

### 正式发布证据中的测试计数

以下是每个实现各自的结果；Click 与 zclick 对应计数相同。完整机器可读摘要位于 [compatibility/releases/0.1.1a1.json](../compatibility/releases/0.1.1a1.json)，原始逐例记录随 Release 的 `compatibility-evidence.zip` 发布。

| 环境范围 | 官方普通测试 | 官方压力测试 |
| --- | --- | --- |
| Linux 的 10 个普通测试环境：CPython 3.10–3.15、3.14t/3.15t、PyPy 3.11/3.12 | 每个环境 2,434 passed、24 skipped、1 xfailed | 其中 CPython 3.14、3.14t/3.15t、PyPy 3.11/3.12 五个环境，各 31,000 passed |
| macOS ARM64 / CPython 3.14 | 2,433 passed、25 skipped、1 xfailed | 31,000 passed |
| Windows x64 / CPython 3.14 | 2,357 passed、101 skipped、1 xfailed | **30,000 passed、1,000 skipped** |

Windows 的 1,000 个压力跳过来自[固定上游源码的 pager 平台条件](https://github.com/pallets/click/blob/cf19179e8e2fd54c601378cec9e0d21bb12b6fb1/tests/test_utils/test_echo_via_pager.py)，两侧均保留，未计作执行通过。其余六个压力环境没有压力跳过。所有普通测试环境还通过 196 项公开 API 契约和 12 个官方 typing 文件；四种真实 Shell 的 9 项执行测试通过。Bash、Zsh 使用非交互记录钩子接收终端编辑器集成调用，Fish 和 PowerShell 调用实际补全引擎，具体范围在原始证据中保留。

wheel 的实际安装检查覆盖 Linux glibc/musl 的 x86_64 与 ARM64、macOS Intel 与 ARM64、Windows x64 与 ARM64，以及 Linux x86_64 的 PyPy 3.11/3.12、CPython 3.14t/3.15t。**安装 smoke 与完整官方套件是不同验证范围**；例如 Windows ARM64 和 musllinux 包已实际安装运行，但未据此宣称每个发行架构都执行了整套 33,459 项用例。

wheel 标签中的系统最低版本来自构建与二进制兼容性检查，实际执行系统为 CI 当前镜像；本轮未把所有标签最低系统版本逐一作为独立主机运行。

### 当前可用的安装入口

可以直接安装 PyPI 上的固定预发布版本：

```sh
python -m pip install zclick==0.1.1a1
```

也可以从 [Release 页面](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a1) 选择与解释器、系统和架构匹配的 wheel。当前工作区的普通 CPython / Linux x86_64 对应以下公开发行包：

```sh
python -m pip install https://github.com/LIghtJUNction/zclick/releases/download/v0.1.1a1/zclick-0.1.1a1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
```

普通 CPython 也可以从发布源码包构建，要求 Rust 1.99.1 与当前平台的构建工具：

```sh
python -m pip install https://github.com/LIghtJUNction/zclick/releases/download/v0.1.1a1/zclick-0.1.1a1.tar.gz
```

### PyPI 发布重试记录

第一次上传时，PyPI 返回的原因是有效身份令牌没有匹配到已配置的 publisher。账户所有者完成配置后，使用同一不可变源码提交和同一批制品重跑了失败的上传任务。第二次尝试从 2026-11-11 14:28:09 UTC 开始，14:28:58 UTC 成功完成；PyPI 元数据显示 13 个文件于 14:28:39–14:28:56 UTC 上传。

本仓库工作流使用的发布者字段为：

| 字段 | 值 |
| --- | --- |
| PyPI project name | `zclick` |
| Repository owner | `LIghtJUNction` |
| Repository name | `zclick` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

首次失败的 [job 130565922326](https://github.com/LIghtJUNction/zclick/actions/runs/43031862640/job/130565922326) 和成功重试的 [job 130584511741](https://github.com/LIghtJUNction/zclick/actions/runs/43031862640/job/130584511741) 均保留。该发布步骤现已完成；子解释器兼容缺口和预发布定位保持不变。

