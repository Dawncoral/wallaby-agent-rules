<!-- wallaby-agent-rules 1.0.1 -->
# wallaby-agent-rules（中文版）

[![License: MIT + Commons Clause](https://img.shields.io/badge/License-MIT%20%2B%20Commons%20Clause-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](CHANGELOG.md)

**AI 记得住，你找得到。**

给你的项目配一个长期记忆——也给你自己一张项目地图。两段粘贴即用的提示词、五个纯文本文件、零依赖。适配任何 AI 编码工具。English: [README.md](README.md)。

我们自己在真实业务里天天跑这套系统。截至 2026 年 10 月，它已记录下 40 次记忆失败——每一条都带日期、带出处，并且都变成了你能在这个仓库里看到的一条规则或一道扫描。

## 30 秒看懂

| 之前 | 之后 |
|---|---|
| 聊了五十轮，AI 的记忆开始变质——已定的事情被重新争论、文件名被编造，你不再信它。 | `MEMORY.md`：每个事实一行，带日期带出处。发生冲突时以文件为准——并当场告诉你，绝不静默吞掉。 |
| 「那个文件在哪？」两周之后没人知道。 | `INDEX.md`：一个文件一行，永远最新。是查找，不是搜索。 |
| 项目根目录慢慢堆满草稿和构建残余。 | `python3 scripts/health_check.py` 每周几秒扫出杂乱。 |
| 「现在线上跑的是哪个版本？」答案只存在某个人脑子里。 | `## 代码与版本` 节：当前版本=一条带日期的记忆事实；每次发布、迁移、回滚都连 commit 号一起记。 |

## 开始——选一条路

两条路都是一段提示词，粘给你项目里的 AI 即可。全文在 [PROMPT.zh-CN.md](PROMPT.zh-CN.md)（英文原版：[PROMPT.md](PROMPT.md)）。

**🚀 一键，约 30 秒**——全部默认（个人开发者、代码项目、信任培养模式开），零提问：

```
抓取 https://raw.githubusercontent.com/Dawncoral/wallaby-agent-rules/main/PROMPT.zh-CN.md
并在本项目里按它的「L0 —— 一键安装」节执行。
```

**🎯 定制，约 2 分钟**——AI 会逐个问你 9 个简短问题（工具、是否涉及代码、项目规模、个人/团队、对话量、记录风格、要不要定期整理、你的口头禅、信任培养开关），然后按你的答案构建同一套系统。

不能抓 URL？直接打开 [PROMPT.zh-CN.md](PROMPT.zh-CN.md) 复制对应段落粘贴——纯文本。

## 你会得到什么

| 文件 | 职责 |
|---|---|
| `AGENTS.md`（或按你的工具用 `CLAUDE.md` / `.cursorrules`） | 入口——告诉 AI 每次开工先读记忆 |
| `MEMORY.md` | 长期记忆：永久事实、关键决策、铁规矩 |
| `NOW.md` | 当前状态：正在做的事、最近碰过的 |
| `INDEX.md` | 项目地图：一个文件一行——首版由 AI 当场扫描你的项目生成 |
| `scripts/health_check.py` | 零依赖每周检查，七项扫描：根目录杂物、构建残余、索引双向漂移、过期条目、入口文件体积墙（字节/行数/token 三维，中文敏感）、无日期事实 |
| `scripts/reconcile.py` | 零依赖每周对账，两项扫描：日志声称「已完成」而 NOW.md 里还在进行、以及没有任何证据可查的「已完成」 |
| 信任培养模式（默认开） | 前两周，新的长期记忆条目先**提报**给你批准才转正——你先看着 AI 选择记什么，再放开让它直接写 |
| 代码与版本节（代码项目） | 当前发布版本=带日期的记忆事实，一变就更新；每次发布/迁移/回滚都带 commit 号落日志 |

安装完成的那一刻，你会看着 AI 扫完你的项目并交出第一份 `INDEX.md`——「你找得到」当场兑现。

**v4.1 新增**：代码版本记忆模块（条件挂载——问卷会问你这个项目是否涉及写代码，涉及才装）+ 完整中文版。

**v4 新增**：信任培养模式（前两周记忆写入需批准——默认开、问卷一题、到期自动结束）+ 工具接入矩阵与每工具一张卡（[templates/integrations/](templates/integrations/)）+ 起用 GitHub Releases。

## 你的工具怎么接

无插件、无 MCP server、无需安装——入口文件就是集成。每个工具读自己的入口文件；启动面谈会帮你选对。

| 工具 | 入口文件 | 备注 |
|---|---|---|
| Claude Code | `CLAUDE.md` | 每次会话开始即读；`/memory` 可快速编辑 |
| Codex | `AGENTS.md` | 原生约定 |
| Cursor | `AGENTS.md` | 原生支持；记忆集中在这里，别拆进 `.cursor/rules` |
| GitHub Copilot | `AGENTS.md` | 原生支持；若已有 `.github/copilot-instructions.md` 也会被读取 |
| OpenHands | `AGENTS.md` | 原生——它的系统提示词要求 agent 维护这个文件 |
| Gemini CLI | `GEMINI.md` | 主文件；也可以在 `GEMINI.md` 里写一行指向 `AGENTS.md` |
| 其他工具 | `AGENTS.md` | 跨工具通用约定；查你的工具文档 |

每个工具的坑与 30 秒自检法：[templates/integrations/](templates/integrations/)。

## 工作原理（四句话）

1. 入口文件让 AI 每次开工先读 `MEMORY.md` + `NOW.md`——记忆是习惯，不是功能。
2. `INDEX.md` 把「帮我找 X」从搜索变成查找，新文件在创建那一刻就被登记。
3. 每周健康检查在混乱累积前抓到漂移——杂物、残余、未登记的文档。
4. 每周对账抓另一种漂移：日志声称的与状态文件显示的之间的差距。

一切都是纯 Markdown，你可以读、`git diff`、直接改。没有向量库、没有服务、没有锁定。

## 已在用？升级

把 [PROMPT.zh-CN.md](PROMPT.zh-CN.md) 里的 **L2 —— 升级检查** 提示词粘给你的 AI。它会识别你的版本（靠首行标记注释或文件指纹），给出增量升级清单——你逐项批准。**你的内容永远不会被覆盖。** 每个版本都发 GitHub Release（含迁移说明），watch 这个仓库即可收到通知。版本历史与迁移步骤：[CHANGELOG.md](CHANGELOG.md)；从早期版本迁移的一页卡：[upgrade/pre-1.0.md](upgrade/pre-1.0.md)。

## 路线图

至今已交付：收工仪式、深度健康检查、对账审计、信任培养模式、工具接入、代码版本模块、中文版。下一个开源大件是多 agent/团队记忆纪律。更深的治理能力（架构评审、托管值守）规划为托管付费形态而非开源件——watch 这个仓库。自 1.0.0 起用语义化版本号；早期迭代（v1–v4.1）已并入 1.0.0——见 [CHANGELOG.md](CHANGELOG.md)。

## 这个仓库里还有

- [`templates/`](templates/)——NOW / INDEX / LOG 模板 + 健康检查与对账脚本，可直接复制。
- [`templates/integrations/`](templates/integrations/)——每工具一张卡：入口文件、坑、30 秒自检。
- [`upgrade/`](upgrade/)——版本间的一页升级卡。
- [`COMMERCIAL.md`](COMMERCIAL.md)——商用授权：什么免费、什么要授权、怎么联系。
- [`AGENTS.md`](AGENTS.md) / [`MEMORY.md`](MEMORY.md)——v1 起始模板（token 预算纪律、三层记忆、相关方名册），仍有效，且本仓库自己也在用。
- [`examples/`](examples/)——填好的 MEMORY / NOW / INDEX 示例：「好」在两周后的样子，不只是第一天。

## 谁在做

Wallaby Token（WALLABY DATA PTY LTD，ABN 90 701 729 964）提供开源大模型推理云服务。这套记忆系统每天跑在我们自己的项目上——不是我们卖的说辞，是我们依赖的基础设施。完整介绍：[wallabytoken.com](https://www.wallabytoken.com)。

## 许可证

MIT + [Commons Clause](LICENSE)——个人项目、研究、公司内部自用免费。把它卖出去（打包、托管、或基于它的付费服务）需要商用授权——见 [COMMERCIAL.md](COMMERCIAL.md)。v4.0.1 之前的版本仍为纯 MIT。
