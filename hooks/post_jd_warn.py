#!/usr/bin/env python3
"""lhg-job-desc 硬门②：写 JD 文件时若含歧视词，给出即时警告。

触发：PostToolUse / Write|Edit。只检查 .md/.txt 文件中是否出现
性别/年龄/户籍/婚育/外貌歧视词；命中则 additionalContext 提醒，
不拦截（写草稿是用户的自由，发布前有 pre_jd_publish 硬门兜底）。

逃生：LHG_JD_HOOKS_OFF=1。内部出错 fail-open。零第三方依赖。
"""

import json
import os
import re
import sys

BIAS_RES = [
    (re.compile(r"限男性|限女性|只招男|只招女|男士优先|女士优先|男性优先|女性优先"), "性别歧视词"),
    (re.compile(r"(?:35|30|28|25|40)岁以下|年龄.{0,4}(?:以下|以内|不超过)"), "年龄歧视词"),
    (re.compile(r"限.{0,4}户籍|.{0,4}户口优先|本地人优先"), "户籍地域歧视词"),
    (re.compile(r"已婚已育优先|未婚优先|单身优先"), "婚育歧视词"),
    (re.compile(r"形象气质佳|身高1[5678]\d(?:cm|厘米)?以上"), "外貌歧视词"),
]

TEXT_EXTS = {".md", ".txt", ".text"}


def main() -> int:
    if os.environ.get("LHG_JD_HOOKS_OFF") == "1":
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open

    tool_input = payload.get("tool_input", {}) or {}
    path = tool_input.get("file_path", "") or ""
    if os.path.splitext(path)[1].lower() not in TEXT_EXTS:
        return 0
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return 0  # fail-open

    hits = []
    for pat, label in BIAS_RES:
        m = pat.search(text)
        if m:
            hits.append("%s（如「%s」）" % (label, m.group(0)[:12]))
    if not hits:
        return 0

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext":
                "⚠️ 检测到 JD 疑似歧视表述：%s。\n"
                "建议立即删除或改写（跑 scripts/audit/jd_audit.py 看完整报告）；"
                "发布前 pre_jd_publish 硬门会拦截含 blocker 的发布。" % "、".join(hits),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
