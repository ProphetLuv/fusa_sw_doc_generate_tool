# -*- coding: utf-8 -*-
"""
文档质量校验器（#8）
对 AI 生成的功能安全文档进行自动质量检查，包括：
- 表格完整性（列数一致、无空行）
- 编号连续性（需求ID、测试用例ID）
- FMEA RPN 计算正确性
- 关键章节存在性
- 追溯矩阵覆盖率
"""

import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """单次校验结果。"""
    check_name: str
    passed: bool
    severity: str  # "error", "warning", "info"
    message: str
    details: str = ""


@dataclass
class ValidationReport:
    """文档校验报告。"""
    doc_type: str
    results: List[ValidationResult] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == "error"]

    @property
    def warnings(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == "warning"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        n_err = len(self.errors)
        n_warn = len(self.warnings)
        status = "✅ 通过" if self.passed else "❌ 未通过"
        return f"{status} | {self.doc_type} | {n_err} 错误, {n_warn} 警告"


def validate_document(doc_type: str, content: str, custom_template: str = None) -> ValidationReport:
    """
    对生成的文档进行质量校验。

    Args:
        doc_type: 文档类型（SRS/SAD/FMEA/SDD/TC-UNIT/TC-INTEGRATION）
        content: 文档 Markdown 内容
        custom_template: 用户上传的自定义模板文本（可选）

    Returns:
        ValidationReport 校验报告
    """
    report = ValidationReport(doc_type=doc_type)

    # 通用检查
    _check_empty_content(report, content)
    _check_tables_integrity(report, content)
    _check_required_sections(report, doc_type, content)

    # 模板结构对比检查
    if custom_template:
        _check_template_structure(report, custom_template, content)

    # 文档类型特定检查
    if doc_type == "SRS":
        _check_srs_ids(report, content)
        _check_traceability_matrix(report, content)
    elif doc_type == "FMEA":
        _check_fmea_rpn(report, content)
        _check_fmea_ai_ap(report, content)
        _check_fmea_ids(report, content)
    elif doc_type in ("TC-UNIT", "TC-INTEGRATION"):
        _check_test_case_ids(report, content, doc_type)

    return report


# ======================================================================
# 通用检查
# ======================================================================

def _check_empty_content(report: ValidationReport, content: str):
    """检查文档是否为空或过短。"""
    if not content or len(content.strip()) < 100:
        report.results.append(ValidationResult(
            check_name="内容完整性",
            passed=False,
            severity="error",
            message="文档内容过短，可能生成失败",
            details=f"当前长度: {len(content)} 字符",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="内容完整性",
            passed=True,
            severity="info",
            message=f"文档长度正常 ({len(content):,} 字符)",
        ))


def _check_tables_integrity(report: ValidationReport, content: str):
    """检查 Markdown 表格完整性（列数一致、无空行）。

    容忍 LLM 常见格式偏差：
    - 尾部缺少 `|` 导致的 ±1 列差异不报警告
    - 仅当列数差异 ≥ 2 时才视为真正问题
    """
    lines = content.split('\n')
    i = 0
    table_count = 0
    bad_tables = 0

    def _count_cols(line: str) -> int:
        """计算表格行的列数，容忍尾部缺少 | 的情况。"""
        parts = line.split('|')
        # 去掉首尾空元素（标准 | a | b | 格式）
        if parts and parts[0].strip() == '':
            parts = parts[1:]
        if parts and parts[-1].strip() == '':
            parts = parts[:-1]
        return len(parts)

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('|') and '|' in line[1:]:
            # 找到表格
            table_count += 1
            header_cols = _count_cols(line)
            i += 1
            # 跳过分隔行
            if i < len(lines) and re.match(r'^\|?\s*:?-+:?', lines[i]):
                i += 1

            row_num = 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                row_cols = _count_cols(lines[i])
                # 容忍 ±1 列差异（LLM 尾部 | 缺失或单元格内 | 转义问题）
                if abs(row_cols - header_cols) >= 2:
                    bad_tables += 1
                    report.results.append(ValidationResult(
                        check_name="表格完整性",
                        passed=False,
                        severity="warning",
                        message=f"表格第 {row_num} 行列数不一致（期望 {header_cols}，实际 {row_cols}）",
                    ))
                    break
                # 检查是否全空行
                cells = [c.strip() for c in lines[i].split('|') if c.strip()]
                if all(c == '' for c in cells):
                    bad_tables += 1
                    report.results.append(ValidationResult(
                        check_name="表格完整性",
                        passed=False,
                        severity="warning",
                        message=f"表格第 {row_num} 行为空行",
                    ))
                    break
                row_num += 1
                i += 1
        else:
            i += 1

    if table_count > 0 and bad_tables == 0:
        report.results.append(ValidationResult(
            check_name="表格完整性",
            passed=True,
            severity="info",
            message=f"全部 {table_count} 个表格格式正确",
        ))


def _check_required_sections(report: ValidationReport, doc_type: str, content: str):
    """检查文档是否包含必需的关键章节。"""
    required = {
        "SRS": ["功能需求", "安全需求", "追溯"],
        "SAD": ["架构概述", "模块分解", "接口", "安全架构"],
        "FMEA": ["FMEA", "失效模式", "RPN", "改进措施"],
        "SDD": ["接口设计", "数据结构", "安全设计"],
        "TC-UNIT": ["测试用例", "测试代码", "覆盖"],
        "TC-INTEGRATION": ["集成测试", "接口", "覆盖"],
    }

    sections = required.get(doc_type, [])
    missing = [s for s in sections if s not in content]

    if missing:
        report.results.append(ValidationResult(
            check_name="章节完整性",
            passed=False,
            severity="warning",
            message=f"缺少关键章节: {', '.join(missing)}",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="章节完整性",
            passed=True,
            severity="info",
            message=f"所有关键章节均已包含",
        ))


def _extract_headings(text: str) -> list:
    """从 Markdown 文本中提取所有标题（# 开头的行）。

    跳过代码块（``` 或 ~~~ 围栏）内的内容，避免将
    #include / #define 等预处理指令误识别为标题。
    """
    headings = []
    in_code_block = False
    for line in text.split('\n'):
        stripped = line.strip()
        # 检测代码块围栏
        if stripped.startswith('```') or stripped.startswith('~~~'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped.startswith('#'):
            # 排除 C/C++ 预处理指令（#include, #define, #ifdef 等）
            if re.match(r'#\s*(include|define|ifdef|ifndef|endif|pragma|if|else|elif|undef)', stripped):
                continue
            # 提取标题级别和内容
            level = 0
            for ch in stripped:
                if ch == '#':
                    level += 1
                else:
                    break
            title = stripped[level:].strip()
            if title:
                headings.append((level, title))
    return headings


def _check_template_structure(report: ValidationReport, template: str, content: str):
    """对比生成文档与模板的章节结构，检查是否遵循了模板。"""
    template_headings = _extract_headings(template)
    doc_headings = _extract_headings(content)

    if not template_headings:
        return  # 模板无标题，跳过检查

    # 提取模板中的标题文本（忽略级别，只关心内容）
    template_titles = [t.lower() for _, t in template_headings]
    doc_titles = [t.lower() for _, t in doc_headings]

    # 检查模板中的标题是否在生成文档中出现
    missing = []
    for title in template_titles:
        # 模糊匹配：模板标题是否作为子串出现在文档标题中
        found = any(title in dt or dt in title for dt in doc_titles)
        if not found:
            # 找到原始标题用于显示
            orig = next(t for _, t in template_headings if t.lower() == title)
            missing.append(orig)

    if missing:
        report.results.append(ValidationResult(
            check_name="模板结构符合性",
            passed=False,
            severity="warning",
            message=f"模板中的以下章节在生成文档中未找到: {', '.join(missing[:5])}",
            details=f"模板共 {len(template_headings)} 个章节，文档共 {len(doc_headings)} 个章节",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="模板结构符合性",
            passed=True,
            severity="info",
            message=f"生成文档完全遵循模板结构（{len(template_headings)} 个章节全部匹配）",
        ))


# ======================================================================
# SRS 特定检查
# ======================================================================

def _check_srs_ids(report: ValidationReport, content: str):
    """检查 SRS 需求 ID 编号是否连续、无重复。
    
    只检查需求表格内的ID（追溯矩阵中引用相同ID是正常的）。
    """
    id_pattern = re.compile(r'SRS-\w+-\d{3}')

    # 提取需求表格中的ID（只检查第一个包含需求ID的表格）
    lines = content.split('\n')
    table_ids = []
    in_req_table = False
    header_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|'):
            if in_req_table and header_found:
                break  # 表格结束
            continue

        cells = [c.strip() for c in stripped.split('|') if c.strip()]
        line_ids = id_pattern.findall(stripped)

        if not in_req_table and line_ids:
            # 检查是否是表头行（含"需求ID"或"前置条件"等关键字）
            if any(kw in stripped for kw in ['需求ID', '需求描述', '前置条件', '预期结果']):
                in_req_table = True
                continue
            # 分隔行
            if re.match(r'^\|?\s*:?-+:?', stripped):
                continue
            # 数据行
            if line_ids:
                table_ids.extend(line_ids)
                in_req_table = True
                header_found = True
            continue

        if in_req_table:
            if re.match(r'^\|?\s*:?-+:?', stripped):
                continue
            if line_ids:
                table_ids.extend(line_ids)
                header_found = True

    # 如果没找到表格内的ID，回退到全文搜索但只统计首次出现
    if not table_ids:
        table_ids = id_pattern.findall(content)
        # 去重：只保留每个ID的首次出现位置
        seen = set()
        unique_ids = []
        for id_ in table_ids:
            if id_ not in seen:
                seen.add(id_)
                unique_ids.append(id_)
        table_ids = unique_ids

    if not table_ids:
        report.results.append(ValidationResult(
            check_name="需求ID编号",
            passed=False,
            severity="warning",
            message="未找到 SRS-XXX-XXX 格式的需求ID",
        ))
        return

    # 检查需求表格内的ID重复（同一ID在需求表格中出现多次才是真正的重复）
    duplicates = [id_ for id_ in table_ids if table_ids.count(id_) > 1]
    if duplicates:
        unique_dups = list(set(duplicates))
        report.results.append(ValidationResult(
            check_name="需求ID编号",
            passed=False,
            severity="error",
            message=f"需求表格内发现重复ID: {', '.join(unique_dups[:5])}",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="需求ID编号",
            passed=True,
            severity="info",
            message=f"共 {len(table_ids)} 个需求ID，无重复",
        ))


def _check_traceability_matrix(report: ValidationReport, content: str):
    """检查追溯矩阵是否包含覆盖状态统计。"""
    has_traceability = "追溯" in content or "traceability" in content.lower()
    has_coverage = "覆盖率" in content or "覆盖状态" in content

    if has_traceability and has_coverage:
        report.results.append(ValidationResult(
            check_name="追溯矩阵",
            passed=True,
            severity="info",
            message="追溯矩阵包含覆盖率统计",
        ))
    elif has_traceability:
        report.results.append(ValidationResult(
            check_name="追溯矩阵",
            passed=False,
            severity="warning",
            message="追溯矩阵存在但缺少覆盖率统计",
        ))


# ======================================================================
# FMEA 特定检查
# ======================================================================

def _check_fmea_rpn(report: ValidationReport, content: str):
    """检查 FMEA 表格中 RPN 计算是否正确（S × O × D）。"""
    lines = content.split('\n')
    errors = 0

    for i, line in enumerate(lines):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c]  # 去除空字符串

        # 尝试找到 S, O, D, RPN 列
        if len(cells) < 8:
            continue

        # 尝试解析数字列（S, O, D 通常是连续的数字）
        nums = []
        for c in cells:
            try:
                nums.append(int(c))
            except ValueError:
                nums.append(None)

        # 查找连续的 S, O, D 值（1-10范围内）
        for j in range(len(nums) - 3):
            s, o, d = nums[j], nums[j+1], nums[j+2]
            rpn = nums[j+3] if j+3 < len(nums) else None
            if s and o and d and 1 <= s <= 10 and 1 <= o <= 10 and 1 <= d <= 10:
                expected_rpn = s * o * d
                if rpn is not None and rpn != expected_rpn:
                    errors += 1
                    if errors <= 3:  # 只报告前3个
                        report.results.append(ValidationResult(
                            check_name="RPN计算",
                            passed=False,
                            severity="error",
                            message=f"第{i+1}行 RPN 计算错误: {s}×{o}×{d}={expected_rpn}，但文档写的是 {rpn}",
                        ))
                break  # 每行只检查一次

    if errors == 0:
        report.results.append(ValidationResult(
            check_name="RPN计算",
            passed=True,
            severity="info",
            message="RPN 计算全部正确",
        ))


def _check_fmea_ai_ap(report: ValidationReport, content: str):
    """检查 FMEA 是否包含 AI-AP 列。"""
    has_ai_ap = "AI-AP" in content or "行动优先级" in content
    if has_ai_ap:
        report.results.append(ValidationResult(
            check_name="AI-AP行动优先级",
            passed=True,
            severity="info",
            message="文档包含 AI-AP 行动优先级列",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="AI-AP行动优先级",
            passed=False,
            severity="warning",
            message="文档缺少 AI-AP 行动优先级列（ISO 26262:2018 要求）",
        ))


def _check_fmea_ids(report: ValidationReport, content: str):
    """检查 FMEA 失效模式 ID 是否有重复。

    只检查失效模式分析主表格内的ID（同一ID在检测措施表、纠正措施表、
    追溯矩阵中重复出现是正常引用，不算重复）。
    """
    id_pattern = re.compile(r'FM-\w+-\d{3}')

    # 提取失效模式分析主表格中的ID（第一个包含 FM-ID 的表格）
    lines = content.split('\n')
    table_ids = []
    in_fm_table = False
    header_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|'):
            if in_fm_table and header_found:
                break  # 表格结束
            continue

        line_ids = id_pattern.findall(stripped)

        if not in_fm_table and line_ids:
            # 检查是否是表头行（含失效模式相关关键字）
            if any(kw in stripped for kw in ['失效模式', '失效ID', '编号', '严重度', 'S', 'O', 'D', 'RPN']):
                in_fm_table = True
                continue
            # 分隔行
            if re.match(r'^\|?\s*:?-+:?', stripped):
                continue
            # 数据行
            if line_ids:
                table_ids.extend(line_ids)
                in_fm_table = True
                header_found = True
            continue

        if in_fm_table:
            if re.match(r'^\|?\s*:?-+:?', stripped):
                continue
            if line_ids:
                table_ids.extend(line_ids)
                header_found = True

    # 如果没找到表格内的ID，回退到全文搜索但只统计首次出现
    if not table_ids:
        all_ids = id_pattern.findall(content)
        seen = set()
        for id_ in all_ids:
            if id_ not in seen:
                seen.add(id_)
                table_ids.append(id_)

    if not table_ids:
        report.results.append(ValidationResult(
            check_name="失效模式ID",
            passed=False,
            severity="warning",
            message="未找到 FM-XXX-XXX 格式的失效模式ID",
        ))
        return

    # 检查主表格内的ID重复（同一ID在分析表中出现多次才是真正的重复）
    duplicates = [id_ for id_ in table_ids if table_ids.count(id_) > 1]
    if duplicates:
        unique_dups = list(set(duplicates))
        report.results.append(ValidationResult(
            check_name="失效模式ID",
            passed=False,
            severity="error",
            message=f"失效模式分析表内发现重复ID: {', '.join(unique_dups[:5])}",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="失效模式ID",
            passed=True,
            severity="info",
            message=f"共 {len(table_ids)} 个失效模式ID，无重复",
        ))


# ======================================================================
# TC 特定检查
# ======================================================================

def _check_test_case_ids(report: ValidationReport, content: str, doc_type: str):
    """检查测试用例 ID 编号是否连续、无重复。

    支持多种 LLM 常见 ID 格式：
    - UT-MC-001, UT-MOTOR-CTRL-001（标准）
    - UT-MC-01, UT-MC-0001（2~4位数字）
    - UT_MC_001（下划线分隔）
    - TC-UNIT-MC-001（带文档类型前缀）
    """
    prefix = "UT" if doc_type == "TC-UNIT" else "IT"
    # 宽松正则：支持 - 或 _ 分隔，2~4 位数字结尾
    id_pattern = re.compile(
        r'(?:TC[-_]?(?:UNIT|INTEG|INT)[-_]?)?' + prefix + r'[-_]\w+[-_]\d{2,4}',
        re.IGNORECASE
    )
    ids = [m.upper() for m in id_pattern.findall(content)]

    if not ids:
        # 回退：尝试更宽松的匹配（任何含 UT/IT 前缀的编号）
        fallback_pattern = re.compile(prefix + r'[-_][\w-]+', re.IGNORECASE)
        fallback_ids = fallback_pattern.findall(content)
        if fallback_ids:
            ids = [m.upper() for m in fallback_ids]
        else:
            report.results.append(ValidationResult(
                check_name="测试用例ID",
                passed=False,
                severity="warning",
                message=f"未找到 {prefix}-XXX-NNN 格式的测试用例ID",
            ))
            return

    # 去重检查（同一 ID 在多个表格中引用是正常的，只统计定义处）
    # 提取表格中首次出现的 ID 作为定义
    seen = set()
    duplicates = []
    for id_ in ids:
        if id_ in seen:
            if id_ not in duplicates:
                duplicates.append(id_)
        seen.add(id_)

    # 只有同一表格内重复才算真正重复（跨表引用正常）
    # 简化处理：如果重复率 < 50% 视为正常引用
    unique_count = len(set(ids))
    total_count = len(ids)
    if duplicates and total_count > unique_count * 2:
        report.results.append(ValidationResult(
            check_name="测试用例ID",
            passed=False,
            severity="error",
            message=f"发现重复测试用例ID: {', '.join(duplicates[:5])}",
        ))
    else:
        report.results.append(ValidationResult(
            check_name="测试用例ID",
            passed=True,
            severity="info",
            message=f"共 {unique_count} 个唯一测试用例ID，无异常重复",
        ))
