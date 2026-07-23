# -*- coding: utf-8 -*-
"""
C/C++ 代码解析器（tree-sitter AST + 正则回退）
用于对上传的嵌入式源码做静态分析，提取结构化信息。

特性（#6 升级）：
- 基于 tree-sitter 的 AST 级分析（函数、结构体、宏、全局变量）
- 函数调用图提取
- 圈复杂度（Cyclomatic Complexity）计算
- 正则回退机制（tree-sitter 不可用时自动降级）
"""

import re
from typing import Dict, List, Any, Optional, Tuple


class CodeParser:
    """
    C/C++ 代码解析器。
    优先使用 tree-sitter AST 分析，失败时回退到正则表达式。
    """

    # ------------------------------------------------------------------
    # 正则模式（回退用）
    # ------------------------------------------------------------------

    _RE_INCLUDE = re.compile(r'^\s*#\s*include\s+[<"]([^>"]+)[>"]', re.MULTILINE)
    _RE_MACRO = re.compile(r'^\s*#\s*define\s+(\w+)(?:\([^)]*\))?\s*(.*)', re.MULTILINE)
    _RE_STRUCT = re.compile(r'\b(?:typedef\s+)?(?:struct|union|enum)\s+(\w+)\s*\{', re.MULTILINE)
    _RE_GLOBAL_VAR = re.compile(
        r'^(?:static\s+|extern\s+|volatile\s+|const\s+)*'
        r'(?:unsigned\s+|signed\s+)?'
        r'(?:void|char|short|int|long|float|double|bool|uint8_t|uint16_t|'
        r'uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|size_t|'
        r'BOOL|BOOLEAN|U8|U16|U32|S8|S16|S32)\s+'
        r'\**\s*(\w+)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;',
        re.MULTILINE,
    )
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
        r'(\w+)'
        r'\s*\([^)]*\)'
        r'\s*\{',
        re.MULTILINE,
    )

    def __init__(self):
        self._ts_parser: Optional[Any] = None
        self._ts_available = False
        self._init_tree_sitter()

    def _init_tree_sitter(self):
        """尝试初始化 tree-sitter 解析器。"""
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_c
            import tree_sitter_cpp

            self._ts_c_lang = Language(tree_sitter_c.language())
            self._ts_cpp_lang = Language(tree_sitter_cpp.language())
            self._ts_parser = Parser()
            self._ts_available = True
        except Exception:
            # 回退：尝试旧版 API
            try:
                from tree_sitter import Language, Parser
                self._ts_c_lang = Language.create(tree_sitter_c.language())
                self._ts_cpp_lang = Language.create(tree_sitter_cpp.language())
                self._ts_parser = Parser()
                self._ts_available = True
            except Exception:
                self._ts_available = False

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def analyze(self, code: str) -> Dict[str, Any]:
        """
        对 C/C++ 代码进行静态分析，返回结构化摘要信息。

        Returns:
            包含以下键的字典：
            - lines:              代码总行数
            - functions:          函数定义数量
            - structs:            struct/union/enum 数量
            - macros:             宏定义数量
            - global_vars:        全局变量数量
            - estimated_tokens:   预估 token 数
            - function_names:     函数名列表
            - includes:           头文件列表
            - call_graph:         函数调用图 {func_name: [called_funcs]}
            - cyclomatic_complexity: 各函数圈复杂度 {func_name: complexity}
            - avg_complexity:     平均圈复杂度
            - max_complexity:     最大圈复杂度及对应函数
        """
        lines = code.count('\n') + (0 if code.endswith('\n') else 1)
        includes = list(dict.fromkeys(self._RE_INCLUDE.findall(code)))
        macros = self._RE_MACRO.findall(code)
        structs = self._RE_STRUCT.findall(code)

        if self._ts_available:
            func_names, call_graph, complexities = self._analyze_with_tree_sitter(code)
        else:
            func_matches = list(self._RE_FUNC_DEF.finditer(code))
            func_names = [m.group(1) for m in func_matches]
            call_graph = self._extract_call_graph_regex(code, func_names)
            complexities = self._calc_complexity_regex(code, func_matches)

        global_vars = self._extract_global_vars(code)
        estimated_tokens = max(1, len(code) // 4)

        avg_cc = sum(complexities.values()) / len(complexities) if complexities else 0
        max_cc_func = max(complexities, key=complexities.get) if complexities else "N/A"
        max_cc = complexities.get(max_cc_func, 0)

        return {
            "lines": lines,
            "functions": len(func_names),
            "structs": len(structs),
            "macros": len(macros),
            "global_vars": len(global_vars),
            "estimated_tokens": estimated_tokens,
            "function_names": func_names,
            "includes": includes,
            "call_graph": call_graph,
            "cyclomatic_complexity": complexities,
            "avg_complexity": round(avg_cc, 1),
            "max_complexity": f"{max_cc} ({max_cc_func})",
        }

    def split_by_function(self, code: str) -> List[Dict[str, Any]]:
        """按函数定义拆分代码，返回每个函数的信息列表。"""
        if self._ts_available:
            return self._split_by_function_ts(code)
        return self._split_by_function_regex(code)

    # ------------------------------------------------------------------
    # tree-sitter 分析
    # ------------------------------------------------------------------

    def _analyze_with_tree_sitter(self, code: str) -> Tuple[List[str], Dict[str, List[str]], Dict[str, int]]:
        """使用 tree-sitter AST 分析代码。"""
        from tree_sitter import Node

        is_cpp = any(ext in code for ext in ['::', '#include <', 'class ', 'template '])
        self._ts_parser.language = self._ts_cpp_lang if is_cpp else self._ts_c_lang
        tree = self._ts_parser.parse(code.encode("utf-8"))
        root = tree.root_node

        func_names: List[str] = []
        call_graph: Dict[str, List[str]] = {}
        complexities: Dict[str, int] = {}

        self._walk_functions(root, code, func_names, call_graph, complexities)

        return func_names, call_graph, complexities

    def _walk_functions(self, node, code: str, func_names: List[str],
                        call_graph: Dict[str, List[str]], complexities: Dict[str, int]):
        """递归遍历 AST 节点，提取函数信息。"""
        if node.type in ("function_definition",):
            # 提取函数名
            name_node = self._find_function_name(node)
            if name_node:
                fname = name_node.text.decode("utf-8")
                func_names.append(fname)

                # 提取函数体内的调用
                body = self._find_child_by_type(node, "compound_statement")
                if body:
                    called = self._extract_calls_from_node(body)
                    call_graph[fname] = called

                # 计算圈复杂度
                complexities[fname] = self._calc_cyclomatic_complexity(node)

        # 递归子节点
        for child in node.children:
            self._walk_functions(child, code, func_names, call_graph, complexities)

    def _find_function_name(self, func_node) -> Optional[Any]:
        """在函数定义节点中查找名称节点。"""
        declarator = self._find_child_by_type(func_node, "function_declarator")
        if declarator:
            return self._find_child_by_type(declarator, "identifier")
        # 回退：查找第一个 identifier
        for child in func_node.children:
            if child.type == "identifier":
                return child
        return None

    def _find_child_by_type(self, node, type_name: str) -> Optional[Any]:
        """查找指定类型的直接子节点。"""
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _extract_calls_from_node(self, node) -> List[str]:
        """从 AST 节点中提取所有函数调用。"""
        calls = []
        if node.type == "call_expression":
            func = node.children[0] if node.children else None
            if func and func.type == "identifier":
                calls.append(func.text.decode("utf-8"))

        for child in node.children:
            calls.extend(self._extract_calls_from_node(child))

        return list(dict.fromkeys(calls))  # 去重保序

    def _calc_cyclomatic_complexity(self, func_node) -> int:
        """计算函数的圈复杂度（基于 AST）。"""
        complexity = 1  # 基础复杂度
        decision_nodes = {
            "if_statement", "for_statement", "while_statement",
            "do_statement", "case_statement", "conditional_expression",
            "&&", "||",
        }

        def count_decisions(node):
            nonlocal complexity
            if node.type in decision_nodes:
                complexity += 1
            for child in node.children:
                count_decisions(child)

        count_decisions(func_node)
        return complexity

    def _split_by_function_ts(self, code: str) -> List[Dict[str, Any]]:
        """使用 tree-sitter 按函数拆分代码。"""
        from tree_sitter import Node

        is_cpp = any(ext in code for ext in ['::', '#include <', 'class ', 'template '])
        self._ts_parser.language = self._ts_cpp_lang if is_cpp else self._ts_c_lang
        tree = self._ts_parser.parse(code.encode("utf-8"))

        results = []
        self._collect_functions(tree.root_node, code, results)
        return results

    def _collect_functions(self, node, code: str, results: List[Dict[str, Any]]):
        if node.type == "function_definition":
            name_node = self._find_function_name(node)
            if name_node:
                fname = name_node.text.decode("utf-8")
                body = self._find_child_by_type(node, "compound_statement")
                if body:
                    body_text = body.text.decode("utf-8")
                    sig_start = node.start_byte
                    sig_end = body.start_byte
                    sig_text = code.encode("utf-8")[sig_start:sig_end].decode("utf-8", errors="replace").strip()
                    sig_text = re.sub(r'\s+', ' ', sig_text)

                    results.append({
                        "name": fname,
                        "signature": sig_text,
                        "body": body_text,
                        "char_start": node.start_byte,
                        "char_end": node.end_byte,
                    })

        for child in node.children:
            self._collect_functions(child, code, results)

    # ------------------------------------------------------------------
    # 正则回退分析
    # ------------------------------------------------------------------

    def _extract_call_graph_regex(self, code: str, func_names: List[str]) -> Dict[str, List[str]]:
        """使用正则提取函数调用图。"""
        func_matches = list(self._RE_FUNC_DEF.finditer(code))
        call_graph = {}

        for match in func_matches:
            fname = match.group(1)
            body_start = match.end() - 1
            body_end = self._find_matching_brace(code, body_start)
            if body_end == -1:
                continue

            body = code[body_start:body_end + 1]
            called = []
            for other_name in func_names:
                if other_name == fname:
                    continue
                # 查找函数调用模式: name(
                pattern = re.compile(r'\b' + re.escape(other_name) + r'\s*\(')
                if pattern.search(body):
                    called.append(other_name)
            call_graph[fname] = called

        return call_graph

    def _calc_complexity_regex(self, code: str, func_matches: list) -> Dict[str, int]:
        """使用正则计算各函数圈复杂度。"""
        complexities = {}
        decision_keywords = re.compile(
            r'\b(if|for|while|do|case|&&|\|\|)\b'
        )

        for match in func_matches:
            fname = match.group(1)
            body_start = match.end() - 1
            body_end = self._find_matching_brace(code, body_start)
            if body_end == -1:
                continue

            body = code[body_start:body_end + 1]
            decisions = len(decision_keywords.findall(body))
            complexities[fname] = 1 + decisions

        return complexities

    def _split_by_function_regex(self, code: str) -> List[Dict[str, Any]]:
        """使用正则按函数拆分代码。"""
        results = []
        func_matches = list(self._RE_FUNC_DEF.finditer(code))

        for match in func_matches:
            func_name = match.group(1)
            body_start = match.end() - 1
            body_end = self._find_matching_brace(code, body_start)
            if body_end == -1:
                continue

            body = code[body_start: body_end + 1]
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
        """从 start 位置的 '{' 开始，找到匹配的 '}' 位置。"""
        depth = 0
        i = start
        n = len(code)

        while i < n:
            ch = code[i]

            if ch == '/' and i + 1 < n and code[i + 1] == '/':
                while i < n and code[i] != '\n':
                    i += 1
                continue

            if ch == '/' and i + 1 < n and code[i + 1] == '*':
                i += 2
                while i < n - 1 and not (code[i] == '*' and code[i + 1] == '/'):
                    i += 1
                i += 2
                continue

            if ch == '"':
                i += 1
                while i < n and code[i] != '"':
                    if code[i] == '\\':
                        i += 1
                    i += 1
                i += 1
                continue

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
        """提取函数签名文本。"""
        line_start = code.rfind('\n', 0, match_start)
        line_start = line_start + 1 if line_start != -1 else 0
        sig_text = code[line_start:body_start].strip()
        sig_text = re.sub(r'\s+', ' ', sig_text)
        return sig_text

    def _extract_global_vars(self, code: str) -> List[str]:
        """提取全局变量名，排除函数体内的局部变量。"""
        func_matches = list(self._RE_FUNC_DEF.finditer(code))
        func_ranges = []
        for m in func_matches:
            body_start = m.end() - 1
            body_end = self._find_matching_brace(code, body_start)
            if body_end != -1:
                func_ranges.append((body_start, body_end))

        def inside_function(pos: int) -> bool:
            return any(start <= pos <= end for start, end in func_ranges)

        global_var_names = []
        for m in self._RE_GLOBAL_VAR.finditer(code):
            if not inside_function(m.start()):
                global_var_names.append(m.group(1))

        return global_var_names
