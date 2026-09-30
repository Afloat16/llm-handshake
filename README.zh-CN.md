# LLM Handshake

**在接入应用之前，发现大模型接口的不兼容行为。**

[English](README.md) · [简体中文](README.zh-CN.md)  
Python 3.10+ · MIT · 零运行时依赖

LLM Handshake 是一个小型命令行诊断工具，用来检查 OpenAI-compatible 大模型接口。先查看完整请求计划，再执行需要的检查；更换模型或升级网关后，还能比较两份报告，发现回归。

一次普通聊天成功，并不代表流式用量、工具参数拼接、结构化输出都能正常工作。本工具把这些能力分开检查，不需要仪表盘、数据库、厂商 SDK，也不读取你的业务文件。

## 不需要密钥，直接体验

在源码目录中运行：

```sh
python scripts/build_zipapp.py
python dist/llm-handshake.pyz demo
```

演示会临时启动本机回环服务器，通过真实 HTTP 客户端执行检查，结束后关闭服务器。不会连接任何模型服务商。

```text
7 pass / 0 warn / 0 fail / 0 skip
Requests: 7 (6 inference)
```

这里的 6 次推理请求是**发往本地模拟服务器的请求**，并没有执行真实模型。还可以体验故障诊断：

```sh
python dist/llm-handshake.pyz demo --broken
```

```text
4 pass / 1 warn / 2 fail / 0 skip
WARN  stream-usage   usage_missing
FAIL  tool-stream    tool_arguments
FAIL  json           json_schema_sample
```

故障演示按设计返回退出码 `1`。完整的[合成示例报告](examples/README.md)保留了诊断信息和后续处理建议。

### 安装为命令行工具

在虚拟环境中，从当前源码目录安装：

```sh
python -m pip install .
llm-handshake demo
```

安装时可能需要下载构建后端，但运行工具只使用 Python 标准库。上面的 `.pyz` 构建和运行都不需要第三方包。已有本地 wheel 时，可使用 `python -m pip install --no-index --no-deps WHEEL文件路径` 安装。

以上是源码与本地文件安装方式，不表示已经发布到 PyPI。

## 检查你的接口

设置**准确的 API 基地址**，包含 `/v1` 等实际前缀，并指定接口提供的模型。工具不会猜测模型，不会自动补 `/v1`，也不会悄悄更换参数重试。

```sh
export OPENAI_BASE_URL="https://your-gateway.example/v1"
export OPENAI_MODEL="your-deployed-model"
# 通过环境变量或密钥管理器提供 OPENAI_API_KEY。
# 不要把真实密钥写入命令参数、源码或提交记录。
```

**先查看请求计划，不发送网络请求：**

```sh
llm-handshake plan --probes all --format json
```

**检查模型列表，不请求推理：**

```sh
llm-handshake check
```

**显式允许完整检查，其中包含 6 次可能计费的推理请求：**

```sh
llm-handshake check --probes all --allow-inference
```

无需认证的本地接口示例：

```sh
llm-handshake check \
  --base-url http://127.0.0.1:11434/v1 \
  --model "$OPENAI_MODEL" \
  --no-auth --probes chat,stream --allow-inference
```

本地示例采用 Ollama 文档中的接口地址形态 [R5]，不表示每个已安装模型都支持全部检查。请填写实际模型 ID。PowerShell 使用 `$env:OPENAI_MODEL = "your-deployed-model"` 设置变量，并将命令写成一行，或使用 PowerShell 的续行方式。

## 检查哪些内容？

| 检查项 | 请求 | 观察内容 |
| :--- | :--- | :--- |
| `models` | `GET /models` | 列表结构、非空 ID、重复项、所选模型是否出现 |
| `chat` | 一次普通文本生成 | 响应结构、助手文本、结束原因、返回的 token 用量 |
| `stream` | 一次普通流式生成 | SSE 分帧、响应标识一致性、文本增量、结束原因、`[DONE]` |
| `stream-usage` | 单独一次带 `include_usage` 的流式请求 | 用量数值和末尾独立用量分片，不与普通流式能力混为一谈 |
| `tools` | 一次强制函数选择 | 调用 ID、函数名、结束原因和整数参数 |
| `tool-stream` | 一次流式函数选择 | 函数名与参数片段的拼接，以及完整调用的校验 |
| `json` | 一次严格 schema 请求 | 实际返回样本是否符合仅含一个整数字段的约束 |

每个检查项至多尝试一次请求，返回的工具调用**不会被执行**。`json` 只验证一次样本；模型可能没有遵守 schema 参数，却碰巧按提示词输出正确内容，因此通过不等于证明服务端强制执行 schema。具体规则与来源见 [PROTOCOL.md](docs/PROTOCOL.md)。

## 常见用法

### 只要求应用真正依赖的能力

```sh
llm-handshake check \
  --probes chat,stream,stream-usage \
  --require chat,stream \
  --allow-inference
```

这个命令允许可选的用量检查出现警告，但要求 `chat` 和 `stream` 都通过。`--require` 中的项目必须同时被 `--probes` 选中，否则在联网前报错。需要所有已选检查都通过时，使用 `--strict`。

### 保存报告

```sh
llm-handshake check --probes all --allow-inference \
  --format json --output before.json

llm-handshake check --probes all --allow-inference \
  --format markdown --output diagnostic.md
```

JSON 用于机器处理和版本对比，文本及 Markdown 适合阅读。`--output` 采用原子写入，在 POSIX 系统中创建仅当前用户可读写的文件；父目录必须事先存在。已有同名文件会被替换。使用 shell 重定向时，权限由 shell 决定。

### 升级后检查回归

使用相同参数重新检测，保存为 `after.json`，然后运行：

```sh
llm-handshake compare before.json after.json
```

原先通过的项目降级、变为跳过或从报告中消失，都能被识别为回归。检查套件版本或 token 参数变化时，报告不能直接比较。更换接口地址或模型，需要显式传入 `--allow-target-change`。耗时和用量波动不会触发这个回归门禁。详见[报告语义](docs/REPORTS.md)。

### 在 Python 中调用

```python
import os
from llm_handshake import Config, run_checks
from llm_handshake.reporting import gate

report = run_checks(Config(
    base_url=os.environ["OPENAI_BASE_URL"],
    model=os.environ["OPENAI_MODEL"],
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    probes=("chat", "stream"),
    allow_inference=True,
))
raise SystemExit(gate(report, required=("chat", "stream")))
```

## 请求透明，限制明确

默认 `check` 仅选择 `models`。执行推理既要选择推理检查项，也要加 `--allow-inference`。完整计划有 7 个请求，其中 6 个为推理请求，每次默认请求最多输出 128 tokens，合计 **768 个请求输出 tokens**。这**不是金额预算**：输入和推理过程可能计费，服务商对限制的解释可能不同，也可能忽略限制；失败请求也可能消耗资源。

`--max-requests` 在计划超出限制时直接拒绝执行，不会偷偷删减检查项。客户端不自动重试、不切换参数、不跟随重定向，也不读取代理环境变量。认证失败、限流、服务器错误或连接、TLS、超时错误发生后，会跳过剩余检查，避免重复访问故障端点。

| 参数 | 默认值 | 作用 |
| :--- | :--- | :--- |
| `--probes` | `models` | 逗号分隔的检查项，或 `all` |
| `--timeout` | `20` 秒 | 单次请求的 socket/截止时间限制；系统同步 DNS 可能超出这个时间 |
| `--max-output-tokens` | `128` | 请求输出上限，范围 1–4096 |
| `--token-limit-field` | `max_tokens` | 模型要求时，显式选择 `max_completion_tokens` [R6] |
| `--max-requests` | `7` | 所选请求计划的最大条数 |
| `--max-response-bytes` | `1048576` | 单次成功响应体最多读取的字节数 |
| `--api-key-env` | `OPENAI_API_KEY` | 读取 bearer token 的环境变量名 |
| `--no-auth` | 关闭 | 忽略密钥变量，连接免认证接口 |
| `--ca-file` | 仅系统信任库 | 添加 PEM CA，不关闭证书和主机名校验 |
| `--allow-http` | 关闭 | 显式允许非回环明文 HTTP；不建议携带密钥使用 |

`OPENAI_BASE_URL`、`OPENAI_MODEL` 是可选环境变量默认值，命令行参数优先。工具不会自动加载 `.env`。全部选项见 `llm-handshake check --help`。

## 隐私与安全

工具只把内置的合成提示词直接发往指定接口。报告不保留密钥、响应正文、原始 SSE 事件、服务商错误文本、模型列表中的 ID 或完整 URL 路径。没有遥测，也不会上传报告。

**JSON 报告仍包含接口来源地址和所选模型名称。** 报告中的 SHA-256 是规范化基地址与模型的无密钥关联指纹，不是匿名化措施。分享前应检查内容。工具无法控制服务商日志、shell 历史、进程检查或不可信的本地环境。详见[安全说明](SECURITY.md)。

## 退出码

| 退出码 | 含义 |
| :--- | :--- |
| `0` | 满足所选通过条件，或比较没有发现状态回归 |
| `1` | 有检查失败，或严格/必需检查未通过 |
| `2` | 配置、本地文件或报告比较输入错误 |
| `3` | 比较发现至少一项回归 |
| `130` | 用户中断；没有自动重试 |

`WARN` 不代表认证通过；缺失用量不会按零处理。请求被拒绝也不会直接解释成“不支持该能力”。截断、拒绝和过滤会被标记为不确定观察结果。

## 范围与限制

0.1 版只覆盖一小部分 **Chat Completions** 接口，不覆盖 Responses、原生 Anthropic/Gemini API、向量、多模态、工具执行及后续对话、代理行为、HTTP/2、Azure 风格查询参数认证或所有厂商扩展参数。当前使用直接 HTTP/1.1，支持 bearer 认证或免认证。

它不是模型能力榜单、负载测试器、计费仪表、安全审计或全面合规认证工具。一次样本通过不能保证后续请求始终成功。`first_delta_ms` 是客户端观察到首个非空文本或工具参数增量的时间，包含连接及网络开销，不是服务商内部推理耗时。仍需在实际客户端中进行集成测试。

本地 HTTP/HTTPS 测试和模拟演示的范围记录在 [TESTING.md](docs/TESTING.md)，不暗示已完成真实服务商认证。

## 为什么还需要这个项目？

LiteLLM 侧重路由和多服务商抽象 [R1]；promptfoo 侧重应用评估和红队测试 [R2]；LLM 提供通用命令行模型接口 [R3]。另外已有 Go 语言的兼容性测试器 [R8, R9]。本项目不声称首创接口测试，而是专注于小型 Python 可执行文件、可预览请求、独立流式用量诊断和保守的报告比较。

[调研与替代方案](docs/RESEARCH.md) · [完整参考来源](docs/REFERENCES.md) · [架构](docs/ARCHITECTURE.md)

实现、合成测试数据、测试和文档均独立编写。参考项目不是运行时依赖，本仓库未包含这些项目的源码，也不代表其维护者认可或背书。

## 开发与维护

```sh
python scripts/run_tests.py
python scripts/build_zipapp.py
python -I dist/llm-handshake.pyz demo
```

可选覆盖率检查：安装开发依赖后执行 `python -m coverage run scripts/run_tests.py`、`python -m coverage report`。GitHub Actions 已配置 Python 3.10–3.14 与 Linux、macOS、Windows；配置存在不等于这些远程任务已经执行。

[贡献指南](CONTRIBUTING.md) · [更新记录](CHANGELOG.md) · [发布说明](docs/PUBLISHING.md)

## 许可证

[MIT](LICENSE)，Copyright 2026 Afloat16。第三方参考关系见 [NOTICE](NOTICE) 与 [REFERENCES.md](docs/REFERENCES.md)。

[R1]: https://github.com/BerriAI/litellm
[R2]: https://github.com/promptfoo/promptfoo
[R3]: https://github.com/simonw/llm
[R5]: https://docs.ollama.com/api/openai-compatibility
[R6]: https://platform.openai.com/docs/api-reference/chat/create
[R8]: https://github.com/beranekio/openai-compatibility-tester
[R9]: https://github.com/avelrl/openai-compatible-tester
