# Bootstrap Wiki

Build LLM Wiki from scratch。

LLM Wiki 是双层系统：skill 层编码 agent 可执行的能力，wiki 层编码可查询的知识网络。两者通过 `[[wiki-link]]` 互联，由 refs/（不可变素材）支撑，glossary.md 控熵。

## Phase 0: Ask

用 AskUserQuestion 一轮收集四个建站参数：

1. 系统定位：这个 LLM Wiki 服务于什么场景/解决什么问题？
2. 资产盘点：已有哪些可直接纳入的资产？[多选项]（已有 skill 或 prompt 模板、已有文档、外部抓取、访谈/会议纪要、从零开始）
3. 核心实体：系统的锚点是谁或什么？[自由输入]（个人系统通常是创建者；团队系统可能是产品或组织）
4. 能力规划：agent 需要具备哪些可执行能力？[自由输入]（每个能力对应一个 skill 目录。暂无明确规划也可后续追加）

## Phase 1: Scaffold

根据 Ask 结果执行脚本：

```bash
scripts/scaffold-wiki.sh <base_path> "<domain>" "<creator_name>"
```

脚本创建基础结构：

```
<base_path>/
├── refs/                  # 不可变素材层
├── wiki/
│   ├── concepts/          # 可复用框架、决策模型
│   ├── summaries/         # 素材摘要（绑定单一 ref 源）
│   └── entities/          # 人、产品、组织
├── wiki/index.md          # 知识定位入口
├── wiki/log.md            # 操作日志
├── wiki/overview.md       # 系统概览（待填充）
├── glossary.md            # 全局术语表：空表带 schema，建立预期，内容随 ingest 生长
├── inbox.md               # 摩擦账本：agent 写、人固化，吸收即删
└── .claude/settings.json  # PostToolUse hook：每次编辑 wiki 页面即跑 wiki-lint；已接入则跳过
```

- Skill 目录不由脚本创建。根据 Ask 中的能力规划，agent 在 Phase 2 按需建立。
- 工具层按需生长，首次写入时 `mkdir -p`：脚本先长成 `scripts/`，模板与配置多到需要归拢时才升为 `utils/`。用户个人习惯的目录（如自产文档区）由其自建，脚手架不预设。

## Phase 2: Seed

脚本完成后，agent 执行初始化：

1. 填充 overview.md：根据 Ask 结果写入系统定位、核心实体、层级关系、运行模式。

2. 创建锚点实体页：走 `entity-bootstrap.md` 流程采集实体信息，产出写入 `wiki/entities/`。更新 index.md。

3. 资产分拣：根据 Ask 中的资产盘点，扫描用户指定路径。按资产性质分流：
   - 可执行的 prompt/workflow/SOP → 评估是否值得建为独立 skill
   - 方法论、参考文档 → 复制到 refs/
   - 可执行脚本 → scripts/；可复用模板、工具配置 → utils/（按需建目录）
   - 列出建议的 ingest 顺序（优先基础性、高关联度素材）

4. 能力层初始化：若 Ask 中有明确的能力规划，为每个能力建 skill 骨架目录（SKILL.md frontmatter + 空 references/）。具体内容待后续迭代填充。

Phase 2 完成后，系统具备运行条件。素材走 wiki-ingest 正常流程，能力迭代走 skill-creator 辅助。

## Schema 集成

读取 `assets/agents-wiki-layer.md` 模板，追加到项目根目录 AGENTS.md
