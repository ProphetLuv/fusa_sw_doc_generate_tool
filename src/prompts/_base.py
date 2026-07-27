# -*- coding: utf-8 -*-
"""
Prompt 共享基础设施：ASIL 等级常量、覆盖率要求、AI-AP 判定表等。
所有 Agent Prompt 模块和 PromptManager 均依赖本模块。
"""

# ASIL 等级对应的 ISO 26262 Part 6 方法要求
_ASIL_REQUIREMENTS = {
    "QM": (
        "- 无特殊功能安全要求，按常规软件工程实践即可\n"
        "- 建议遵循基本编码规范，但不强制 MISRA C 合规"
    ),
    "ASIL A": (
        "- 需要结构化分析（SAD/SDD）\n"
        "- 单元测试建议达到语句覆盖率 ≥ 80%\n"
        "- 建议遵循 MISRA C:2023 规则（Directive/Required/Advisory），偏差需记录\n"
        "- 需要基本的故障检测机制"
    ),
    "ASIL B": (
        "- 需要完整的 SRS/SAD/SDD 文档链\n"
        "- 单元测试需达到分支覆盖率 ≥ 80%\n"
        "- 必须遵循 MISRA C:2023 Mandatory + Required 规则，偏差需正式论证\n"
        "- 需要 FMEA 分析覆盖所有安全相关功能\n"
        "- 需要看门狗、CRC 等基本安全机制"
    ),
    "ASIL C": (
        "- 需要完整的文档链 + 双向追溯矩阵\n"
        "- 单元测试需达到分支覆盖率 ≥ 90%\n"
        "- 必须遵循 MISRA C:2023 Mandatory + Required 规则，零偏差容忍\n"
        "- 需要 FMEA + FTA 组合分析\n"
        "- 需要冗余设计或多样性设计\n"
        "- 需要独立的代码审查和静态分析"
    ),
    "ASIL D": (
        "- 需要完整的文档链 + 双向追溯矩阵（需求↔设计↔代码测试）\n"
        "- 单元测试需达到 MC/DC 覆盖率 ≥ 90%\n"
        "- 必须遵循 MISRA C:2023 Mandatory + Required 规则，零偏差容忍\n"
        "- 需要 FMEA + FTA + DFA 组合分析\n"
        "- 需要软件多样性或硬件冗余\n"
        "- 需要独立的验证和确认（V&V）\n"
        "- 需要 WCET 分析和栈使用分析\n"
        "- 需要防御性编程和故障注入测试"
    ),
}


def get_asil_requirements(asil_level: str) -> str:
    """获取 ASIL 等级对应的 ISO 26262 方法要求文本。"""
    return _ASIL_REQUIREMENTS.get(asil_level, _ASIL_REQUIREMENTS["ASIL B"])


# ASIL 等级对应的覆盖率要求（用于 TC-UNIT）
_ASIL_COVERAGE = {
    "QM":    "语句覆盖率（无硬性指标）",
    "ASIL A": "语句覆盖率 ≥ 80%",
    "ASIL B": "分支覆盖率 ≥ 80%",
    "ASIL C": "分支覆盖率 ≥ 90%",
    "ASIL D": "MC/DC 覆盖率 ≥ 90%",
}


def get_asil_coverage(asil_level: str) -> str:
    """获取 ASIL 等级对应的覆盖率要求文本。"""
    return _ASIL_COVERAGE.get(asil_level, _ASIL_COVERAGE["ASIL B"])


# AI-AP 判定表说明（AIAG-VDA FMEA 手册 2019）
AI_AP_TABLE = """
**AI-AP（行动优先级）判定规则**（依据 AIAG-VDA FMEA 手册 2019）：

AI-AP 由严重度(S)、发生度(O)、检测度(D) 三者组合决定，分为高(H)、中(M)、低(L)三级：
- **H（高）**：必须采取改进措施。典型组合：S≥7 且 O≥4；或 S≥5 且 O≥5 且 D≥5
- **M（中）**：建议采取改进措施。典型组合：S≥4 且 O≥3 且 D≥4；或其他中等风险组合
- **L（低）**：可接受，无需额外措施

注意：AI-AP 不完全等同于 RPN 排序。即使 RPN 较低，若 S 很高（≥7），AI-AP 仍可能为 H。
"""
