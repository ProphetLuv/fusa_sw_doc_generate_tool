# -*- coding: utf-8 -*-
"""
七种功能安全文档类型的专业 Prompt 模板包。

对外暴露 PromptManager，保持 `from prompts import PromptManager` 兼容。

子模块：
- _base.py          : 共享常量（ASIL 要求、覆盖率、AI-AP 表）
- srs.py            : SRS 软件需求规格说明
- sad.py            : SAD 软件架构设计
- fmea.py           : FMEA 失效模式与影响分析
- dfa.py            : DFA 相关失效分析
- sdd.py            : SDD 软件详细设计
- tc_unit.py        : TC-UNIT 单元测试用例
- tc_integration.py : TC-INTEGRATION 集成测试用例
"""

from typing import Dict, Any, Optional

from safety_knowledge import get_safety_knowledge
from prompts._base import get_asil_requirements
from prompts.srs import build_srs_prompt
from prompts.sad import build_sad_prompt
from prompts.fmea import build_fmea_prompt
from prompts.dfa import build_dfa_prompt
from prompts.sdd import build_sdd_prompt
from prompts.tc_unit import build_tc_unit_prompt
from prompts.tc_integration import build_tc_integration_prompt


class PromptManager:
    """
    Prompt 管理器，根据文档类型分发到对应的专业 Prompt 模板。
    """

    DOC_TYPES = ("SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION")

    # 文档类型全名映射
    _DOC_FULL_NAMES = {
        "SRS": "软件需求规格说明",
        "SAD": "软件架构设计",
        "FMEA": "失效模式与影响分析",
        "DFA": "相关失效分析",
        "SDD": "软件详细设计",
        "TC-UNIT": "单元测试用例",
        "TC-INTEGRATION": "集成测试用例",
    }

    # dispatch 表：文档类型 → 构建函数
    _BUILDERS = {
        "SRS": build_srs_prompt,
        "SAD": build_sad_prompt,
        "FMEA": build_fmea_prompt,
        "DFA": build_dfa_prompt,
        "SDD": build_sdd_prompt,
        "TC-UNIT": build_tc_unit_prompt,
        "TC-INTEGRATION": build_tc_integration_prompt,
    }

    def get_prompt(
        self,
        doc_type: str,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        custom_template: Optional[str] = None,
        background_prompt: Optional[str] = None,
    ) -> str:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")

        builder = self._BUILDERS.get(doc_type.upper())
        if not builder:
            raise ValueError(f"不支持的文档类型: {doc_type}，可选: {self.DOC_TYPES}")

        prompt = builder(code, module_name, asil_level)

        # 注入全局项目背景（在所有 Agent 指令之前）
        if background_prompt:
            prompt = self._inject_background(prompt, background_prompt)

        # 注入功能安全领域知识库（降低 LLM 幻觉，提升专业性）
        knowledge = get_safety_knowledge(asil_level, doc_type.upper())
        if knowledge:
            prompt += knowledge

        prior_docs = ctx.get("prior_docs")
        if prior_docs:
            prompt = self._inject_prior_docs(prompt, prior_docs)

        if custom_template:
            prompt = self._apply_custom_template(prompt, custom_template)

        return prompt

    def _inject_background(self, prompt: str, background_prompt: str) -> str:
        """在 Prompt 最开头注入项目背景描述，帮助 LLM 理解代码上下文。"""
        bg = background_prompt.strip()
        if not bg:
            return prompt
        return f"## 项目背景与代码概述\n\n{bg}\n\n---\n\n{prompt}"

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
    # 分段并发
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
        "DFA": [
            {"id": 1, "title": "第1~2章", "sections": "1. 分析范围与方法、2. 架构元素识别"},
            {"id": 2, "title": "第3~4章", "sections": "3. 共因失效分析（CCF）、4. 级联失效分析（Cascading）"},
            {"id": 3, "title": "第5~6章", "sections": "5. 独立性/无干扰分析（FFI）、6. 单点失效分析（SPF）"},
            {"id": 4, "title": "第7~8章", "sections": "7. DFA 综合评估（风险汇总+追溯矩阵）、8. 结论与建议"},
        ],
        "SDD": [
            {"id": 1, "title": "第1~3章", "sections": "1. 设计概述、2. 架构设计、3. 接口设计"},
            {"id": 2, "title": "第4~6章", "sections": "4. 详细设计、5. 数据结构设计、6. 算法设计"},
        ],
        "TC-UNIT": [
            {"id": 1, "title": "第1~3章", "sections": "1. 测试策略、2. 单元测试用例表（等价类/边界值/错误猜测/状态转换/安全机制/故障注入）、3. 测试规程"},
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
        background_prompt: Optional[str] = None,
    ) -> list:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")

        chunks = self.DOC_CHUNKS.get(doc_type.upper(), [])
        if not chunks:
            full_prompt = self.get_prompt(doc_type, code, context, custom_template, background_prompt=background_prompt)
            return [(doc_type, full_prompt)]

        results = []
        prior_docs = ctx.get("prior_docs")
        for chunk in chunks:
            chunk_prompt = self._build_chunk_prompt(
                doc_type, code, module_name, asil_level,
                chunk["id"], chunk["title"], chunk["sections"],
                total_chunks=len(chunks),
            )
            # 注入全局项目背景
            if background_prompt:
                chunk_prompt = self._inject_background(chunk_prompt, background_prompt)
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
        asil_req = get_asil_requirements(asil_level)
        full_name = self._DOC_FULL_NAMES.get(doc_type, doc_type)

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

    # ------------------------------------------------------------------
    # 审查修订
    # ------------------------------------------------------------------

    def get_review_prompt(self, doc_type: str, generated_doc: str, code: str, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")
        asil_req = get_asil_requirements(asil_level)
        full_name = self._DOC_FULL_NAMES.get(doc_type, doc_type)

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
| 合规性 | ✅/⚠️/❌ | X 处 |
| 追溯性 | ✅/⚠️/❌ | X 处 |

**总体评价**：[简要总结文档质量和主要修订内容]"""

    # ------------------------------------------------------------------
    # 分段一致性合并审查
    # ------------------------------------------------------------------

    def get_consistency_merge_prompt(self, doc_type: str, merged_doc: str, code: str,
                                      context: Optional[Dict[str, Any]] = None) -> str:
        """生成分段并发后的一致性合并审查 Prompt。"""
        ctx = context or {}
        module_name = ctx.get("module_name", "目标模块")
        asil_level = ctx.get("asil_level", "ASIL B")
        full_name = self._DOC_FULL_NAMES.get(doc_type, doc_type)

        return f"""你是一名功能安全文档质量工程师。以下 **{full_name}文档（{doc_type}）** 是由多个章节并行生成后拼接而成的，
请对其进行**一致性合并审查**，确保全文统一、无冲突。

## 全局上下文
- 模块名称：{module_name}
- ASIL 等级：{asil_level}

## 待审查的拼接文档
{merged_doc}

## 原始源代码（供核对）
```c
{code}
```

## 一致性审查要求

### 1. 术语一致性
- 检查同一函数/变量/模块在全文中是否使用相同的名称
- 检查缩略语是否在首次出现时有完整定义
- 统一中英文术语的使用（如"失效模式" vs "故障模式"）

### 2. 编号一致性
- 检查所有 ID 编号（SRS-XXX / FM-XXX / UT-XXX / CCF-XXX 等）是否全局唯一
- 检查编号是否连续、无跳号
- 如发现重复 ID，请重新编号为连续唯一值

### 3. 交叉引用完整性
- 检查追溯矩阵中引用的 ID 是否在正文中实际存在
- 检查"参见第X章"等引用是否指向正确的章节
- 检查表格之间的关联字段是否一致

### 4. 格式统一性
- 统一表格列名和列数（相同类型的表格应结构一致）
- 统一标题层级（不应出现跳级，如 ## 直接到 ####）
- 统一 Mermaid 图的风格

### 5. 内容连贯性
- 检查相邻章节之间是否有重复内容（并行生成常见）
- 检查是否有矛盾的结论（如一处说"已覆盖"，另一处说"未覆盖"）
- 确保全文读起来是一份连贯的文档，而非多份文档的简单拼接

## 输出要求
- 直接输出修订后的完整 Markdown 文档
- 对每处修改用 `<!-- 一致性修订: 原因 -->` 注释标注
- 如果原文档一致性已经很好，不需要刻意修改
- 在文档末尾添加：

---
### 一致性审查报告
| 审查维度 | 评价 | 修订数量 |
|---------|------|--------|
| 术语一致性 | ✅/⚠️/❌ | X 处 |
| 编号一致性 | ✅/⚠️/❌ | X 处 |
| 交叉引用 | ✅/⚠️/❌ | X 处 |
| 格式统一性 | ✅/⚠️/❌ | X 处 |
| 内容连贯性 | ✅/⚠️/❌ | X 处 |

**总体评价**：[简要总结一致性状况和主要修订]"""
