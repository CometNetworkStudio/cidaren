# OmniTask Script · 词达人（cidaren）

词达人（app.vocabgo.com）自动答题脚本，适配 [OmniTask](https://github.com/CometNetworkStudio/OmniTask) 平台，也可独立运行。

## 简介

- 自动完成词达人「班级学习任务 / 班级测试任务」。
- 答题策略：题库 → LLM → 跳过；以服务端 `VerifyAnswer.answer_corrects` 为准回写题库。
- 支持人类化思考延迟与请求间隔（可配）。
- 既可被 OmniTask 以子进程（stdio JSON）调用，也可本地 CLI 单跑。

## 免责声明

本项目**仅供个人学习与技术研究使用**。请遵守词达人平台服务条款与所在学校规定，因使用本项目产生的一切后果由使用者自行承担。请勿用于商业牟利或倒卖。

## 净室重写声明

本脚本为**独立实现**，仅依据平台公开网络接口行为编写，**未复制任何 GPL/无协议项目的源码**。参考项目 `ularch/Easy_Cidaren`（GPL-3.0，且声明禁止商用）仅用于理解协议；本项目代码为其净室重写版本，采用 MIT 协议开源。

## 用法

### 方式一：独立 CLI

```bash
pip install -r requirements.txt
python main.py --cli \
  --action study \
  --credential token=<你的词达人 Token> \
  --param "task_name=List  04" \
  --param limit=1
```

- `--action`：`study`（班级学习任务）/ `class`（班级任务）。
- `--param k=v`：可重复，见 `script.json` 的 `params`。
- `--credential k=v`：可重复，仅 `token`。

### 方式二：OmniTask 平台调用

OmniTask 的 Go Host 会以子进程启动 `main.py`，通过 stdin 下发一条 `execute` 请求，脚本以 stdout 逐行输出事件。协议见：
<https://github.com/CometNetworkStudio/OmniTask/blob/main/docs/script-protocol.md>

## 参数（`params`）

| key | 默认 | 说明 |
|---|---|---|
| `task_name` | 空 | 仅执行名称包含该子串的任务 |
| `task_type` | 1 | 1 班级学习 / 2 班级测试 |
| `progress_lt` | 100 | 仅处理进度低于该值 |
| `limit` | 0 | 最多任务数，0=不限 |
| `max_steps` | 1000 | 单任务最多题数 |
| `think_min` / `think_max` | 2 / 4 | 每题作答后的思考停顿（秒） |
| `spend_min` / `spend_max` | 5 / 15 | 服务端 `time_spent`，单位 500=1s |

## 凭据

| key | 说明 |
|---|---|
| `token` | 词达人 Token（需自行抓包获取） |

## 目录

```
.
├── cidaren/        # 协议实现（sign/jv/client/answer/runner）
├── core/           # 内置 OmniTask Script SDK（http/ratelimit/bank/llm）
├── gen/            # gRPC 生成物（题库客户端）
├── main.py         # 入口（Host 模式 / CLI）
├── cli.py          # 本地命令行
└── script.json     # manifest
```

## License

MIT © CometNetworkStudio
