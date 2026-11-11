<!-- wallaby-agent-rules 1.4.3 -->
# wallaby-agent-rules（中文版）

[![License: MIT + Commons Clause](https://img.shields.io/badge/License-MIT%20%2B%20Commons%20Clause-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.4.3-blue.svg)](CHANGELOG.md)

**AI 记得住，你找得到。**

给你的项目配一个长期记忆——也给你自己一张项目地图。两段粘贴即用的提示词、五个纯文本文件、零依赖。适配任何 AI 编码工具。English: [README.md](README.md)。

我们自己在真实业务里天天跑这套系统。截至 2026 年 10 月，它已记录下 45 次记忆失败——每一条都带日期、带出处，并且都变成了你能在这个仓库里看到的一条规则或一道扫描（[失败分类学全文，带证据](https://wallabytoken.com/blog/p/ai-memory-benchmarks-wrong-thing.html)）。

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

**🧩 Hermes Agent，一条命令**——整套装成可安装技能：

```
hermes skills install Dawncoral/wallaby-agent-rules/skills/agent-memory-rules
```

**🛠 治理包，约 1 分钟**——可选的传导、前提检查、矛盾历史和验收回执：

```
python3 extras/memory-governance/memory_governance.py --target /path/to/your-project init
cd /path/to/your-project
python3 scripts/memory_governance.py doctor
```

不能抓 URL？直接打开 [PROMPT.zh-CN.md](PROMPT.zh-CN.md) 复制对应段落粘贴——纯文本。

## 你会得到什么

| 文件 | 职责 |
|---|---|
| `AGENTS.md`（或按你的工具用 `CLAUDE.md` / `.cursorrules`） | 入口——告诉 AI 每次开工先读记忆 |
| `MEMORY.md` | 长期记忆：永久事实、关键决策、铁规矩 |
| `NOW.md` | 当前状态：正在做的事、最近碰过的 |
| `INDEX.md` | 项目地图：一个文件一行——首版由 AI 当场扫描你的项目生成。管辖范围：文档与知识文件；代码文件归 git 与 CHANGELOG 管，索引不重复 git 的活 |
| `scripts/health_check.py` | 零依赖每周检查，十项扫描：根目录杂物、构建残余、索引双向漂移、过期条目、入口文件体积墙（字节/行数/token 三维，中文敏感）、无日期事实、MEMORY 预算与降级候选、密钥卫生、提交沉默检测 |
| `scripts/reconcile.py` | 零依赖每周对账，两项扫描：日志声称「已完成」而 NOW.md 里还在进行、以及没有任何证据可查的「已完成」 |
| 信任培养模式（默认开） | 前两周，新的长期记忆条目先**提报**给你批准才转正——你先看着 AI 选择记什么，再放开让它直接写 |
| 代码与版本节（代码项目） | 当前发布版本=带日期的记忆事实，一变就更新；每次发布/迁移/回滚都带 commit 号落日志 |

安装完成的那一刻，你会看着 AI 扫完你的项目并交出第一份 `INDEX.md`——「你找得到」当场兑现。

**1.4.3 新增**：[记忆治理包](extras/memory-governance/)把能力表、地图、传导检查和记忆文件接到一起。`route` 为一次改动出一张约 2 KB 的卡：能复用什么、碰到地图上哪些组件、要同步哪些面、走轻档还是重档，以及只列改动路径所依赖的前提。`audit` 查漏登和失效条目，`map sync` 让 MAP.md 里的机器区保持最新，`split` 把 LOG.md 已结束的月份切成分卷；MEMORY.md 和 INDEX.md 的拆分要你确认才执行，每次分裂都能回滚。`audit` 还会量 agent 加载的说明文件：第一次运行自动记下基线，之后超了就提示，并指出跨文件重复的规则；只报告，不拦截。另有可选的[记忆 MCP 服务器](extras/memory-mcp/)，给读不到入口文件的 agent 用同一套文件，九个工具，38 项冒烟自检。一次改动现在只要两条命令：改之前 `route --record`，改完 `verify`。`write` 往记忆文件里加一行并先做检查，已有的行一个字节都不动。`events` 把每次写入连同是哪个 agent 写的记下来；`id` 给每条决定、失败记录和回执发号，同一台机器上不会有两个 agent 拿到同一个号。从 1.4.0、1.4.1 或 1.4.2 升级只替换命令行这一个文件，其他文件都不变。

**1.4.2 新增**：治理 CLI 无损升级。`upgrade` 默认只预览并拒绝降级，`--apply` 会先备份再只替换 CLI；新 CLI 必须能启动并报告预期版本，否则自动恢复旧脚本。记忆文件、配置、回执和其他项目文件均不受影响。

**1.4.1 新增**：[《周轧差创建指南》](extras/memory-governance/WEEKLY_RECONCILE.md)把检查变成可重复的复核流程：确定范围、机械扫描、小样本语义复核、前提与矛盾检查、责任人分配，以及一页报告模板。

**1.4.0 新增**：[记忆治理包](extras/memory-governance/)把变更传导变成可执行检查。九类事件映射到必触面，前提失败返回非零退出码，矛盾历史只追加，旧引用或未读文件仍在时验收回执不能转绿。三个可选模板 [MAP.md](templates/MAP.md)、[CAPABILITIES.md](templates/CAPABILITIES.md)、[FAILURES.md](templates/FAILURES.md) 和 [10 个脱敏失败示例](examples/FAILURES.example.md)让系统更容易交接。收工流程现在要求 LOG.md 与 NOW.md 在同一动作里更新。现有安装继续有效，每项新增都可单独采用。见 [1.3 到 1.4 升级卡](upgrade/1.3-to-1.4.md)。

**1.3.0 新增**：Skill Forge——同一治理思想，上移一层。记忆体系管 AI *记得什么*；[Skill Forge](extras/skill-forge/) 管它*会做什么*：技能从需求推导起步（带高危确认清单），按实测过的规格生成，再靠技能自己写故障台账持续纠偏。三种形态同一协议——MCP 服务器、即贴即用提示词包、可安装技能。装进你项目的文件没有任何变化；它是 `extras/` 下的独立工具包。

**1.1.0 新增**：三项卫生加固，全部来自我们在自己业务里跑这套系统记下的失败形态——MEMORY 老化（软上限约 150 行带日期条目或约 8k 估算 token，token 估算对中文按字加权；超上限后闲置 30 天以上的事实在收工时降级进 LOG.md，低于上限则完全静默）、密钥卫生扫（被 git 追踪的凭证文件与常见密钥模式会被抓到，占位符不误报；它只是提醒，不是保险网——让密钥远离 git 靠的是习惯，不是一道闸）、提交沉默检测（有 git 提交而 NOW.md/LOG.md 里没有对应记录，当场显形）。另：INDEX.md 管辖范围写明（管文档与知识文件——代码归 git 管），并附 `extras/pre-commit.sample` 可选钩子样件给想要强制的人。它刻意只是样件：检出加节奏才是系统本体，阻断式钩子第一次烦到人就会被 `--no-verify` 绕过。

**v4.1 新增**：代码版本记忆模块（条件挂载——问卷会问你这个项目是否涉及写代码，涉及才装）+ 完整中文版。

**v4 新增**：信任培养模式（前两周记忆写入需批准——默认开、问卷一题、到期自动结束）+ 工具接入矩阵与每工具一张卡（[templates/integrations/](templates/integrations/)）+ 起用 GitHub Releases。

## 你的工具怎么接

无插件、无 MCP server、无需安装——入口文件就是集成。每个工具读自己的入口文件；启动面谈会帮你选对。读不到入口文件的 agent，可以用可选的[记忆 MCP 服务器](extras/memory-mcp/)读同一套文件。

| 工具 | 入口文件 | 备注 |
|---|---|---|
| Claude Code | `CLAUDE.md` | 每次会话开始即读；`/memory` 可快速编辑 |
| Codex | `AGENTS.md` | 原生约定 |
| Cursor | `AGENTS.md` | 原生支持；记忆集中在这里，别拆进 `.cursor/rules` |
| GitHub Copilot | `AGENTS.md` | 原生支持；若已有 `.github/copilot-instructions.md` 也会被读取 |
| Hermes | `AGENTS.md` | 原生；git 根目录到工作目录链式加载；也可装成 hub 技能 |
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

## 跑这套系统要花多少钱

记忆系统 = 一段固定前缀：`MEMORY.md` 和 `NOW.md` 跟着每次调用走。这笔成本不大；有提示词缓存时，大头按缓存命中价计。

按 Kimi K3 算笔账。健康的 `MEMORY.md` 在健康检查强制执行的约 8k 估算 token 软上限以内，整个前缀按 10k token 计；每天 100 次调用，一个月过表的前缀量是 30M token：

| 每月前缀成本 | 输入，未命中缓存 | 输入，命中缓存 |
|---|---|---|
| 官方刊例 | $90.00（$3.00 / 1M token） | $9.00（$0.30 / 1M token） |
| Wallaby | $76.50（$2.55 / 1M token） | $7.65（$0.255 / 1M token） |

省下来的大头来自缓存：两份价目表里，缓存命中价都是输入价的十分之一。我们的费率是官方刊例的 8.5 折。前缀没动就便宜重读；真改了记忆，按全价输入计一次。同模型、同权重、同 1M 上下文。费率截至 2026-11-05；现行费率见 [pricing.json](https://wallabytoken.com/pricing.json)。

想要这个价格，迁移只有一行：把 `base_url` 指向 `https://api.wallabytoken.com/v1`，换上你的 key——OpenAI 兼容。（[wallabytoken.com](https://wallabytoken.com) 是我们自己的产品，见文末「谁在做」。）

## 已在用？升级

把 [PROMPT.zh-CN.md](PROMPT.zh-CN.md) 里的 **L2 —— 升级检查** 提示词粘给你的 AI。它会识别你的版本（靠首行标记注释或文件指纹），给出增量升级清单——你逐项批准。**你的内容永远不会被覆盖。** 每个版本都发 GitHub Release（含迁移说明），watch 这个仓库即可收到通知。版本历史与迁移步骤：[CHANGELOG.md](CHANGELOG.md)；从早期版本迁移的一页卡：[upgrade/pre-1.0.md](upgrade/pre-1.0.md)。

## 路线图

至今已交付：收工仪式、深度健康检查（十项扫描：漂移、预算、老化、密钥卫生、提交沉默）、对账审计、信任培养模式、工具接入、代码版本模块、中文版、文件式记忆治理，以及带事件日志和编号计数器的受检写入通道。开源部分管的是一台机器上的一个项目：经命令行的每次写入都记下是哪个 agent 写的，编号不会撞。团队之间、跨机器的多 agent 记忆纪律属于商业层，架构评审与托管值守也在其中，见 [COMMERCIAL.md](COMMERCIAL.md)。自 1.0.0 起用语义化版本号；早期迭代（v1–v4.1）已并入 1.0.0——见 [CHANGELOG.md](CHANGELOG.md)。

## 这个仓库里还有

- [`templates/`](templates/)——NOW / INDEX / LOG 模板、可选 MAP / CAPABILITIES / FAILURES / PROFILE 模板，以及健康检查与对账脚本，可直接复制。
- [`templates/integrations/`](templates/integrations/)——每工具一张卡：入口文件、坑、30 秒自检。
- [`extras/memory-governance/`](extras/memory-governance/)——通过一个零依赖 CLI 提供传导、前提检查、矛盾历史、验收回执、改动路由、登记审计、地图同步、记忆分裂、受检写入、事件日志与编号计数器。
- [`extras/memory-mcp/`](extras/memory-mcp/)——把同一套记忆文件做成 MCP 服务器：读取、查找、提议、记日志、查能力表、为改动出路由卡；写入先脱敏，提议不进 MEMORY.md。
- [`skills/agent-memory-rules/`](skills/agent-memory-rules/)——整套系统打包成可安装的 agent 技能（SKILL.md + 两个检查脚本），适配 Hermes 及任何认 SKILL.md 约定的工具。
- [`extras/skill-forge/`](extras/skill-forge/)——Skill Forge：技能本身的生命周期治理。需求推导、按实测规格生成、故障台账、优化回路——MCP 服务器、提示词包、SKILL.md 技能三种形态。
- [`upgrade/`](upgrade/)——版本间的一页升级卡。
- [`COMMERCIAL.md`](COMMERCIAL.md)——商用授权：什么免费、什么要授权、怎么联系。
- [`AGENTS.md`](AGENTS.md) / [`MEMORY.md`](MEMORY.md)——v1 起始模板（token 预算纪律、三层记忆、相关方名册），仍有效，且本仓库自己也在用。
- [`examples/`](examples/)——填好的 MEMORY / NOW / INDEX 示例，另有 10 个脱敏合成失败条目。

## 谁在做

Wallaby Token（WALLABY DATA PTY LTD，ABN 90 701 729 964）提供开源大模型推理云服务。这套记忆系统每天跑在我们自己的项目上——不是我们卖的说辞，是我们依赖的基础设施。完整介绍：[wallabytoken.com](https://www.wallabytoken.com)。

## 许可证

MIT + [Commons Clause](LICENSE)——个人项目、研究、公司内部自用免费。把它卖出去（打包、托管、或基于它的付费服务）需要商用授权——见 [COMMERCIAL.md](COMMERCIAL.md)。v4.0.1 之前的版本仍为纯 MIT。
