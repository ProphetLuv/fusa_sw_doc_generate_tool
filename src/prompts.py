# -*- coding: utf-8 -*-
"""
六种功能安全文档类型的专业 Prompt 模板
- SRS            : 软件需求规格说明（Software Requirements Specification）
- SAD            : 软件架构设计（Software Architecture Design）
- FMEA           : 失效模式与影响分析（Failure Mode and Effects Analysis）
- SDD            : 软件详细设计（Software Detailed Design）
- TC-UNIT        : 单元测试用例（Unit Test Cases）
- TC-INTEGRATION : 集成测试用例（Integration Test Cases）

特性：
- ASIL 等级差异化要求（#1）
- FMEA 支持 AI-AP 行动优先级（#2）
- 双向追溯矩阵增强（#4）
- SWE.4 软件单元验证输出（#5）
"""

from typing import Dict, Any, Optional


# ASIL 等级对应的 ISO 26262 Part 6 方法要求
_ASIL_REQUIREMENTS = {
    "QM": (
        "- 无特殊功能安全要求，按常规软件工程实践即可\n"
        "- 建议遵循基本编码规范，但不强制 MISRA C 合规"
    ),
    "ASIL A": (
        "- 需要结构化分析（SAD/SDD）\n"
        "- 单元测试建议达到语句覆盖率 ≥ 80%\n"
        "- 建议遵循 MISRA C:2012 规则，偏差需记录\n"
        "- 需要基本的故障检测机制"
    ),
    "ASIL B": (
        "- 需要完整的 SRS/SAD/SDD 文档链\n"
        "- 单元测试需达到分支覆盖率 ≥ 80%\n"
        "- 必须遵循 MISRA C:2012 规则，偏差需论证\n"
        "- 需要 FMEA 分析覆盖所有安全相关功能\n"
        "- 需要看门狗、CRC 等基本安全机制"
    ),
    "ASIL C": (
        "- 需要完整的文档链 + 双向追溯矩阵\n"
        "- 单元测试需达到分支覆盖率 ≥ 90%\n"
        "- 必须遵循 MISRA C:2012 规则，零偏差容忍\n"
        "- 需要 FMEA + FTA 组合分析\n"
        "- 需要冗余设计或多样性设计\n"
        "- 需要独立的代码审查和静态分析"
    ),
    "ASIL D": (
        "- 需要完整的文档链 + 双向追溯矩阵（需求↔设计↔代码测试）\n"
        "- 单元测试需达到 MC/DC 覆盖率 ≥ 90%\n"
        "- 必须遵循 MISRA C:2012 规则，零偏差容忍\n"
        "- 需要 FMEA + FTA + DFA 组合分析\n"
        "- 需要软件多样性或硬件冗余\n"
        "- 需要独立的验证和确认（V&V）\n"
        "- 需要 WCET 分析和栈使用分析\n"
        "- 需要防御性编程和故障注入测试"
    ),
}


def _get_asil_requirements(asil_level: str) -> str:
    """获取 ASIL 等级对应的 ISO 26262 方法要求文本。"""
    return _ASIL_REQUIREMENTS.get(asil_level, _ASIL_REQUIREMENTS["ASIL B"])


# ASIL 等级对应的覆盖率要求（用于 TC-UNIT）
_Asil_COVERAGE = {
    "QM":    "语句覆盖率（无硬性指标）",
    "ASIL A": "语句覆盖率 ≥ 80%",
    "ASIL B": "分支覆盖率 ≥ 80%",
    "ASIL C": "分支覆盖率 ≥ 90%",
    "ASIL D": "MC/DC 覆盖率 ≥ 90%",
}


def _get_asil_coverage(asil_level: str) -> str:
    return _Asil_COVERAGE.get(asil_level, _Asil_COVERAGE["ASIL B"])


# AI-AP 判定表说明（ISO 26262:2018 Part 3）
_AI_AP_TABLE = """
**AI-AP（行动优先级）判定规则**（依据 ISO 26262:2018 Part 3）：

AI-AP 由严重度(S)、发生度(O)、检测度(D) 三者组合决定，分为高(H)、中(M)、低(L)三级：
- **H（高）**：必须采取改进措施。典型组合：S≥7 且 O≥4；或 S≥5 且 O≥5 且 D≥5
- **M（中）**：建议采取改进措施。典型组合：S≥4 且 O≥3 且 D≥4；或其他中等风险组合
- **L（低）**：可接受，无需额外措施

注意：AI-AP 不完全等同于 RPN 排序。即使 RPN 较低，若 S 很高（≥7），AI-AP 仍可能为 H。
"""


class PromptManager:
    """
    Prompt 管理器，根据文档类型分发到对应的专业 Prompt 模板。
    """

    DOC_TYPES = ("SRS", "SAD", "FMEA", "SDD", "TC-UNIT", "TC-INTEGRATION")

    def get_prompt(
        self,
        doc_type: str,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        custom_template: Optional[str] = None,
    ) -> str:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")

        dispatch = {
            "SRS": self._build_srs_prompt,
            "SAD": self._build_sad_prompt,
            "FMEA": self._build_fmea_prompt,
            "SDD": self._build_sdd_prompt,
            "TC-UNIT": self._build_tc_unit_prompt,
            "TC-INTEGRATION": self._build_tc_integration_prompt,
        }

        builder = dispatch.get(doc_type.upper())
        if not builder:
            raise ValueError(f"不支持的文档类型: {doc_type}，可选: {self.DOC_TYPES}")

        prompt = builder(code, module_name, asil_level)

        prior_docs = ctx.get("prior_docs")
        if prior_docs:
            prompt = self._inject_prior_docs(prompt, prior_docs)

        if custom_template:
            prompt = self._apply_custom_template(prompt, custom_template)

        return prompt

    def _apply_custom_template(self, base_prompt: str, template: str) -> str:
        template_instruction = f"""

## ⚠️ 重要：自定义输出格式要求

用户提供了自定义文档模板，请**严格按照以下模板的格式和结构**输出文档。
模板中定义的章节标题、表格列名、字段顺序、命名规范等必须严格遵守。
如果模板与上方的默认格式要求有冲突，以模板为准。

### 用户自定义模板内容

```
{template}
```

请确保生成的文档完全匹配上述模板的结构和格式要求。
"""
        return base_prompt + template_instruction

    def _inject_prior_docs(self, base_prompt: str, prior_docs: Dict[str, str]) -> str:
        sections = []
        for doc_type, content in prior_docs.items():
            if content:
                sections.append(f"### 已生成的 {doc_type} 文档（作为分析参考）\n\n{content}\n")

        if not sections:
            return base_prompt

        prior_section = "\n\n##  前置参考文档\n\n以下是已生成的前置文档，请在分析时充分参考这些文档中的信息：\n\n" + "\n".join(sections)
        return base_prompt + prior_section

    # ------------------------------------------------------------------
    # SRS - 软件需求规格说明（#1 ASIL差异化 + #4 追溯矩阵增强）
    # ------------------------------------------------------------------

    def _build_srs_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        safety_extra = ""
        if asil_level not in ("QM", "ASIL A"):
            safety_extra = f"""
对于 **{asil_level}** 等级，安全需求必须包含：
- 故障检测与诊断机制（具体检测方法和响应时间要求）
- 安全状态定义和转换条件（明确定义每个安全状态及触发条件）
- 降级/容错策略（多级降级路径）
- 硬件-软件安全接口要求（HSI）"""

        nonfunc_extra = ""
        if asil_level not in ("QM", "ASIL A"):
            nonfunc_extra = f"""
对于 **{asil_level}** 等级，非功能需求必须明确列出：
- WCET（最坏情况执行时间）约束及分析方法
- RAM/ROM 使用上限
- 任务调度时序约束"""

        return f"""你是一名功能安全工程师，请根据以下 C/C++ 嵌入式代码，逆向提取并撰写符合 ISO 26262 / ASPICE 标准的**软件需求规格说明书（SRS）**。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的 SRS 文档：

# {module_name} 软件需求规格说明书（SRS）

## 1. 概述
简要描述模块的功能、用途和在系统中的角色。

## 2. 功能需求

以表格形式列出每条需求：

| 需求ID | 前置条件 | 需求描述 | 预期结果 | 需求类型 | ASIL等级 | 验证方法 | 追溯代码 |
|--------|----------|----------|----------|----------|----------|----------|----------|

要求：
- **需求ID**：格式为 SRS-MOD-XXX（MOD为模块缩写，XXX为三位序号，从001开始连续编号）
- **【强制约束】每个需求ID必须全局唯一，严禁重复！** 每写一条需求前，先检查该ID是否已在文档中出现过。如果已存在则使用下一个序号。全文不得有任何两个相同的需求ID。
- **前置条件**：描述触发该需求的前提状态或输入条件（如“当电机处于 RUNNING 状态时”、“当检测到过流信号时”）
- **需求描述**：使用“系统 shall …”句式，描述系统/模块应执行的动作
- **预期结果**：描述执行后应得到的具体可验证结果（如“PWM占空比降为0，电机进入制动状态”）
- 完整格式示例：“当[前置条件]满足时，[系统] shall 执行[动作]，得到[预期结果]”
- **需求类型**：功能需求 / 性能需求 / 接口需求 / 安全需求 / 可靠性需求
- **ASIL等级**：{asil_level}（可根据安全相关性调整子需求的等级）
- **验证方法**：测试 / 分析 / 检查 / 演示
- **追溯代码**：对应到具体的函数名或代码行

## 3. 非功能需求
包括性能约束、可靠性要求、可维护性要求等。
{nonfunc_extra}

## 4. 接口需求
描述模块与外部的接口（硬件接口、软件接口、通信协议等），以表格形式列出。

## 5. 安全需求
与功能安全相关的特殊需求，包括故障检测、安全状态转换、降级策略等。
{safety_extra}

## 6. 双向追溯矩阵（增强版）

需求与代码函数、测试用例的完整追溯链，格式如下：

| 需求ID | 需求描述 | 对应函数 | 对应测试用例ID | 覆盖状态 |
|--------|----------|----------|---------------|----------|

要求：
- 每条需求必须追溯到至少一个代码函数
- 每个安全相关函数必须有对应的测试用例ID（格式 UT-MOD-XXX）
- 覆盖状态：✅已覆盖 / ⚠️部分覆盖 / 未覆盖
- 在表格末尾添加**追溯覆盖率统计**：已覆盖需求数 / 总需求数 = 覆盖率%
- 标注所有 ❌未覆盖 的需求，说明原因和风险分析

请确保需求覆盖代码中的所有关键逻辑，不遗漏任何重要的功能点和安全机制。

【输出前自检清单】
1. 所有需求ID是否唯一？（逐个检查，无重复）
2. 编号是否从001开始连续递增？
3. 追溯矩阵中的ID是否与需求表中的ID完全一致？"""

    # ------------------------------------------------------------------
    # SAD - 软件架构设计文档（#1 ASIL差异化）
    # ------------------------------------------------------------------

    def _build_sad_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        safety_extra = ""
        if asil_level in ("ASIL C", "ASIL D"):
            safety_extra = """
### 10.4 多样性与冗余设计（ASIL C/D 必需）
- 软件多样性策略（不同算法实现同一功能）
- 硬件冗余方案（如适用）
- 投票/比较机制设计"""

        return f"""你是一名功能安全工程师，请根据以下 C/C++ 嵌入式代码，撰写符合 ISO 26262 / ASPICE 标准的**软件架构设计文档（SAD）**。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的 SAD 文档：

# {module_name} 软件架构设计文档（SAD）

## 1. 架构概述
描述软件整体架构风格（分层架构/组件架构/事件驱动等）、设计原则、架构约束。

## 2. 系统上下文图
使用 Mermaid 绘制系统与外部实体的交互关系。

## 3. 模块分解
### 3.1 模块列表
| 模块ID | 模块名称 | 职责描述 | 关键函数 | ASIL等级 |
|--------|---------|---------|---------|---------|

### 3.2 模块层次结构图
使用 Mermaid 绘制模块间的层次关系和依赖。

### 3.3 模块详细设计
对每个模块描述其职责、接口、依赖关系和约束。

## 4. 组件接口规格
### 4.1 内部接口（模块间）
| 接口ID | 提供方模块 | 消费方模块 | 接口类型 | 数据格式 | 触发条件 | 安全约束 |
|--------|-----------|-----------|---------|---------|---------|---------|

### 4.2 外部接口（与硬件/其他系统）
| 接口ID | 方向 | 协议 | 数据格式 | 速率 | 安全机制 |
|--------|------|------|---------|------|---------|

## 5. 数据流架构
使用 Mermaid 绘制数据在模块间的流转路径，标注数据变换和缓存点。

## 6. 硬件-软件映射
| 软件组件 | 硬件资源 | 资源类型 | 容量需求 | 说明 |
|---------|---------|---------|---------|------|

## 7. 通信架构
描述模块间的通信机制（函数调用、消息队列、共享内存、CAN/SPI/I2C 等）。

## 8. 中断与任务调度
| 任务/中断 | 优先级 | 周期 | 所属模块 | 最大执行时间 | 安全关键 |
|----------|--------|------|---------|------------|---------|

## 9. 内存架构
描述代码段、数据段、堆栈的分配策略和保护机制。

## 10. 安全架构
### 10.1 故障检测机制
看门狗、ECC、CRC、心跳监测等。
### 10.2 安全状态转换
使用 Mermaid 状态图描述正常→降级→安全状态的转换路径。
### 10.3 冗余设计
软件多样性、N版本编程、投票机制等（如适用）。
{safety_extra}

## 11. 架构决策记录（ADR）
记录关键架构决策及其理由和替代方案。

请确保架构文档与代码实现严格对应，每个架构元素都能追溯到具体代码模块。"""

    # ------------------------------------------------------------------
    # FMEA - 失效模式与影响分析（#1 ASIL差异化 + #2 AI-AP）
    # ------------------------------------------------------------------

    def _build_fmea_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        return f"""你是一名功能安全工程师，请根据以下 C/C++ 嵌入式代码，执行完整的**失效模式与影响分析（FMEA）**，符合 ISO 26262 Part 6/Part 9 和 IEC 61508 标准。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的 FMEA 报告：

# {module_name} 失效模式与影响分析（FMEA）

## 1. 分析范围与方法
简述分析覆盖范围、使用标准（ISO 26262:2018 / IEC 61508）、分析假设。

## 2. FMEA 分析表

请覆盖以下五个失效维度，为每个维度生成详细的失效模式分析：

### 2.1 变量级失效分析
覆盖全局变量、局部变量、静态变量的失效（溢出、下溢、未初始化、数据损坏、符号错误等）。

### 2.2 函数级失效分析
覆盖函数返回值错误、函数未执行、函数执行时序错误、无限循环、栈溢出等。

### 2.3 接口级失效分析
覆盖参数传递错误、接口协议违反、数据格式不匹配、通信超时等。

### 2.4 逻辑级失效分析
覆盖条件判断错误、分支遗漏、状态机死锁、竞争条件、优先级反转等。

### 2.5 资源级失效分析
覆盖内存泄漏、缓冲区溢出、堆栈溢出、外设寄存器访问异常、中断冲突等。

每个维度的 FMEA 表格格式如下：

| 失效模式ID | 失效模式 | 失效原因 | 失效影响 | 严重度(S) | 发生度(O) | 检测度(D) | RPN | AI-AP | 现有控制措施 | 建议改进措施 |
|-----------|----------|----------|----------|-----------|-----------|-----------|-----|-------|------------|------------|

评分标准：
- **严重度(S)**：1-10（10=灾难性安全影响，1=无影响）
- **发生度(O)**：1-10（10=极可能发生，1=几乎不可能）
- **检测度(D)**：1-10（10=完全无法检测，1=必定能检测到）
- **RPN** = S × O × D
{_AI_AP_TABLE}

## 3. 高风险失效模式汇总
列出 AI-AP 为 H（高）以及 RPN ≥ 100 的失效模式，按 AI-AP 优先、RPN 降序排列。

## 4. 改进措施建议
针对高风险失效模式提出具体的改进措施建议，包括：
- 设计改进（算法/架构层面）
- 检测机制增强（运行时监控、自检）
- 每项措施需标注预期降低的 S/O/D 值和改进后的 AI-AP

请确保分析全面、深入，不遗漏任何潜在的失效模式。"""

    # ------------------------------------------------------------------
    # SDD - 软件详细设计（#1 ASIL差异化）
    # ------------------------------------------------------------------

    def _build_sdd_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        wcet_extra = ""
        if asil_level in ("ASIL C", "ASIL D"):
            wcet_extra = """
| WCET分析方法 | 使用的分析工具/方法（静态分析/测量法） |
| 栈使用分析 | 最坏情况栈深度估算方法及结果 |"""

        return f"""你是一名功能安全工程师，请根据以下 C/C++ 嵌入式代码，撰写符合 ISO 26262 / ASPICE 标准的**软件详细设计文档（SDD）**。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的 SDD 文档：

# {module_name} 软件详细设计文档（SDD）

## 1. 设计概述
模块架构概览、设计约束、与其他模块的关系。

## 2. 接口设计

### 2.1 函数接口详细设计

对代码中的每个函数，按以下格式描述：

#### 函数名: `function_name`

| 属性 | 描述 |
|------|------|
| 函数签名 | 完整签名 |
| 功能描述 | 函数功能说明 |
| 前置条件 | 调用前必须满足的条件 |
| 后置条件 | 调用后保证的状态 |
| 输入参数 | 参数名、类型、范围、含义 |
| 输出参数 | 参数名、类型、范围、含义 |
| 返回值 | 返回值类型及含义 |
| WCET | 最坏情况执行时间估算 |
| 线程安全 | 是否线程安全及原因 |
| 可重入性 | 是否可重入及原因 |
| 副作用 | 对全局状态的影响 |
| 错误处理 | 异常情况处理方式 |
{wcet_extra}

### 2.2 外部接口
硬件寄存器访问、外设通信接口、OS/RTOS 接口等。

## 3. 状态机设计
如果代码中包含状态机逻辑，请绘制状态转换表和状态转换图（Mermaid 格式）。

| 当前状态 | 触发事件 | 转换动作 | 下一状态 | 条件 |
|---------|---------|---------|---------|------|

## 4. 数据流设计
描述数据在模块内部的流转路径，包括数据变换、缓存、过滤等。

## 5. 数据结构设计
列出所有关键数据结构（struct、enum、union），说明每个字段的用途和取值范围。

## 6. 算法设计
对核心算法进行描述，包括算法逻辑、复杂度分析、边界条件处理。

## 7. 资源使用
| 资源类型 | 使用量估算 | 说明 |
|---------|-----------|------|
| ROM (代码段) | | |
| RAM (数据段) | | |
| 栈空间 | | |
| 外设 | | |
| 中断 | | |

## 8. 安全设计
防御性编程措施、故障检测机制、安全状态转换策略。

## 9. MISRA C 合规性说明
列出代码中已遵循的 MISRA C:2012 规则，以及任何偏差项和论证理由。

请确保设计文档与代码实现严格对应，每个设计元素都能追溯到具体代码。"""

    # ------------------------------------------------------------------
    # TC-UNIT - 单元测试用例（#1 ASIL差异化 + #5 SWE.4 增强）
    # ------------------------------------------------------------------

    def _build_tc_unit_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        coverage_req = _get_asil_coverage(asil_level)
        return f"""你是一名功能安全测试工程师，请根据以下 C/C++ 嵌入式代码，设计完整的**单元测试用例文档（TC-UNIT）**，符合 ISO 26262 Part 6 软件单元测试要求和 ASPICE SWE.4 单元测试规范。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的单元测试用例文档：

# {module_name} 单元测试用例文档（TC-UNIT）

## 1. 测试策略
简述单元测试方法、覆盖目标、测试环境假设（含 Mock/Stub 策略）。
- **覆盖率目标**：{coverage_req}
- **测试框架**：Unity (C) / Google Test (C++)

## 2. 单元测试用例表

请使用以下五类测试设计技术，为代码中的每个函数设计单元测试用例：

### 2.1 等价类划分测试
针对输入参数的有效等价类和无效等价类设计用例。

### 2.2 边界值分析测试
针对参数取值边界（最小值、最小值+1、最大值-1、最大值、越界值）设计用例。

### 2.3 错误猜测测试
基于经验猜测可能的错误场景（空指针、整数溢出、数组越界、除零等）。

### 2.4 状态转换测试
如果代码包含状态机，设计覆盖所有状态转换路径的测试用例。

### 2.5 安全机制测试
针对故障检测、安全状态转换、看门狗、冗余校验等安全机制设计单元测试。

测试用例表格格式：

| 测试用例ID | 测试技术 | 被测函数 | 测试目的 | 前置条件 | 输入数据 | 预期结果 | 优先级 | 追溯需求 |
|-----------|---------|---------|---------|---------|---------|---------|--------|---------|

要求：
- **测试用例ID**：格式 UT-MOD-XXX（XXX为三位序号，必须连续）
- **优先级**：高(安全相关) / 中(功能正确性) / 低(边界/异常)
- **追溯需求**：关联到 SRS 需求ID（格式 SRS-MOD-XXX）

## 3. 测试规程（Test Procedure）

为每个高优先级测试用例提供详细的执行步骤：

| 步骤编号 | 操作描述 | 预期观察 | 通过准则 |
|---------|---------|---------|---------|

## 4. 单元测试代码

请为关键测试用例生成 Unity（C语言）和 Google Test（C++）两种框架的单元测试代码：

### 4.1 Unity 框架测试代码
```c
#include "unity.h"
// ... 完整的 Unity 单元测试代码，含 setUp/tearDown
```

### 4.2 Google Test 框架测试代码
```cpp
#include <gtest/gtest.h>
// ... 完整的 GTest 单元测试代码
```

## 5. 测试覆盖矩阵
单元测试用例与函数的覆盖矩阵表，标注每个函数被哪些用例覆盖。

## 6. 测试结果记录模板

提供测试结果记录表格，供实际测试执行时填写：

| 测试用例ID | 执行日期 | 执行者 | 实际结果 | 通过/失败 | 备注/缺陷ID |
|-----------|---------|--------|---------|----------|------------|

## 7. 覆盖率分析报告模板

| 覆盖类型 | 目标 | 实际值 | 是否达标 | 未覆盖项说明 |
|---------|------|--------|---------|------------|
| 语句覆盖 | 100% | | | |
| 分支覆盖 | {coverage_req} | | | |
{"| MC/DC覆盖 | ≥90% | | | |" if asil_level == "ASIL D" else ""}

## 8. 测试通过准则
- 所有高优先级用例必须 100% 通过
- 覆盖率必须达到 {coverage_req}
- 所有失败用例必须有对应的缺陷记录和修复计划

请确保单元测试用例全面覆盖代码的所有分支和路径，特别关注安全相关的测试场景。"""

    # ------------------------------------------------------------------
    # TC-INTEGRATION - 集成测试用例（#1 ASIL差异化）
    # ------------------------------------------------------------------

    def _build_tc_integration_prompt(self, code: str, module_name: str, asil_level: str) -> str:
        asil_req = _get_asil_requirements(asil_level)
        return f"""你是一名功能安全测试工程师，请根据以下 C/C++ 嵌入式代码，设计完整的**集成测试用例文档（TC-INTEGRATION）**，符合 ISO 26262 Part 6 软件集成测试要求和 ASPICE SWE.5 集成测试规范。

## 模块名称
{module_name}

## ASIL 等级
{asil_level}

## 本 ASIL 等级的 ISO 26262 Part 6 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 输出格式要求

请按照以下结构输出 Markdown 格式的集成测试用例文档：

# {module_name} 集成测试用例文档（TC-INTEGRATION）

## 1. 集成测试策略
简述集成测试方法（自顶向下 / 自底向上 / 三明治法）、测试环境假设（含硬件在环 HIL / 软件在环 SIL）、Mock/Stub 策略。

## 2. 接口分析
### 2.1 模块内部接口
分析代码中各函数/子模块之间的调用关系和数据流，绘制接口调用图。
### 2.2 外部接口
分析模块与外部系统（驱动层、中间件、总线通信）的接口依赖关系。

## 3. 集成测试用例表

请使用以下测试设计技术设计集成测试用例：

### 3.1 接口调用链测试
### 3.2 数据流集成测试
### 3.3 控制流集成测试
### 3.4 时序与并发测试
### 3.5 故障注入集成测试

测试用例表格格式：

| 测试用例ID | 测试技术 | 被测接口/调用链 | 测试目的 | 前置条件 | 输入数据 | 预期结果 | 优先级 | 追溯需求 |
|-----------|---------|--------------|---------|---------|---------|---------|--------|---------|

要求：
- **测试用例ID**：格式 IT-MOD-XXX（XXX为三位序号，必须连续）
- **优先级**：高(安全相关) / 中(功能正确性) / 低(边界/异常)
- **追溯需求**：关联到 SRS / SAD 需求ID

## 4. 集成测试代码框架
### 4.1 使用 CMock/FFI 的集成测试代码
### 4.2 使用 Google Mock 的集成测试代码

## 5. 测试覆盖矩阵
集成测试用例与接口/调用链的覆盖矩阵表。

## 6. 测试结果记录模板

| 测试用例ID | 执行日期 | 执行者 | 实际结果 | 通过/失败 | 备注/缺陷ID |
|-----------|---------|--------|---------|----------|------------|

## 7. 测试通过准则
各 ASIL 等级对应的集成测试覆盖率要求、接口覆盖率要求、通过率要求。

请确保集成测试用例全面覆盖模块间的所有接口和关键调用路径，特别关注安全相关的集成场景。"""

    # ------------------------------------------------------------------
    # 分段并发 & 审查修订
    # ------------------------------------------------------------------

    DOC_CHUNKS = {
        "SRS": [
            {"id": 1, "title": "第1~3章", "sections": "1. 引言（目的、范围、术语）、2. 系统概述、3. 功能需求"},
            {"id": 2, "title": "第4~6章", "sections": "4. 非功能需求（性能、安全、可靠性）、5. 接口需求、6. 安全需求"},
            {"id": 3, "title": "第7~9章", "sections": "7. 约束条件、8. 数据需求、9. 外部接口需求"},
        ],
        "SAD": [
            {"id": 1, "title": "第1~3章", "sections": "1. 架构概述、2. 系统上下文图、3. 模块分解"},
            {"id": 2, "title": "第4~6章", "sections": "4. 组件接口规格、5. 数据流架构、6. 硬件-软件映射"},
            {"id": 3, "title": "第7~9章", "sections": "7. 通信架构、8. 中断与任务调度、9. 内存架构"},
        ],
        "FMEA": [
            {"id": 1, "title": "第1~4章", "sections": "1. 文档信息、2. 审批记录、3. 分析范围与目的、4. 风险优先级定义（S/O/D/RPN 准则表）"},
            {"id": 2, "title": "第5章", "sections": "5. 失效模式分析表（核心：逐函数/模块识别失效模式、影响、S/O/D 评分、RPN 计算）"},
            {"id": 3, "title": "第6~8章", "sections": "6. 现有检测与预防措施、7. 建议纠正措施、8. 安全机制覆盖分析"},
            {"id": 4, "title": "第9~10章", "sections": "9. 残余风险评估、10. 追溯矩阵（失效模式→安全需求→测试用例映射）"},
        ],
        "SDD": [
            {"id": 1, "title": "第1~3章", "sections": "1. 设计概述、2. 架构设计、3. 接口设计"},
            {"id": 2, "title": "第4~6章", "sections": "4. 详细设计、5. 数据结构设计、6. 算法设计"},
        ],
        "TC-UNIT": [
            {"id": 1, "title": "第1~3章", "sections": "1. 测试策略、2. 单元测试用例表（等价类/边界值/错误猜测/状态转换/安全机制）、3. 测试规程"},
            {"id": 2, "title": "第4~6章", "sections": "4. 单元测试代码、5. 测试覆盖矩阵、6. 测试结果记录模板"},
            {"id": 3, "title": "第7~8章", "sections": "7. 覆盖率分析报告模板、8. 测试通过准则"},
        ],
        "TC-INTEGRATION": [
            {"id": 1, "title": "第1~3章", "sections": "1. 集成测试策略、2. 接口分析（内部接口/外部接口）、3. 集成测试用例表"},
            {"id": 2, "title": "第4~6章", "sections": "4. 集成测试代码框架、5. 测试覆盖矩阵、6. 测试结果记录模板"},
        ],
    }

    def get_chunk_prompts(
        self,
        doc_type: str,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        custom_template: Optional[str] = None,
    ) -> list:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")

        chunks = self.DOC_CHUNKS.get(doc_type.upper(), [])
        if not chunks:
            full_prompt = self.get_prompt(doc_type, code, context, custom_template)
            return [(doc_type, full_prompt)]

        results = []
        prior_docs = ctx.get("prior_docs")
        for chunk in chunks:
            chunk_prompt = self._build_chunk_prompt(
                doc_type, code, module_name, asil_level,
                chunk["id"], chunk["title"], chunk["sections"],
                total_chunks=len(chunks),
            )
            if prior_docs:
                chunk_prompt = self._inject_prior_docs(chunk_prompt, prior_docs)
            if custom_template:
                chunk_prompt = self._apply_custom_template(chunk_prompt, custom_template)
            results.append((chunk["title"], chunk_prompt))

        return results

    def _build_chunk_prompt(
        self, doc_type: str, code: str, module_name: str, asil_level: str,
        chunk_id: int, chunk_title: str, sections: str, total_chunks: int,
    ) -> str:
        asil_req = _get_asil_requirements(asil_level)
        doc_full_names = {
            "SRS": "软件需求规格说明",
            "SAD": "软件架构设计",
            "FMEA": "失效模式与影响分析",
            "SDD": "软件详细设计",
            "TC-UNIT": "单元测试用例",
            "TC-INTEGRATION": "集成测试用例",
        }
        full_name = doc_full_names.get(doc_type, doc_type)

        return f"""你是一名功能安全工程师。请根据以下 C/C++ 嵌入式代码，撰写符合 ISO 26262 / ASPICE 标准的 **{full_name}文档（{doc_type}）** 中的 **{chunk_title}** 部分。

## 全局上下文
- 模块名称：{module_name}
- ASIL 等级：{asil_level}
- 本文档共分 {total_chunks} 个部分并行生成，你负责第 {chunk_id} 部分：{sections}
- 请只输出你负责的章节内容，不要输出文档标题和其他章节

## 本 ASIL 等级的 ISO 26262 方法要求
{asil_req}

## 源代码
```c
{code}
```

## 你需要输出的章节
{sections}

## 输出要求
- 直接输出 Markdown 格式的章节内容，从 `## 第X章` 开始
- 不需要输出文档标题（# 标题），直接从二级标题开始
- 保持与完整文档的上下文一致性
- 表格、Mermaid 图等元素按标准格式输出
- 确保内容与源代码严格对应，不编造不存在的功能"""

    def get_review_prompt(self, doc_type: str, generated_doc: str, code: str, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")
        asil_req = _get_asil_requirements(asil_level)

        doc_full_names = {
            "SRS": "软件需求规格说明",
            "SAD": "软件架构设计",
            "FMEA": "失效模式与影响分析",
            "SDD": "软件详细设计",
            "TC-UNIT": "单元测试用例",
            "TC-INTEGRATION": "集成测试用例",
        }
        full_name = doc_full_names.get(doc_type, doc_type)

        return f"""你是一名资深功能安全审查工程师。请对以下已由其他同事撰写的 **{full_name}文档（{doc_type}）** 进行专业审查和修订。

## 审查背景
- 模块名称：{module_name}
- ASIL 等级：{asil_level}

## 本 ASIL 等级的 ISO 26262 方法要求
{asil_req}

## 待审查的文档
{generated_doc}

## 原始源代码（供核对）
```c
{code}
```

## 审查要求

请从以下维度进行审查并直接输出修订后的完整文档：

### 1. 准确性审查
- 核对文档中描述的功能是否与源代码一致
- 检查是否有虚构的函数、变量、接口
- 验证数据类型、参数、返回值是否准确

### 2. 完整性审查
- 是否有遗漏的关键功能或安全机制
- 是否覆盖了所有重要的函数和模块
- 表格是否完整（无空行、无缺失列）
- 需求ID/测试用例ID编号是否连续、无重复

### 3. 一致性审查
- 术语使用是否前后一致
- 模块名称、函数名称是否与代码一致
- 交叉引用是否正确

### 4. ISO 26262 合规性审查
- {asil_level} 等级对应的要求是否满足（参照上方方法要求）
- 安全机制描述是否充分
- 是否缺少必要的安全相关章节

### 5. 追溯性审查
- 需求→代码→测试的双向追溯是否完整
- 追溯矩阵中是否有未覆盖项

### 6. 修订规则
- 保留原文档的正确部分，只修改有问题的部分
- 对每处修改用 `<!-- 修订: 原因 -->` 注释标注修改理由
- 如果原文档质量已经很高，不需要刻意修改

## 输出格式
直接输出修订后的完整 Markdown 文档。在文档末尾添加：

---
### 审查报告
| 审查维度 | 评价 | 修订数量 |
|---------|------|---------|
| 准确性 | ✅/⚠️/❌ | X 处 |
| 完整性 | ✅/⚠️/❌ | X 处 |
| 一致性 | ✅/⚠️/❌ | X 处 |
| 合规性 | ✅/️/❌ | X 处 |
| 追溯性 | ✅/⚠️/ | X 处 |

**总体评价**：[简要总结文档质量和主要修订内容]"""
