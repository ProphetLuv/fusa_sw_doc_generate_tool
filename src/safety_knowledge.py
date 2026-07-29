# -*- coding: utf-8 -*-
"""
功能安全领域知识库
为 Prompt 注入结构化领域参考数据，降低 LLM 幻觉风险，提升专业性。

数据来源：
- ISO 26262:2018 Part 5/6/9
- IEC 62380（已被 IEC 61709 取代，失效率数据仍具参考性）
- SN 29500 元器件失效率
- AIAG-VDA FMEA 手册 2019
- 典型嵌入式安全机制诊断覆盖率（DC）参考值
"""

from typing import Optional


# ======================================================================
# 典型嵌入式失效模式库（基于 IEC 62380 / SN 29500）
# ======================================================================

FAILURE_MODE_LIBRARY = """
### 典型嵌入式软件失效模式参考（ISO 26262-6:2018 Annex D / IEC 61709）

**数据失效模式**（对应 26262-6 Annex D「信息交换」「内存」干扰类型）：
- 数据损坏（bit-flip / 多比特错误）
- 数据丢失（未写入 / 写入被覆盖）
- 数据延迟（超出 FTTI 窗口）
- 数据不一致（多副本不同步）
- 数据溢出 / 下溢（整数运算边界）

**控制流失效模式**（对应 26262-6 Annex D「时序与执行」干扰类型）：
- 命令未执行（函数未调用 / 条件永假）
- 命令错误执行（参数错误 / 算法错误）
- 命令时序错误（过早 / 过晚 / 重复执行）
- 命令持续时间错误（过长 / 过短）

**资源失效模式**：
- CPU 过载（WCET 超限 / 优先级反转）
- 内存耗尽（栈溢出 / 堆碎片）
- 通信总线忙（CAN/SPI 总线仲裁失败）
- 外设故障（ADC 卡死 / PWM 输出锁定）

**典型失效率参考（SN 29500, 40°C 环境）**：
- MCU 核心: 10~50 FIT（1 FIT = 10⁻⁹/h）
- SRAM (per Mbit): 5~20 FIT
- Flash (per Mbit): 1~5 FIT
- CAN 收发器: 10~30 FIT
- 电源调节器: 20~50 FIT
"""


# ======================================================================
# 安全机制诊断覆盖率（DC）参考值（ISO 26262 Part 5 Annex D）
# ======================================================================

SAFETY_MECHANISM_DC_TABLE = """
### 典型安全机制诊断覆盖率（DC）参考值

| 安全机制 | 典型 DC 范围 | DC 等级 | 适用场景 |
|---------|-------------|---------|---------|
| 简单比较（1oo2 比较） | 90%~99% | 中~高 | 双核锁步、冗余计算 |
| CRC 校验（8/16/32位） | 90%~99% | 中~高 | 通信数据完整性 |
| ECC（SECDED） | ≥99% | 高 | SRAM/Flash 数据纠错 |
| 看门狗（窗口型） | 90% | 中 | 程序执行时序监控 |
| 逻辑监控（Question-Answer） | 90% | 中 | 程序流/安全状态转换验证 |
| 时序+逻辑组合程序流监控 | 99% | 高 | 高 ASIL 程序执行监控 |
| 电压/时钟监控 | 90%~99% | 中~高 | 电源/时钟故障检测 |
| 冗余传感器比较 | 90%~99% | 中~高 | 传感器合理性检查 |
| 范围检查（Plausibility） | 60%~90% | 低~中 | 输入信号合理性 |
| 超时监控 | 60%~90% | 低~中 | 通信/任务执行监控 |
| 栈溢出检测（硬件） | 90%~99% | 中~高 | 栈空间保护 |
| MPU/MMU 空间隔离 | ≥99% | 高 | 内存空间保护 |
| 心跳监测 | 60%~90% | 低~中 | 模块存活检测 |

**DC 等级声称值（ISO 26262-5:2018 Annex D）**：
- 低（Low）: 60%
- 中（Medium）: 90%
- 高（High）: 99%

> 注：ISO 26262 仅定义 60%/90%/99% 三档 DC 声称值，无「很高（≥99.9%）」档位；
> 声称高于表中典型值的 DC 需提供失效模式级的定量分析证据。
"""


# ======================================================================
# ASIL 分解规则（ISO 26262 Part 9 Clause 5）
# ======================================================================

ASIL_DECOMPOSITION_RULES = """
### ASIL 分解规则（ISO 26262:2018 Part 9 Clause 5）

ASIL 分解允许将高 ASIL 等级的安全需求分配给多个低 ASIL 等级的冗余元素，
前提是这些元素之间满足**独立性（Independence）** 要求。

> 术语辨析（ISO 26262-9 Clause 5/6/7）：**独立性 = 无相关失效**（共因失效 CCF
> + 级联失效），须通过**相关失效分析（DFA）**论证；**FFI（免于干扰）仅覆盖级联
> 失效**，是弱于独立性的要求，不能单独作为 ASIL 分解的依据。

**合法分解方案**：

| 原始 ASIL | 分解方案 | 独立性要求 |
|-----------|---------|-----------|
| ASIL D | ASIL D(D) + QM(D) | 需论证 QM 元素与 ASIL D 元素间的独立性 |
| ASIL D | ASIL C(D) + ASIL A(D) | 两元素间需 DFA 论证独立性 |
| ASIL D | ASIL B(D) + ASIL B(D) | 两元素间需 DFA 论证独立性（工程常用） |
| ASIL C | ASIL C(C) + QM(C) | 需论证 QM 元素与 ASIL C 元素间的独立性 |
| ASIL C | ASIL B(C) + ASIL A(C) | 两元素间需 DFA 论证独立性 |
| ASIL B | ASIL B(B) + QM(B) | 需论证 QM 元素与 ASIL B 元素间的独立性 |
| ASIL B | ASIL A(B) + ASIL A(B) | 两元素间需 DFA 论证独立性 |
| ASIL A | ASIL A(A) + QM(A) | 需论证 QM 元素与 ASIL A 元素间的独立性 |

**分解约束**：
1. 括号中的字母表示原始 ASIL 等级（分解来源），确认措施仍按原始 ASIL 执行
2. 分解后的元素必须执行独立的验证活动
3. 相同 ASIL 的冗余分解（如 B+B）建议采用多样性设计（不同算法/不同团队），
   以降低共因失效风险；多样性是推荐缓解手段，独立性论证（DFA）才是必要条件
4. 含 QM 的分解需通过 DFA 证明 QM 元素不会经共因/级联失效影响高 ASIL 元素
5. 分解不适用于同一元素内部，只适用于架构层面的冗余元素

**独立性论证方法（DFA 输入）**：
- 共因失效分析：共享资源（电源/时钟/库函数/编译器）、共同环境条件识别
- 数据流分析：确认无共享数据路径（级联失效）
- 控制流分析：确认无共享控制路径（级联失效）
- 资源分析：确认 CPU/内存/外设资源隔离（时间与空间分区）
- 设计审查：确认由不同团队独立开发（多样性）
"""


# ======================================================================
# FTTI（故障容错时间间隔）参考
# ======================================================================

FTTI_REFERENCE = """
### 故障容错时间间隔（FTTI）参考（ISO 26262-1:2018 3.61）

**FTTI** = 故障发生 → **可能发生危害事件**的最小时间间隔（假设无安全机制干预）。
安全机制必须在 FTTI 内完成故障检测与响应，即满足：

**FHTI（故障处理时间）= FDTI（故障检测时间）+ FRTI（故障响应时间）< FTTI**

其中 FDTI 含诊断确认时间，FRTI 含安全状态转换与执行器响应时间。

**典型汽车系统 FTTI 参考值**：

| 应用场景 | 典型 FTTI | 安全机制响应要求 |
|---------|-----------|----------------|
| 电动助力转向（EPS） | 10~50 ms | 看门狗 + 扭矩传感器冗余 |
| 防抱死制动（ABS/ESC） | 20~100 ms | 压力传感器 + 轮速传感器交叉校验 |
| 电机控制（逆变器） | 5~20 ms | 过流/过压硬件保护 + 软件监控 |
| 电池管理（BMS） | 100 ms~1 s | 电压/温度冗余采样 + 热失控预警 |
| 自适应巡航（ACC） | 100~500 ms | 雷达/摄像头传感器融合 |
| 车身控制（灯光/雨刮） | 1~10 s | 短路/开路检测 |

> 注：以上为行业经验参考值，实际 FTTI 应从危害分析与风险评估（HARA）中的
> 具体危害场景推导，不可直接照搬。
"""


# ======================================================================
# 知识库注入接口
# ======================================================================

def get_safety_knowledge(asil_level: str, doc_type: str) -> str:
    """
    根据 ASIL 等级和文档类型，返回应注入的安全知识片段。

    Args:
        asil_level: ASIL 等级（QM / ASIL A / ASIL B / ASIL C / ASIL D）
        doc_type:   文档类型（SRS / SAD / FMEA / DFA / SDD / TC-UNIT / TC-INTEGRATION）

    Returns:
        格式化的安全知识文本（Markdown），可直接拼接到 Prompt 中
    """
    sections = []

    # FMEA / DFA 注入失效模式库和安全机制 DC 表
    if doc_type in ("FMEA", "DFA"):
        sections.append(FAILURE_MODE_LIBRARY)
        sections.append(SAFETY_MECHANISM_DC_TABLE)
        if asil_level in ("ASIL C", "ASIL D"):
            sections.append(FTTI_REFERENCE)

    # DFA 额外注入 ASIL 分解规则（含独立性论证方法，DFA 的核心分析对象）
    if doc_type == "DFA" and asil_level in ("ASIL B", "ASIL C", "ASIL D"):
        sections.append(ASIL_DECOMPOSITION_RULES)

    # SRS 注入 ASIL 分解规则（ASIL B 及以上）
    if doc_type == "SRS" and asil_level in ("ASIL B", "ASIL C", "ASIL D"):
        sections.append(ASIL_DECOMPOSITION_RULES)

    # SAD 注入安全机制 DC 表（用于架构安全机制选型）
    if doc_type == "SAD" and asil_level in ("ASIL B", "ASIL C", "ASIL D"):
        sections.append(SAFETY_MECHANISM_DC_TABLE)

    # SDD 注入 FTTI 参考（ASIL C/D 需要时间约束分析）
    if doc_type == "SDD" and asil_level in ("ASIL C", "ASIL D"):
        sections.append(FTTI_REFERENCE)
        sections.append(SAFETY_MECHANISM_DC_TABLE)

    # TC-UNIT / TC-INTEGRATION 注入安全机制参考（用于故障注入测试设计）
    if doc_type in ("TC-UNIT", "TC-INTEGRATION") and asil_level in ("ASIL B", "ASIL C", "ASIL D"):
        sections.append(SAFETY_MECHANISM_DC_TABLE)

    if not sections:
        return ""

    header = "\n\n## 📚 功能安全领域参考知识（仅供分析参考，请结合代码实际情况使用）\n\n"
    return header + "\n".join(sections)


def get_asil_decomposition_guidance(asil_level: str) -> str:
    """
    获取 ASIL 分解指导文本（用于 SRS Prompt 中的安全需求章节）。

    Args:
        asil_level: 当前模块的 ASIL 等级

    Returns:
        ASIL 分解相关的 Prompt 指导文本
    """
    if asil_level in ("QM", "ASIL A"):
        return ""

    return f"""
### 安全需求 ASIL 分解（ISO 26262 Part 9 Clause 5）

对于 **{asil_level}** 等级的安全需求，请分析是否适合进行 ASIL 分解：

1. **分解可行性判断**：
   - 该安全需求是否可通过冗余架构实现？
   - 是否存在两个或多个独立元素可分担安全功能？

2. **如适合分解，请输出分解方案表**：

| 原始需求ID | 原始ASIL | 分解方案 | 子需求A (ASIL) | 子需求B (ASIL) | 独立性论证方法 | 验证策略 |
|-----------|---------|---------|---------------|---------------|--------------|---------|

3. **独立性论证要求**：
   - 数据独立性：子需求A/B 不共享关键数据路径
   - 时间独立性：子需求A/B 不共享关键时序资源
   - 设计独立性：建议由不同团队/不同算法实现

4. **不适合分解的需求**：标注"不可分解"并说明原因（如单传感器路径、无冗余可能）
"""
