# -*- coding: utf-8 -*-
"""
C/C++ 代码轻量解析器（纯正则实现，不依赖 tree-sitter）
用于对上传的嵌入式源码做静态分析，提取结构化信息。
"""

import re
from typing import Dict, List, Any


class CodeParser:
    """
    基于正则表达式的 C/C++ 代码解析器。
    适用于嵌入式场景下的函数、结构体、宏、全局变量等轻量提取。
    """

    # ------------------------------------------------------------------
    # 正则模式定义
    # ------------------------------------------------------------------

    # #include 头文件
    _RE_INCLUDE = re.compile(
        r'^\s*#\s*include\s+[<"]([^>"]+)[>"]',
        re.MULTILINE,
    )

    # 宏定义（#define NAME ...）
    _RE_MACRO = re.compile(
        r'^\s*#\s*define\s+(\w+)(?:\([^)]*\))?\s*(.*)',
        re.MULTILINE,
    )

    # struct / union / enum 定义
    _RE_STRUCT = re.compile(
        r'\b(?:typedef\s+)?(?:struct|union|enum)\s+(\w+)\s*\{',
        re.MULTILINE,
    )

    # 全局变量：出现在函数体外、以 ; 结尾的声明行
    # 简化规则：以常见类型关键字开头，不在函数体内部
    _RE_GLOBAL_VAR = re.compile(
        r'^(?:static\s+|extern\s+|volatile\s+|const\s+)*'
        r'(?:unsigned\s+|signed\s+)?'
        r'(?:void|char|short|int|long|float|double|bool|uint8_t|uint16_t|'
        r'uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|size_t|'
        r'BOOL|BOOLEAN|U8|U16|U32|S8|S16|S32)\s+'
        r'\**\s*(\w+)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;',
        re.MULTILINE,
    )

    # 函数定义（支持多行签名）
    # 匹配模式：[返回类型] [修饰符] 函数名(参数列表) {
    _RE_FUNC_DEF = re.compile(
        r'^[ \t]*'
        r'(?:(?:static|inline|extern|const|volatile|__attribute__\s*\(\([^)]*\)\))\s+)*'
        r'(?:unsigned\s+|signed\s+)?'
        r'(?:void|char|short|int|long|float|double|bool|'
        r'uint8_t|uint16_t|uint32_t|uint64_t|'
        r'int8_t|int16_t|int32_t|int64_t|'
        r'size_t|BOOL|BOOLEAN|U8|U16|U32|S8|S16|S32|'
        r'[A-Z]\w*_t|[A-Z]\w*_e|[A-Z]\w*_s|[A-Z]\w*_type|'
        r'struct\s+\w+|enum\s+\w+|union\s+\w+|\w+)\s+'
        r'\**\s*'
        r'(\w+)'               # 函数名（捕获组1）
        r'\s*\([^)]*\)'        # 参数列表
        r'\s*\{',              # 函数体开始花括号
        re.MULTILINE,
    )

    # 函数签名（带返回类型）用于提取展示
    _RE_FUNC_SIG = re.compile(
        r'^[ \t]*'
        r'((?:(?:static|inline|extern|const|volatile|__attribute__\s*\(\([^)]*\)\))\s+)*'
        r'(?:unsigned\s+|signed\s+)?'
        r'(?:void|char|short|int|long|float|double|bool|'
        r'uint8_t|uint16_t|uint32_t|uint64_t|'
        r'int8_t|int16_t|int32_t|int64_t|'
        r'size_t|BOOL|BOOLEAN|U8|U16|U32|S8|S16|S32|'
        r'[A-Z]\w*_t|[A-Z]\w*_e|[A-Z]\w*_s|[A-Z]\w*_type|'
        r'struct\s+\w+|enum\s+\w+|union\s+\w+|\w+)\s+'
        r'\**\s*'
        r'\w+'
        r'\s*\([^)]*\))',
        re.MULTILINE,
    )

    def analyze(self, code: str) -> Dict[str, Any]:
        """
        对 C/C++ 代码进行静态分析，返回结构化摘要信息。

        Args:
            code: 完整的 C/C++ 源代码字符串

        Returns:
            包含以下键的字典：
            - lines:           代码总行数
            - functions:       函数定义数量
            - structs:         struct/union/enum 数量
            - macros:          宏定义数量
            - global_vars:     全局变量数量
            - estimated_tokens: 预估 token 数（按 4 字符 ≈ 1 token 估算）
            - function_names:  函数名列表
            - includes:        头文件列表
        """
        lines = code.count('\n') + (0 if code.endswith('\n') else 1)

        # 头文件
        includes = self._RE_INCLUDE.findall(code)

        # 宏
        macros = self._RE_MACRO.findall(code)

        # 结构体 / 联合体 / 枚举
        structs = self._RE_STRUCT.findall(code)

        # 函数
        func_matches = list(self._RE_FUNC_DEF.finditer(code))
        function_names = [m.group(1) for m in func_matches]

        # 全局变量（排除函数体内的声明，使用粗略过滤）
        global_vars = self._extract_global_vars(code, func_matches)

        # 预估 token：经验公式 ≈ 字符数 / 4（中英文混合场景偏保守）
        estimated_tokens = max(1, len(code) // 4)

        return {
            "lines": lines,
            "functions": len(func_matches),
            "structs": len(structs),
            "macros": len(macros),
            "global_vars": len(global_vars),
            "estimated_tokens": estimated_tokens,
            "function_names": function_names,
            "includes": list(dict.fromkeys(includes)),  # 去重并保持顺序
        }

    def split_by_function(self, code: str) -> List[Dict[str, Any]]:
        """
        按函数定义拆分代码，返回每个函数的信息列表。

        Args:
            code: 完整的 C/C++ 源代码字符串

        Returns:
            列表，每个元素为字典：
            - name:       函数名
            - signature:  完整函数签名（含返回类型和参数）
            - body:       函数体（含花括号）
            - char_start: 在源码中的起始字符位置
            - char_end:   在源码中的结束字符位置
        """
        results: List[Dict[str, Any]] = []
        func_matches = list(self._RE_FUNC_DEF.finditer(code))

        for match in func_matches:
            func_name = match.group(1)
            body_start = match.end() - 1  # '{' 的位置

            # 通过花括号配对找到函数体结束位置
            body_end = self._find_matching_brace(code, body_start)
            if body_end == -1:
                # 配对失败，跳过该函数
                continue

            body = code[body_start: body_end + 1]

            # 提取签名：从 match 起始向前找返回类型行
            sig = self._extract_signature(code, match.start(), body_start)

            results.append({
                "name": func_name,
                "signature": sig.strip(),
                "body": body,
                "char_start": match.start(),
                "char_end": body_end,
            })

        return results

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _find_matching_brace(self, code: str, start: int) -> int:
        """
        从 start 位置的 '{' 开始，找到匹配的 '}' 位置。
        正确处理字符串字面量、字符常量和注释中的花括号。

        Returns:
            匹配的 '}' 索引，若未找到返回 -1
        """
        depth = 0
        i = start
        n = len(code)

        while i < n:
            ch = code[i]

            # 跳过单行注释
            if ch == '/' and i + 1 < n and code[i + 1] == '/':
                while i < n and code[i] != '\n':
                    i += 1
                continue

            # 跳过多行注释
            if ch == '/' and i + 1 < n and code[i + 1] == '*':
                i += 2
                while i < n - 1 and not (code[i] == '*' and code[i + 1] == '/'):
                    i += 1
                i += 2
                continue

            # 跳过字符串字面量
            if ch == '"':
                i += 1
                while i < n and code[i] != '"':
                    if code[i] == '\\':
                        i += 1  # 跳过转义字符
                    i += 1
                i += 1
                continue

            # 跳过字符常量
            if ch == "'":
                i += 1
                while i < n and code[i] != "'":
                    if code[i] == '\\':
                        i += 1
                    i += 1
                i += 1
                continue

            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return i

            i += 1

        return -1

    def _extract_signature(self, code: str, match_start: int, body_start: int) -> str:
        """
        提取函数签名文本（从行首到 '{' 之前）。
        """
        # 向前找到当前行的行首
        line_start = code.rfind('\n', 0, match_start)
        line_start = line_start + 1 if line_start != -1 else 0
        sig_text = code[line_start:body_start].strip()
        # 清理多余空白
        sig_text = re.sub(r'\s+', ' ', sig_text)
        return sig_text

    def _extract_global_vars(
        self, code: str, func_matches: list
    ) -> List[str]:
        """
        提取全局变量名，排除函数体内的局部变量。
        通过判断变量声明是否在某个函数体内部来进行过滤。
        """
        # 构建函数体区间集合
        func_ranges = []
        for m in func_matches:
            body_start = m.end() - 1
            body_end = self._find_matching_brace(code, body_start)
            if body_end != -1:
                func_ranges.append((body_start, body_end))

        def inside_function(pos: int) -> bool:
            """判断字符位置是否在某个函数体内部"""
            return any(start <= pos <= end for start, end in func_ranges)

        global_var_names = []
        for m in self._RE_GLOBAL_VAR.finditer(code):
            if not inside_function(m.start()):
                global_var_names.append(m.group(1))

        return global_var_names
