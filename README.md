<!-- About 简介（推送后填写到仓库 About 栏）：
JD撰写专家：岗位信息→职责/任职资格→评分→多版本，18条规则审计偏见词 ｜ 一键安装：/plugin marketplace add lhg-plugs/lhg-job-desc
-->
<!-- topics（推送后打）：claude-code, claude-plugin, agent-skills, jd, recruiting, hiring -->

# lhg-job-desc：JD撰写专家

> **一句话介绍**：给 AI 助手装上"JD 撰写组合拳"——粘贴岗位信息，六章结构撰写→职责/任职资格分级→JD 评分→招聘网站版/内推版/猎头版多版本输出，18 条确定性规则自动拦截性别/年龄/户籍歧视词。
>
> **一键安装**：在 Claude Code 里运行
> ```
> /plugin marketplace add lhg-plugs/lhg-job-desc
> /plugin install lhg-job-desc@lhg-plugs
> ```

> **⚠️ 先说红线**：本插件**不写任何歧视性表述**——限男性/35岁以下/限户籍/已婚已育优先/形象气质佳等，
> 写进去会被审计脚本判 blocker 并被发布硬门拦截；**不编造公司信息**——融资/规模/荣誉没有来源一律标 `[待确认]`。

## 它是什么

`lhg-job-desc` 是一个 Claude Code 插件（plugin 为主、skill 为辅）：

- **4 个命令**（小白入口）：`jd` 撰写一条龙，`jd-check` 自查，`jd-score` 评分，`jd-versions` 多版本
- **4 个平台中立 skill**（方法论，可移植到豆包/Workbuddy 等）：JD 六章结构、职责撰写、任职资格分级、包容性语言
- **2 个专家 agent**：JD 撰写专家、JD 审计专家
- **2 个硬门 hooks**：发布前审计拦截（blocker 未清零不许发布）、写 JD 文件歧视词即时警告（均可一键豁免）
- **18 条确定性审计规则**：5 条包容性（性别/年龄/户籍/婚育/外貌）+ 3 条结构 + 3 条薪资 + 2 条篇幅 + 3 条完整 + 2 条格式，纯 Python、零第三方依赖，秒级出结果

## 4 个命令用法

| 命令 | 作用 | 示例 |
|---|---|---|
| `/lhg-job-desc:jd` | 岗位信息→六章 JD→评分→多版本，一条龙 | `/lhg-job-desc:jd`（然后粘贴岗位信息） |
| `/lhg-job-desc:jd-check` | JD 自查：18 条规则审计 + 人工复核 4 项 | `/lhg-job-desc:jd-check jd.md --fix` |
| `/lhg-job-desc:jd-score` | JD 评分：审计 + 5 维 10 分制打分表 | `/lhg-job-desc:jd-score jd.md` |
| `/lhg-job-desc:jd-versions` | 多版本：招聘网站版/内推版/猎头版 | `/lhg-job-desc:jd-versions jd.md` |

## 自查说明

自查 = 确定性脚本（机器）+ 人工复核清单（人）：

1. 先跑 `scripts/audit/jd_audit.py --target <JD文件或目录>`，零成本；
2. 发现分三级：**blocker**（性别/年龄/户籍歧视词、缺核心章节、占位符残留，必须清零）、**warning**（婚育/外貌歧视、职责空话、薪资缺失/过宽、错别字、配比失衡，逐条修或给理由）、**nit**（JD 过短、标点不统一）；
3. 再按 `jd-check` 命令过一遍脚本抓不到的 4 项（职责是否说人话、要求是否招得到人、薪资是否有诚意、公司介绍是否像广告）。

blocker 清零才算"可发布"；**把歧视词换成隐晦说法（如"限男性"改"需要较强体力"）算换皮，照样拦截**。

## 目录结构

```
lhg-job-desc/
├── .claude-plugin/          # plugin.json（插件清单）+ marketplace.json（本仓即市场）
├── commands/                # 4 个命令：jd / jd-check / jd-score / jd-versions
├── skills/                  # 4 个平台中立 skill（lhg-jd-structure/duty/qual/inclusive）
├── agents/                  # 2 个专家 agent（jd-writer / jd-auditor）
├── hooks/                   # 2 个硬门（发布拦截 / 歧视词警告）+ 豁免说明
├── scripts/audit/           # 18 条确定性审计规则（零第三方依赖）
├── fixtures/                # 冒烟测试用例（bad/a.md + bad/b.md / good/jd.md）
├── smoke_test.py            # 一键冒烟测试（51 项）
├── ATTRIBUTION.md           # 灵感来源声明
└── LICENSE                  # MIT
```

## 什么时候用 / 什么时候不用

**什么时候用：**

- 你要从零写一份 JD，只有用人部门几句口头描述 → `/lhg-job-desc:jd` 15 分钟出初稿
- JD 写完准备发布，吃不准有没有歧视风险 → `/lhg-job-desc:jd-check` 先审后发
- 手里有 2-3 份 JD，不知道哪份好 → `/lhg-job-desc:jd-score` 量化打分横向对比
- 一份 JD 要发招聘网站、转内推、给猎头三个渠道 → `/lhg-job-desc:jd-versions` 一次生成三版

**什么时候不用：**

- 你想让 AI 帮你把"限男性""35岁以下"写得委婉点蒙混过关 → **本插件不干这个**，这是红线，换皮照样拦截
- 你要的是英文 Offer Letter / 劳动合同 → 本插件只做 JD（职位描述），不做法律文书
- 你希望 JD 自动发布到招聘网站 → 本插件只生成和审计文本，发布动作由你亲手完成（发布前硬门会先审计）
- 你只想找个 JD 模板套一套 → 去套模板更快；本插件是"撰写+审计+评分"全链路，模板只是副产品

## lhg-plugs 插件矩阵

| 插件 | 一句话 | 安装 |
|---|---|---|
| [lhg-job-desc](https://github.com/lhg-plugs/lhg-job-desc) | JD撰写专家：岗位信息→评分→多版本，18条规则拦截歧视词 | `/plugin install lhg-job-desc@lhg-plugs` |
| *（后续插件在此追加，保持表格格式一致）* | | |

## 自检与反馈

本插件自带质检：每次使用后可跑 `python3 smoke_test.py` 一键验证（JSON 合法、skill/command/agent 完整性、18 条规则、fixtures 命中、hooks 行为）。

发现 bug 或有改进建议，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-job-desc/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。

## 出品：刘洪光

本插件由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 抖音：搜「刘老师讲AI实战」
- 微信：lhgsmsw
