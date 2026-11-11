# zclick 0.1.1a2 交付记录

## 本轮结论与发布状态

本轮完成了可复用的 Rust 解析结构、参数输入借用、受条件约束的原生排序，以及 Python 类型选择、帮助和终端格式化路径的优化。两台主机上，1,000 个选项的重复解析相对已发布 0.1.1a1 分别为 **2.535× / 2.354×**，完整调用相对 Click 8.5.1 分别为 **1.771× / 2.017×**。完整调用对旧版的改善只有 **1.042× / 1.050×**，不能称为这一版本的大幅新增收益。下文的两个数依次表示本地与发布 CI 测量。[完整性能记录](performance-0.1.1a2.md)

**纯解析对 Click 的优势没有跨主机复现。** 1,000 个选项在本地测得 1.236×，CI 则为 0.975×；CI 中 a2 的中位耗时略高。两组数据均保留，不能只选本地较好的结果。

**0.1.1a2 已发布到 [GitHub Releases](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a2) 和 [PyPI](https://pypi.org/project/zclick/0.1.1a2/)。** [Release 43052475382](https://github.com/LIghtJUNction/zclick/actions/runs/43052475382) 的 61 个任务全部成功，标签 `v0.1.1a2` 指向源码 [`7e3d597873b737bbfc8c2df090773aad56d9bd73`](https://github.com/LIghtJUNction/zclick/commit/7e3d597873b737bbfc8c2df090773aad56d9bd73)。公开 PyPI 的 12 个 wheel 与一个源码包，SHA-256 均与实际下载核对的 GitHub 制品一致；也已在仓库外的隔离环境从 PyPI 安装并运行示例。[发布核验](../compatibility/releases/0.1.1a2-pypi.json)

**0.1.1a2 仍是预发布，完整 Click 兼容目标尚未达成。** CPython 子解释器兼容继续记为 `UNFINISHED`。小规模重复解析、单选项完整调用和嵌套命令在两台主机上仍慢于 Click，因此没有“所有 Click 应用都大幅提速”的结论。[兼容性清单](../COMPATIBILITY.md)、[未完成项](../compatibility/known-gaps.json)

## 固定目标与依赖

本轮继续使用同一个 Click 行为目标；源码、API、文档和官方测试都来自固定版本。

| 项目 | 固定值与边界 |
| --- | --- |
| 项目版本 | Python `0.1.1a2`；Cargo `0.1.1-alpha.2` |
| Click 目标 | **8.5.1**；源码 `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1` |
| zclap | registry 精确版本 **0.1.4**；正式依赖不使用 Git 分支或开发机路径 |
| 原生绑定 | **PyO3 0.30.1**，包含其必要的传递与构建依赖 |
| Rust / MSRV | **1.99.1**，Edition **2024** |
| Python | 最低 **3.10**；普通 CPython wheel 使用稳定 ABI，PyPy 和 free-threaded CPython 使用各自构建 |
| Python 运行时第三方依赖 | 空；Click、pytest、Maturin 等属于开发、构建或对照环境 |

版本与来源见 [target.json](../compatibility/target.json)、[zclap.json](../compatibility/zclap.json)、[Cargo.toml](../Cargo.toml) 和 [pyproject.toml](../pyproject.toml)。Rust 语义核心使用 `no_std + alloc`，直接第三方依赖只有 zclap；Python 扩展使用 `std` 和 PyO3，仍会分配 Python 与 Rust 对象。

应用迁移方式保持为 `import zclick as click`，子模块导入对应改为 `from zclick.xxx import ...`。发行包不安装顶层 `click`，不修改原版 Click，也不通过全局 `sys.modules` 重定向其他库。已有示例、类型声明和 `py.typed` 的入口见 [README](../README.md)。

## 优化实际减少了什么工作

### 复用结构，保留每次调用的状态

解析 schema 是选项名字和参数消费规则的结构表。一个命令或解析器最多保留最近一份由 Rust 拥有的不可变 schema；每次调用先读取当前定义并核验，匹配时复用，变化时建立新表。这样，未变化的名字和查找表不必反复构造。核验本身仍在计时范围内。[实现](../crates/zclick-python/src/plan.rs)、[结构变更测试](../tests/test_native_plan.py)

默认值函数的结果、环境变量、提示输入、Context 和回调结果不进入这个缓存。修改参数、别名、参数个数、callback 或类型方法后，后续调用仍读取当前 Python 对象。重入拥有独立解析状态，已经执行过的命令也有 pickle 和 deepcopy 回归。[动态语义](../tests/test_dynamic_semantics.py)、[复用命令测试](../tests/test_cached_command_semantics.py)

### 减少输入复制和解释层的重复操作

普通参数字符串在一次原生调用期间借用解释器提供的 UTF-8 缓冲区，并保留原 Python 对象的所有权。参数来源通过索引记录，避免把相同内容或空缓冲区误当成同一个对象。含 surrogate 的字符串走可逆表示；这条路径和结果对象的创建仍可能分配内存。[边界测试](../tests/test_native_kernel.py)

Python 适配层减少了临时类型映射表、重复导入和部分格式化辅助对象。内置类型选择每次读取当前公开类型对象；字符串子类、自定义转换器和被替换的方法仍可被观察到。单行帮助的常见情况避免提前加载 `inspect`，特殊空白继续使用当前解释器的标准库语义，包括 Python 3.12 与 3.13 的差异。[表面接口回归](../tests/test_surface_fast_paths.py)

### 大参数表预建位置索引，再稳定排序

普通 CPython 对象、实际的 list 容器和至少 512 项声明参数满足守卫条件时，原生排序先建立首次出现位置的查找表，再做稳定排序。它减少了重复 `list.index` 线性查找，排序本身最坏仍需 O(n log n) 时间。小列表、自定义相等比较、属性或真值协议，以及 PyPy，继续执行 Python 的实际 `sorted` 和 `index` 规则。[排序实现](../crates/zclick-python/src/ordering.rs)、[排序回归](../tests/test_native_ordering.py)

以上工作仍使用 zclap 做实际选项识别和最终验证。类型转换、参数回调等 Python 扩展点保留当前方法调用。完整执行时间还包括启动、导入、命令构造、上下文、转换、用户回调和输出，因此重复解析的加速比不能直接当作整个应用的加速比。[架构说明](architecture.md)

## 双主机三方性能一览

两次测量都将固定 Click、已发布 a1 wheel 和冻结的 a2 wheel 放在同一个 Python 解释器下比较；没有用历史报告的 a1 数字替代当轮对照。每轮的工作树开始和结束时均干净，各主机的全部测量 worker 都绑定 CPU 0。两次运行的处理器、解释器和构建环境不同，因此分别报告，不合并为一个“平均提速”。

| 记录 | 本地测量 | 发布 CI 测量 |
| --- | --- | --- |
| 源码 | [`c949d301`](https://github.com/LIghtJUNction/zclick/commit/c949d301f815c882acce9a96fe2a0c3b8da9bded) | [`7e3d5978`](https://github.com/LIghtJUNction/zclick/commit/7e3d597873b737bbfc8c2df090773aad56d9bd73) |
| Python / CPU | CPython 3.12.14 / AMD EPYC 9V74 | CPython 3.14.10 / AMD EPYC 7763 |
| a2 wheel 目标 | 本机构建 `manylinux_2_34` | 发行构建 `manylinux_2_17` |
| 完整样本 | [本地 JSON](../benchmarks/results/cpython312-linux-c949d30.json) | [CI JSON](../benchmarks/results/cpython314-linux-7e3d597.json) |

下表保留全部 18 项重复调用场景。比值为各自主机上**参考中位耗时 / a2 中位耗时**，大于 1 表示 a2 耗时更低。Click 对照与旧版 a1 对照分列，不能将项目已有的性能优势全部归为本轮新增收益。

| 场景 | 本地 Click/a2 | CI Click/a2 | 本地 a1/a2 | CI a1/a2 |
| --- | ---: | ---: | ---: | ---: |
| 命令构造，1 个选项 | 1.020× | 1.036× | 1.161× | 1.145× |
| 重复解析，1 个选项 | 0.541× | 0.617× | 1.231× | 1.271× |
| 完整调用，1 个选项 | 0.973× | 0.979× | 1.012× | 1.053× |
| 帮助文本，1 个选项 | 2.344× | 2.790× | 1.118× | 1.216× |
| 命令构造，10 个选项 | 1.026× | 1.050× | 1.141× | 1.159× |
| 重复解析，10 个选项 | 0.757× | 0.650× | 1.753× | 1.675× |
| 完整调用，10 个选项 | 1.160× | 1.132× | 1.198× | 1.114× |
| 帮助文本，10 个选项 | 1.885× | 2.083× | 1.284× | 1.242× |
| 命令构造，100 个选项 | 1.042× | 1.045× | 1.138× | 1.151× |
| 重复解析，100 个选项 | 0.868× | 0.735× | 2.370× | 2.161× |
| 完整调用，100 个选项 | 1.195× | 1.289× | 1.175× | 1.114× |
| 帮助文本，100 个选项 | 1.346× | 1.468× | 1.229× | 1.290× |
| 命令构造，1,000 个选项 | 1.137× | 1.063× | 1.086× | 1.152× |
| 重复解析，1,000 个选项 | 1.236× | 0.975× | 2.535× | 2.354× |
| 完整调用，1,000 个选项 | 1.771× | 2.017× | 1.042× | 1.050× |
| 帮助文本，1,000 个选项 | 1.214× | 1.320× | 1.283× | 1.305× |
| 嵌套命令 | 0.886× | 0.909× | 1.096× | 1.027× |
| Unicode/ANSI 换行 | 7.404× | 9.314× | 1.113× | 1.045× |

1,000 个选项的纯解析在 CI 中为 a2 **857.956 µs**、Click **836.866 µs**、a1 **2,019.259 µs**。完整调用则为 a2 **7,023.316 µs**、Click **14,169.504 µs**、a1 **7,377.726 µs**。这说明减少解析成本确实改善了旧版，但一次完整命令还包含上下文、转换和回调，改善比例不同。

完整调用复用已经定义的 Command。全新进程测量另外包含启动、导入、构造、输出捕获与退出；导入区间仅计算导入本身。部分边界比值如下，全部 8 项冷启动的绝对耗时保留在[英文完整报告](performance-0.1.1a2.md)。

| 场景 | 本地 Click/a2 | CI Click/a2 | 本地 a1/a2 | CI a1/a2 |
| --- | ---: | ---: | ---: | ---: |
| 全新进程，1,000 选项命令 | 1.336× | 1.291× | 1.317× | 1.137× |
| 全新进程，1,000 选项帮助 | 1.264× | 1.150× | 1.238× | 1.151× |
| 导入区间 | 1.384× | 1.287× | 1.393× | 1.253× |

CI 的 1,000 选项命令与帮助进程分别为 **57.698 ms / 65.037 ms**，导入区间为 **21.891 ms**。两台主机各自的 8 项冷启动中位数均低于两个对照，但保留的离群值不支持“每次启动都会更快”。完整报告也保留 CPU 时间、Python current/peak 分配和 RSS。

CI 基准 wheel 与同轮发布的 Linux GNU wheel **拥有相同的运行时代码与原生二进制内容**：18 个 Python/native 文件逐个哈希相同。两个 wheel 压缩文件的 SHA-256 不同，不能称为整个制品逐字节相同。[逐文件对比记录](../compatibility/releases/0.1.1a2-benchmark-payload.json)保留两份 wheel 哈希、全部运行时文件哈希和验证范围。这个检查关联了测量代码与发行构建，不代替发布成功或其他架构性能的证据。

### 测量方法与能够支持的结论

每次三方比较使用同一 Python 解释器，wheel 分别安装到独立环境。每轮使用新的隔离进程，每台主机各 12 轮；每六轮包含三方的全部六种先后顺序一次，冷启动各场景另有独立顺序。输出、解析结果和对象身份先检查再计时，原始报告保留 wheel、源码、Cargo.lock、主机和每轮观测。正常 GC 保持启用。[测量协议](../benchmarks/README.md)

大规模重复解析相对旧版的改进在两台主机的每轮配对中都出现，但完整调用只有小幅新增改善。本地 1,000 选项完整调用的 a1/a2 配对比值为 0.861–1.424，CI 为 1.034–1.075。CI 的 1,000 选项纯解析相对 Click 的配对比值为 0.938–1.065，跨越 1。冷启动也有离群值：本地 a2 的 100 选项帮助中位数为 33.707 ms，最大值为 149.031 ms，变异系数为 78.43%。CI 波动较小不能成为删除本地离群值的理由，全部样本保留。

本地旧版是发布的 `manylinux_2_17` wheel，候选是本机构建的 `manylinux_2_34` wheel。解释器、测量主机和顺序得到控制，构建环境仍不同，**不能把全部变化归因于源码**。CPU 频率没有锁定，也没有可用的频率读数；共享主机调度和文件缓存仍会影响结果。CI 使用与正式分发对齐的 manylinux 构建，运行时内容也已逐文件核对；它独立补充了证据，没有替换本地结果。跨主机的变化同时涉及 Python 版本与处理器，仍不能单独归因。

内存指标也没有“全面降低”的结论。整个 worker 的 RSS 中位数，本地 a2 / Click / a1 为 **25.492 / 24.059 / 25.107 MiB**，CI 为 **33.324 / 32.039 / 33.287 MiB**。它包含导入、哈希校验、tracemalloc 和整组工作负载。1,000 选项解析的 Python 分配峰值，本地从 a1 的 163,850 字节降到 a2 的 54,281 字节，CI 从 175,010 字节降到 54,355 字节。Python 分配指标不覆盖所有 Rust 分配，不能替代整个进程的内存测量。

## 验证方法与兼容边界

发布门禁仍要求固定的 **33,459 个官方用例 ID**，其中 **31,000 个为压力用例**，以及 **196 项公开 API**及成员契约、12 个官方 typing 文件和四种真实 Shell 执行。用例、断言和原版 skip/xfail 条件保持不变，逐例报告要与不可变源码提交绑定。分片只改变执行批次；平台跳过项不能计作实际通过。[固定库存](../compatibility/test-manifest.json)、[完整门禁说明](development.md)

本轮新增回归针对结构复用、方法和实例修改、重入、复制、字符串身份、Unicode 空白，以及排序中的相等比较和首次位置规则。大命令的部分动态边界在独立解释器中验证，避免前一个测试改变优化适用条件、掩盖后一个测试。本次发布的 12 个普通兼容测试任务与 28 个压力测试任务均已成功完成，原版 skip/xfail 仍单独记录；逐环境计数见[发布验证记录](../compatibility/releases/0.1.1a2.json)。

### 本轮实际平台结果

以下计数来自本次公开的 `compatibility-evidence.zip`，对应同一个发布源码提交。每个环境都收集了 **321 个项目测试**与 **2,459 个官方普通用例**；表内是每个所列运行时各自的结果。官方列中，原版 Click 与 zclick 的计数一致，缺失用例、额外用例和意外新增 skip 均为 0。所有任务没有失败或错误。[逐环境证据](../compatibility/releases/0.1.1a2.json)

| 实际测试环境 | 项目测试：通过 / 跳过 | 官方普通：通过 / 跳过 / 预期失败 | 官方压力：通过 / 跳过 |
| --- | ---: | ---: | ---: |
| Linux CPython 3.10–3.13、3.15 | 314 / 7 | 2,434 / 24 / 1 | 未在这些配置运行压力测试 |
| Linux CPython 3.14 | 314 / 7 | 2,434 / 24 / 1 | 31,000 / 0 |
| Linux free-threaded CPython 3.14、3.15 | 314 / 7 | 2,434 / 24 / 1 | 31,000 / 0 |
| Linux PyPy 3.11、3.12 | 310 / 11 | 2,434 / 24 / 1 | 31,000 / 0 |
| macOS CPython 3.14 | 314 / 7 | 2,433 / 25 / 1 | 31,000 / 0 |
| Windows CPython 3.14 | 316 / 5 | 2,357 / 101 / 1 | 30,000 / 1,000 |

Windows 的 1,000 个压力跳过来自原版分页器用例，原版与 zclick 条件一致，**不计作实际通过**。正常测试中的 skip 和预期失败也单独保留。完整库存门禁核验的是固定的 33,459 个用例 ID 与结果条件，不能把库存大小直接称为各平台全部实际通过数。

12 个测试环境的 **196 项公开 API**及成员契约均完成核对，mypy 在每个环境检查的 **12 个官方 typing 文件**均通过。Rust 的 **1 个单元测试和 22 个集成测试**全部通过，没有忽略项，`clippy -D warnings` 通过。真实 Shell 的 **9 个用例**全部通过，实际版本为 Bash 5.3.9、Zsh 5.9、Fish 4.9.3、PowerShell 7.7.0。[检查范围和版本记录](../compatibility/releases/0.1.1a2.json)

**12 个 wheel 和一个源码包的实际安装执行检查均成功。** 源码包先重新构建，再安装运行。每个制品的实际 runner、解释器和系统记录在证据中；wheel 的最低系统兼容标签不等于在那个最低系统版本上运行了全量测试。

仍需明确保留以下边界：

- **子解释器尚不兼容。** 当前绑定在初始化早期拒绝子解释器导入，避免跨解释器错误共享 Python 对象；安全拒绝不等于实现了 Click 的行为。
- **第三方扩展的内部导入仍需迁移。** 应用里的 `import zclick as click` 不会改写扩展文件中的 `import click`。[扩展实测](extensions.md)单独记录了三个原版扩展的类身份和上下文边界。
- **CliRunner 不提供同进程线程间的隔离保证。** 它会替换流、环境变量和工作目录；并行 runner 测试使用独立进程。free-threaded wheel 不改变这一工具边界。
- **安装检查与完整平台测试范围不同。** wheel 成功构建和安装执行，不能自动证明该架构运行了全部官方用例。Shell source 执行、终端编辑器注册记录和真实终端设备也需区分，具体范围见[补全文档](shell-completion.md)。

## 复现入口

以下为普通 CPython/Linux 开发环境示例。Windows 的环境激活方式不同；PyPy 和 free-threaded CPython 构建需要增加 `--no-default-features`。完整跨平台步骤见[开发指南](development.md)。

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
maturin develop --release --locked
python -m pytest tests
python scripts/run_compatibility.py --output reports/normal -- -m 'not stress'
python scripts/run_stress.py --output reports/stress --workers 4 --batch-size 500
python scripts/api_inventory.py --source .cache/click-source --output reports/api-reference.json
python scripts/api_inventory.py --compare reports/api-reference.json --output reports/api.json
python -m mypy .cache/click-migrated/tests/typing --no-incremental
```

正式基准需要冻结源码并留出没有本地构建或测试竞争的测量时段：

```sh
maturin build --release --locked --out dist/benchmark-candidate
python benchmarks/compare.py \
  --candidate-wheel dist/benchmark-candidate/*.whl \
  --iterations 1000 --repeats 12 --seed 20261111 --affinity auto \
  --output reports/benchmarks-0.1.1a2.json
```

目录中有多个 wheel 时应传入目标文件的确切路径；不支持 Linux affinity 的平台去掉该选项。driver 会重新使用锁定的已发布基线，校验候选版本及 Python 源文件。短诊断模式用于检查测量工具，不能作为发布性能结论。

## 发布结果与公开安装核验

本轮完整发布工作流 **61 个任务全部成功**，`v0.1.1a2` 标签解析到源码 `7e3d597873b737bbfc8c2df090773aad56d9bd73`。以下时间均为 2026-11-11 UTC；上传任务成功与公开文件核对分别记录。

| 项目 | 实际结果 | 证据 |
| --- | --- | --- |
| GitHub Release | 16:02:29 发布，Release ID `441909181`；任务于 16:02:31 成功 | [发布页](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a2)、[发布任务](https://github.com/LIghtJUNction/zclick/actions/runs/43052475382/job/130639368136) |
| PyPI | 发布任务于 16:03:19 成功；公开版本有 13 个分发文件 | [PyPI](https://pypi.org/project/zclick/0.1.1a2/)、[发布任务](https://github.com/LIghtJUNction/zclick/actions/runs/43052475382/job/130639366379) |
| 文件一致性 | 12 个 wheel 加一个 sdist，全部公开 PyPI 哈希与下载的 GitHub 文件哈希一致 | [分发核验记录](../compatibility/releases/0.1.1a2-pypi.json) |
| 实际安装 | 新建环境从公开 PyPI 以 `--no-deps` 安装，在仓库外用 `-I` 运行；没有安装原版 Click | 同一核验记录中的安装检查 |
| 示例行为 | 提示输入名字 Ada，按 `--count 2` 输出两次问候，退出码 0；原生模块哈希与 CI 基准一致 | 同一核验记录中的输出与原生模块哈希 |

可信发布者已实际发布成功。PyPI 公布的 provenance 记录将发布者标识为 GitHub 仓库 `LIghtJUNction/zclick`、工作流 `release.yml`、环境 `pypi`；本次核验范围为该公开发布身份，以及分发文件的 SHA-256 一致性。[核验范围](../compatibility/releases/0.1.1a2-pypi.json)

可直接安装固定预发布版本：

```sh
python -m pip install zclick==0.1.1a2
```

普通 CPython wheel 覆盖 Linux glibc、Linux musl、macOS、Windows 的 x86-64 与 ARM64。另有 Linux x86-64 的 PyPy 3.11、3.12 和 free-threaded CPython 3.14、3.15 专用 wheel；源码包也已发布。安装制品覆盖范围与运行完整兼容测试的平台范围分别记录，不能混为一项保证。

双主机性能和运行时逐文件对比保留在上文。当前版本仍公开标记为预发布，子解释器兼容尚未完成；性能较慢的场景、平台原有跳过条件和第三方扩展迁移边界也继续保留。旧版 [0.1.1a1 交付记录](DELIVERY.zh-CN.md)与[历史性能记录](performance.md)保持原样。
