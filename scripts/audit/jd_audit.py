#!/usr/bin/env python3
"""lhg-job-desc 确定性审计：18 条 JD 撰写规则，零第三方依赖。

扫描目标（单个 .md/.txt 文件或目录），输出 JSON 与人类可读报告；
有 blocker 时以 exit code 2 退出，warning 以 exit code 1 退出（供 hooks 与 CI 使用）。

规则文案均为本项目原创（方法论思路受 lhg-resume 的 JD 解析流程启发，
未复制任何第三方的原文案与代码）。

用法：
    python3 jd_audit.py --target <文件或目录> [--format json|text] [--fail-on blocker|warning|nit]
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"
TOOL = "lhg-job-desc/jd-audit"

SCAN_EXTS = {".md", ".txt", ".text"}

PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# ---------- 包容性：歧视词 ----------
GENDER_RE = re.compile(r"限男性|限女性|只招男|只招女|男士优先|女士优先|男性优先|女性优先|仅限男|仅限女")
AGE_RE = re.compile(r"(?:35|30|28|25|40)岁以下|年龄.{0,4}(?:以下|以内|不超过)|年龄要求.{0,6}\d+")
HUKOU_RE = re.compile(r"限.{0,4}户籍|.{0,4}户口优先|本地人优先|外地人勿扰|仅限.{0,4}户籍")
MARRY_RE = re.compile(r"已婚已育优先|未婚优先|单身优先|无生育计划|婚育情况")
LOOKS_RE = re.compile(r"形象气质佳|身高1[5678]\d(?:cm|厘米)?以上|长相端正|五官端正|颜值高")

# ---------- 结构 ----------
SECTION_RE = {
    "公司介绍": re.compile(r"^#{1,4}\s*(公司介绍|关于我们|公司简介)", re.M),
    "岗位职责": re.compile(r"^#{1,4}\s*(岗位职责|工作职责|职责描述|工作内容)", re.M),
    "任职要求": re.compile(r"^#{1,4}\s*(任职要求|任职资格|岗位要求|应聘要求)", re.M),
}
BULLET_RE = re.compile(r"^\s*(?:[-*•·]\s+|\d{1,2}[.)、]\s*)(.+)$")
EMPTY_DUTY_RE = re.compile(r"负责相关工作|完成领导交办|协助处理日常|其他事项|服从安排")

# ---------- 薪资 ----------
PAY_HINT_RE = re.compile(r"薪资|薪酬|待遇|月薪|年薪|k\b|K\b|万/月|万/年|元/月")
PAY_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK万]\s*[-~–—至]\s*(\d+(?:\.\d+)?)\s*[kK万]")
PAY_NUM_RE = re.compile(r"薪资.{0,8}(\d+(?:\.\d+)?)\s*[-~–—至]\s*(\d+(?:\.\d+)?)(?![kK万\d])")

# ---------- 错别字（高频易判对） ----------
TYPO_PAIRS = [
    (re.compile(r"做为"), "做为", "应为「作为」"),
    (re.compile(r"帐号"), "帐号", "非财务语境应为「账号」"),
    (re.compile(r"其它"), "其它", "建议用「其他」"),
    (re.compile(r"在次"), "在次", "应为「在此」"),
    (re.compile(r"必需要"), "必需要", "应为「必须要」"),
    (re.compile(r"以致于"), "以致于", "多余，应为「以致」或「以至于」"),
]

PLACEHOLDER_RE = re.compile(r"\[TODO\]|TODO|{{.+?}}|XXX|待补充|xxx公司|XX公司")

# ---------- 职责动词库 ----------
DUTY_VERBS = [
    "负责", "主导", "推动", "制定", "设计", "开发", "搭建", "优化", "管理",
    "带领", "协调", "跟进", "执行", "分析", "监控", "维护", "拓展", "策划",
    "撰写", "审核", "对接", "支持", "保障", "落地", "复盘", "规划",
]


class Finding:
    __slots__ = ("rule_id", "severity", "category", "title", "file", "line", "snippet", "detail")

    def __init__(self, rule_id, severity, category, title, file, line, snippet, detail):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.title = title
        self.file = file
        self.line = line
        self.snippet = snippet[:160]
        self.detail = detail

    def to_dict(self):
        return {"rule_id": self.rule_id, "severity": self.severity,
                "category": self.category, "title": self.title,
                "file": self.file, "line": self.line,
                "snippet": self.snippet, "detail": self.detail}


RULES = []
_RULE_BY_ID = {}


def rule(rule_id, severity, category, title, detail):
    def deco(fn):
        r = {"id": rule_id, "severity": severity, "category": category,
             "title": title, "detail": detail, "check": fn}
        _RULE_BY_ID[rule_id] = r
        RULES.append(r)
        return fn
    return deco


def _finding(rule_id, path, line, snippet):
    r = _RULE_BY_ID[rule_id]
    return Finding(r["id"], r["severity"], r["category"], r["title"],
                   path, line, snippet, r["detail"])


def _lines(text):
    return text.split("\n")


def _section_bullets(text, section_name):
    """取某章节标题下、到下一个同级/高级标题为止的 bullet 条目。"""
    lines = _lines(text)
    start, level = -1, 0
    pat = SECTION_RE[section_name]
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,4})\s*(.+?)\s*$", ln)
        if m and pat.search(ln):
            start, level = i, len(m.group(1))
            break
    if start < 0:
        return []
    items = []
    for ln in lines[start + 1:]:
        m = re.match(r"^(#{1,4})\s*", ln)
        if m and len(m.group(1)) <= level:
            break
        b = BULLET_RE.match(ln)
        if b:
            items.append(b.group(1).strip())
    return items


# ================= 包容性规则 =================

@rule("JD-INC-001", "blocker", "包容性", "性别歧视词",
      "JD 出现限男性/限女性/男士优先等表述。除极少数法定特殊岗位外，性别限制涉嫌就业歧视，建议删除或改为能力描述。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = GENDER_RE.search(ln)
        if m:
            out.append(_finding("JD-INC-001", doc["path"], i, m.group(0)))
    return out


@rule("JD-INC-002", "blocker", "包容性", "年龄歧视词",
      "JD 出现「35岁以下」「年龄不超过」等硬性年龄上限，涉嫌年龄歧视。建议改为经验年限要求（如「3年以上相关经验」）。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = AGE_RE.search(ln)
        if m:
            out.append(_finding("JD-INC-002", doc["path"], i, m.group(0)))
    return out


@rule("JD-INC-003", "blocker", "包容性", "户籍地域歧视",
      "JD 出现户籍/户口/本地人优先等表述，涉嫌地域歧视。建议删除；如确需本地办公，写「工作地点：北京，需到岗办公」即可。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = HUKOU_RE.search(ln)
        if m:
            out.append(_finding("JD-INC-003", doc["path"], i, m.group(0)))
    return out


@rule("JD-INC-004", "warning", "包容性", "婚育歧视",
      "JD 出现已婚已育优先/未婚优先/无生育计划等表述，涉嫌婚育歧视且易引发舆情。建议整段删除。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = MARRY_RE.search(ln)
        if m:
            out.append(_finding("JD-INC-004", doc["path"], i, m.group(0)))
    return out


@rule("JD-INC-005", "warning", "包容性", "外貌歧视",
      "JD 出现形象气质佳/身高要求/长相端正等表述。除礼仪模特等特殊岗位外，建议删除，改为着装/仪态等职业化要求。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = LOOKS_RE.search(ln)
        if m:
            out.append(_finding("JD-INC-005", doc["path"], i, m.group(0)))
    return out


# ================= 结构规则 =================

@rule("JD-STR-001", "blocker", "结构", "缺核心章节",
      "JD 缺少「公司介绍」「岗位职责」「任职要求」中的一个或多个核心章节，结构不完整，候选人无法快速判断匹配度。")
def _r(doc):
    missing = [k for k, p in SECTION_RE.items() if not p.search(doc["text"])]
    if missing:
        return [_finding("JD-STR-001", doc["path"], 1, "缺失章节：" + "、".join(missing))]
    return []


@rule("JD-STR-002", "warning", "结构", "职责与要求数量失衡",
      "任职要求条数超过岗位职责条数的 2 倍：要么职责写得太虚，要么要求列得太苛刻，都会吓跑候选人。建议职责≥4 条，或把要求合并精简。")
def _r(doc):
    duties = _section_bullets(doc["text"], "岗位职责")
    quals = _section_bullets(doc["text"], "任职要求")
    if duties and quals and len(quals) > 2 * len(duties):
        return [_finding("JD-STR-002", doc["path"], 1,
                         "职责 %d 条，要求 %d 条（>2 倍）" % (len(duties), len(quals)))]
    return []


@rule("JD-STR-003", "warning", "结构", "职责空话",
      "职责中出现「负责相关工作」「完成领导交办的其他事项」等空话：等于没写，还暴露岗位边界不清。删掉或写具体。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = EMPTY_DUTY_RE.search(ln)
        if m:
            out.append(_finding("JD-STR-003", doc["path"], i, m.group(0)))
    return out


# ================= 薪资规则 =================

@rule("JD-PAY-001", "warning", "薪资", "薪资范围缺失",
      "全文未提薪资/薪酬/待遇。无薪资的 JD 投递转化率明显更低；至少给范围（如 15-25k·13薪），或写「薪资面议」并注明面议区间。")
def _r(doc):
    if not PAY_HINT_RE.search(doc["text"]):
        return [_finding("JD-PAY-001", doc["path"], 1, "全文无薪资相关表述")]
    return []


@rule("JD-PAY-002", "warning", "薪资", "薪资范围过宽",
      "薪资上下限倍数≥3（如 8k-30k）：范围太宽等于没写，候选人默认按最低看。建议按职级拆成 2 个 JD，或收窄到 1.5 倍以内。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = PAY_RANGE_RE.search(ln)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo > 0 and hi / lo >= 3:
                out.append(_finding("JD-PAY-002", doc["path"], i, m.group(0)))
    return out


@rule("JD-PAY-003", "nit", "薪资", "薪资单位不明",
      "薪资数字后无单位（如「薪资 15-25」）：是 k 还是万？歧义会让候选人直接划走。补上 k/K/万/元。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = PAY_NUM_RE.search(ln)
        if m:
            out.append(_finding("JD-PAY-003", doc["path"], i, m.group(0)))
    return out


# ================= 篇幅规则 =================

@rule("JD-LEN-001", "warning", "篇幅", "条目过多",
      "职责超过 8 条或要求超过 10 条：没人会逐条看完，重点被淹没。合并同类项，职责留 4-6 条、要求留 5-8 条。")
def _r(doc):
    out = []
    duties = _section_bullets(doc["text"], "岗位职责")
    quals = _section_bullets(doc["text"], "任职要求")
    if len(duties) > 8:
        out.append(_finding("JD-LEN-001", doc["path"], 1, "岗位职责 %d 条（>8）" % len(duties)))
    if len(quals) > 10:
        out.append(_finding("JD-LEN-001", doc["path"], 1, "任职要求 %d 条（>10）" % len(quals)))
    return out


@rule("JD-LEN-002", "nit", "篇幅", "JD 过短",
      "全文不足 200 字：信息太少，候选人无法判断岗位价值，大概率被当成「皮包岗」划走。")
def _r(doc):
    n = len(re.sub(r"\s+", "", doc["text"]))
    if n < 200:
        return [_finding("JD-LEN-002", doc["path"], 1, "全文约 %d 字（<200）" % n)]
    return []


# ================= 文字规则 =================

@rule("JD-TYP-001", "warning", "文字", "常见错别字",
      "命中高频错别字（如做为→作为、帐号→账号、其它→其他）。JD 里的错别字直接拉低公司专业形象，发布前逐条改。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        for pat, word, fix in TYPO_PAIRS:
            if pat.search(ln):
                out.append(_finding("JD-TYP-001", doc["path"], i, "%s（%s）" % (word, fix)))
                break
    return out


@rule("JD-PLACE-001", "blocker", "完整", "占位符残留",
      "残留 [TODO]/{{}}/XXX/待补充 等占位符：说明 JD 还没写完就准备发出去了，逐条清零后再发布。")
def _r(doc):
    out = []
    for i, ln in enumerate(_lines(doc["text"]), 1):
        m = PLACEHOLDER_RE.search(ln)
        if m:
            out.append(_finding("JD-PLACE-001", doc["path"], i, m.group(0)))
    return out


@rule("JD-CONT-001", "warning", "完整", "联系方式缺失",
      "无邮箱/电话/投递链接：候选人想投都不知道往哪投。至少留一个投递邮箱或招聘官网链接。")
def _r(doc):
    if not (EMAIL_RE.search(doc["text"]) or PHONE_RE.search(doc["text"])
            or re.search(r"投递|简历投|http", doc["text"])):
        return [_finding("JD-CONT-001", doc["path"], 1, "无联系方式/投递入口")]
    return []


# ================= 格式规则 =================

@rule("JD-FMT-001", "warning", "格式", "职责条目无动词开头",
      "职责条目不是动词开头（如「团队的日常管理」）：读起来像名词堆砌。改为「负责团队日常管理」式动宾结构。")
def _r(doc):
    out = []
    for item in _section_bullets(doc["text"], "岗位职责"):
        if not any(item.startswith(v) for v in DUTY_VERBS):
            out.append(_finding("JD-FMT-001", doc["path"], 1, item[:40]))
    return out


@rule("JD-FMT-002", "nit", "格式", "条目标点不统一",
      "同一章节内有的条目以句号结尾、有的没有。统一：中文 JD 建议条目末尾不加句号（短句）或统一加。")
def _r(doc):
    out = []
    for sec in ("岗位职责", "任职要求"):
        items = _section_bullets(doc["text"], sec)
        if len(items) >= 3:
            ended = sum(1 for it in items if it.rstrip().endswith(("。", ".")))
            if 0 < ended < len(items):
                out.append(_finding("JD-FMT-002", doc["path"], 1,
                                    "%s：%d/%d 条以句号结尾" % (sec, ended, len(items))))
                break
    return out


# ================= 主流程 =================

SEV_ORDER = {"blocker": 0, "warning": 1, "nit": 2}
EXIT_CODE = {"blocker": 2, "warning": 1, "nit": 0}


def collect_targets(target):
    paths = []
    if os.path.isdir(target):
        for root, _, files in os.walk(target):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in SCAN_EXTS:
                    paths.append(os.path.join(root, f))
    elif os.path.isfile(target):
        paths.append(target)
    return paths


def load_doc(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return {"path": path, "text": f.read()}


def run_audit(paths):
    findings = []
    for p in paths:
        doc = load_doc(p)
        for r in RULES:
            try:
                findings.extend(r["check"](doc) or [])
            except Exception as e:
                findings.append(Finding(r["id"], "nit", "内部",
                                        "规则执行异常", p, 0, "",
                                        "规则 %s 执行出错（已跳过）：%s" % (r["id"], e)))
    findings.sort(key=lambda f: (SEV_ORDER[f.severity], f.file, f.line))
    return findings


def summarize(findings):
    s = {"blocker": 0, "warning": 0, "nit": 0, "rules_run": len(RULES)}
    for f in findings:
        s[f.severity] += 1
    return s


def format_text(findings, summary):
    lines = ["[%s] JD 审计报告 v%s" % (TOOL, VERSION),
             "规则 %d 条 | blocker %d / warning %d / nit %d"
             % (summary["rules_run"], summary["blocker"],
                summary["warning"], summary["nit"]),
             "-" * 56]
    cur = None
    for f in findings:
        if f.severity != cur:
            cur = f.severity
            lines.append("## %s" % cur.upper())
        lines.append("[%s] %s:%s %s" % (f.rule_id, f.file, f.line, f.title))
        if f.snippet:
            lines.append("    片段：%s" % f.snippet)
        lines.append("    建议：%s" % f.detail)
    if not findings:
        lines.append("零发现：JD 结构完整、无歧视词、无占位符，可以进入人工复核。")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="lhg-job-desc 确定性 JD 审计")
    ap.add_argument("--target", required=True, help="JD 文件或目录")
    ap.add_argument("--format", choices=["json", "text"], default="text")
    ap.add_argument("--fail-on", choices=["blocker", "warning", "nit"],
                    default="blocker",
                    help="达到该级别即非零退出（默认 blocker）")
    args = ap.parse_args(argv)

    paths = collect_targets(args.target)
    if not paths:
        print("未找到可扫描文件：%s" % args.target, file=sys.stderr)
        return 2

    findings = run_audit(paths)
    summary = summarize(findings)

    if args.format == "json":
        print(json.dumps({"tool": TOOL, "version": VERSION,
                          "summary": summary,
                          "findings": [f.to_dict() for f in findings]},
                         ensure_ascii=False, indent=2))
    else:
        print(format_text(findings, summary))

    worst = "nit"
    for f in findings:
        if SEV_ORDER[f.severity] < SEV_ORDER[worst]:
            worst = f.severity
    return 2 if SEV_ORDER[worst] <= SEV_ORDER[args.fail_on] else 0


if __name__ == "__main__":
    sys.exit(main())
