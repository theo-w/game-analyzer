"""富文本 HTML 白名单净化。

用于用户可控的分享报告内容（report_data.html / html_excerpt）：白名单重建，
丢弃 script/style 内容、事件属性与危险 URL scheme，其余标签属性一律剥除。
"""

from __future__ import annotations

import html as _html
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

ALLOWED_TAGS = frozenset({
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u", "s", "code", "pre",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td",
    "a", "img", "span", "div", "small", "sup", "sub",
})
VOID_TAGS = frozenset({"br", "hr", "img"})
# 任意标签都允许的全局属性；其余按标签白名单
ALLOWED_ATTRS: Dict[str, frozenset] = {
    "*": frozenset({"class"}),
    "a": frozenset({"href", "title", "target"}),
    "img": frozenset({"src", "alt", "title"}),
}
# 危险 scheme 一律拒绝；data: 仅放行 data:image/（防止 data:text/html）
_BLOCKED_URL_PREFIXES = ("javascript:", "vbscript:", "data:text", "data:application")
# C0 控制符与 DEL 全部剥除：浏览器 URL 解析会丢弃前导控制符，"\x0ejavascript:" 可还原出
# javascript: scheme 绕过前缀检测（WHATWG URL 规范行为）
_CONTROL_CHARS = {c: None for c in list(range(0x20)) + [0x7F]}


def _safe_url(value: str) -> Optional[str]:
    url = value.translate(_CONTROL_CHARS).strip()
    lowered = url.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "#", "/")):
        return url
    if lowered.startswith("data:image/"):
        return url
    if any(lowered.startswith(p) for p in _BLOCKED_URL_PREFIXES):
        return None
    # 无 scheme 的相对路径放行；含可疑 scheme 写法（如 " javascript:"）已在去空白后拦截
    return url


class _WhitelistParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self._skip_tag: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self._skip_tag:
            return
        if tag in ("script", "style", "iframe", "object", "embed", "template"):
            self._skip_tag = tag
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, frozenset()) | ALLOWED_ATTRS["*"]
        parts = []
        has_blank_target = False
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed or name.startswith("on"):
                continue
            if value is None:
                continue
            if name == "target" and value.strip().lower() == "_blank":
                has_blank_target = True
            if name in ("href", "src"):
                value = _safe_url(value)
                if value is None:
                    continue
            parts.append(f'{name}="{_html.escape(value, quote=True)}"')
        if tag == "a" and has_blank_target:
            # target=_blank 强制补 rel，防反向标签劫持
            parts = [p for p in parts if not p.startswith("rel=")]
            parts.append('rel="noopener noreferrer"')
        attr_str = (" " + " ".join(parts)) if parts else ""
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}{attr_str}>")
        else:
            self.out.append(f"<{tag}{attr_str}>")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)
        elif tag in ALLOWED_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_tag = None
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip_tag and data:
            self.out.append(_html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self.out)


def sanitize_rich_html(raw: str) -> str:
    """按白名单净化富文本 HTML；输入非字符串或为空时原样返回空串。"""
    if not raw or not isinstance(raw, str):
        return ""
    parser = _WhitelistParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        # 解析失败时宁可丢弃格式也不能放行原始输入
        return _html.escape(raw, quote=False)
    return parser.result()
