# 第三方 Click 扩展的迁移边界

仅修改应用自己的导入，不能保证第三方扩展同时迁移到 zclick。本次检查了三个真实发布包，它们都在自身源码中导入原版 `click`。原版 Click 与 zclick 同时安装时，这些导入仍然指向原版 Click；应用中的 `import zclick as click` 只改变应用当前模块里的变量绑定。

## 已验证的具体行为

下面的实验固定原版 Click 为 **8.5.1**，扩展保持发布包原样。每个扩展先运行原版 Click 对照，再运行只调整应用导入的混合场景。测试文件为 [`integration_tests/test_extensions.py`](../integration_tests/test_extensions.py)，依赖固定在 [`requirements-extensions.txt`](../integration_tests/requirements-extensions.txt)。

| 扩展及版本 | 原版 Click 对照 | zclick 混合场景的观察 | 迁移结论 |
| --- | --- | --- | --- |
| `click-didyoumean==0.3.1` | 拼错子命令时返回退出码 2，并显示候选命令。 | `@zclick.group(cls=DYMGroup)` 仍然构造原版 `click.Group` 子类；简单命令可以执行。加入 `@zclick.pass_context` 后，调用因没有活动的 zclick 上下文而失败。 | 简单示例能运行，不足以证明已使用 Rust 解析。该扩展的类继承和上下文调用需要一致迁移。 |
| `click-plugins==1.1.1.2` | 能把入口点加载的命令注册到原版 `click.Group` 并执行。 | `with_plugins([])(zclick.Group(...))` 立即抛出 `TypeError`，因为扩展检查原版 `click.Group` 的类型身份。 | 未修改的发布包不接受 zclick 的 Group。 |
| `click-repl==0.4.1` | 注册 REPL 后，从输入流执行 `hello` 和 `:exit` 成功。 | 注册到 zclick Group 后，扩展包装的原版 `click.pass_context` 从原版 Click 的上下文栈取值，调用 REPL 时抛出 `RuntimeError`。 | 注册成功不等于可执行；上下文装饰器、命令类型判断和补全类型判断需要一起验证。 |

这些是**兼容性诊断测试**。其中一些测试明确断言混合场景会失败，测试通过表示观察到的边界可以复现，不能把其通过数计入“第三方扩展已经兼容”的数量。原版 `click-repl` 对照还会触发其使用 `MultiCommand` 产生的弃用警告；测试明确捕获该警告，未修改扩展源码或 Click 的警告行为。

## 为什么导入别名不能解决这些问题

Python 的导入别名只作用于写下该导入语句的模块。应用把名称 `click` 绑定到 zclick 后，扩展文件中的 `import click` 会继续独立查找名为 `click` 的包。两者拥有不同的类对象，因此 `isinstance(zclick.Group(...), click.Group)` 为假。

上下文同样具有各自的状态。zclick 调用命令时把自己的 Context 放入自己的上下文栈；原版 Click 的 `get_current_context()` 不会从这个栈取值。诊断测试双向检查两个栈相互独立，这也确保 zclick 没有通过修改全局 `sys.modules` 或替换原版 Click 偷偷改变其他库。

## 复现

在仓库根目录创建专用开发环境。下面的安装会构建当前仓库，要求已安装项目声明的 Rust 工具链；第三方扩展和原版 Click 只安装到这个隔离环境。

```sh
python -m venv .venv-extensions
.venv-extensions/bin/python -m pip install -r integration_tests/requirements-extensions.txt
.venv-extensions/bin/python -m pip install --no-deps .
.venv-extensions/bin/python -m pytest integration_tests/test_extensions.py -q
```

Windows 将解释器路径替换为 `.venv-extensions\Scripts\python.exe`。常规 `pytest tests` 不包含这个独立的扩展实验；选中 `integration_tests/test_extensions.py` 时缺少任何固定依赖都会直接报错，不会用跳过测试代替结果。

## 实际迁移方式

先把应用的 `import click` 改为 `import zclick as click`，把 `from click.xxx` 改为相应的 `from zclick.xxx`。随后检查每个扩展内部的导入、继承、`isinstance` 判断、异常捕获和上下文装饰器。只有经过实际执行验证的扩展版本，才适合在迁移清单中标记为支持。

对于上表三个未修改的版本，本项目不宣称自动兼容。可以向扩展维护者提交显式支持 zclick 的改动，或在许可证允许且能够维护的前提下迁移应用自己的扩展副本。更改扩展导入之后仍需测试成功路径、失败路径、上下文传播和补全；本轮未把未经执行的修改方案标记为已支持。

## 来源与证据

- [click-didyoumean 0.3.1 的发布说明](https://pypi.org/project/click-didyoumean/0.3.1/) 和 [项目源码](https://github.com/click-contrib/click-didyoumean)描述其自定义 Group 用法；本仓库测试进一步检查实际构造出来的类和上下文行为。
- [click-plugins 1.1.1.2 的发布说明](https://pypi.org/project/click-plugins/1.1.1.2/) 和 [项目源码](https://github.com/click-contrib/click-plugins)说明入口点注册方式；测试覆盖真实 `with_plugins` 装饰器的类型检查。
- [click-repl 0.4.1 的发布说明](https://pypi.org/project/click-repl/0.4.1/) 和 [项目源码](https://github.com/click-contrib/click-repl)说明 `register_repl` 和上下文复用；测试运行真实 REPL 注册函数及原版输入流对照。

证据范围限于固定版本和列出的路径。它证明了三个具体的导入边界，未穷举所有第三方扩展、交互终端、插件加载器或提示工具包配置，也没有提出扩展性能提升的结论。

## 自审

- **贡献**：提供三个真实扩展的可复现迁移边界，未把示例运行成功等同于 Rust 后端已经生效。
- **清晰度**：固定版本、测试入口和隔离环境命令齐全，解释了类型身份与上下文栈两个直接原因。
- **实验强度**：同一扩展同时运行原版 Click 对照与混合导入场景；结论由类型、退出码、输出和异常支撑。
- **评估完整性**：明确列出未测试的扩展和交互场景，没有从三个样本推断整个生态。
- **方法正确性**：保留扩展源码、原版 Click 安装和各自的模块身份；不使用运行时替换、全局导入劫持或断言修改。
