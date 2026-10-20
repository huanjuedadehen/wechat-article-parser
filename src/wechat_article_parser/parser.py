"""微信公众号文章解析器核心模块。"""

from __future__ import annotations

import base64
import html as html_module
import re
from collections import deque
from dataclasses import replace
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

from .models import AccountType, ArticleDisplayType, ArticleResult, ArticleURLType, WeChatVerifyError

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)
_TIMEOUT = 15

# 将字符串和注释作为整体，避免其中的括号干扰图片数组的层级判断。
_JS_DATA_TOKEN_RE = re.compile(
    r"(?P<string>'(?:\\[\s\S]|[^'\\])*'|\"(?:\\[\s\S]|[^\"\\])*\"|`(?:\\[\s\S]|[^`\\])*`)"
    r"|(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)"
    r"|[a-zA-Z_$][\w$]*|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|[^\s]"
)


# ---------------------------------------------------------------------------
# Markdown 转换器
# ---------------------------------------------------------------------------

class _MarkdownConverter(MarkdownConverter):
    def convert_br(self, el, text, parent_tags):
        # 代码中的换行不需要 Markdown 硬换行所用的两个尾随空格。
        if "pre" in parent_tags:
            return "\n"
        return super().convert_br(el, text, parent_tags)

    def convert_pre(self, el, text, parent_tags):
        # BeautifulSoup 已解码 &nbsp;；代码中将其还原为可直接复制的普通空格。
        return super().convert_pre(el, text.replace("\xa0", " "), parent_tags)

    def convert_td(self, el, text, parent_tags):
        # GFM 表格内的管道符即使位于行内代码中，也必须转义。
        return super().convert_td(el, text.replace("|", r"\|"), parent_tags)

    def convert_th(self, el, text, parent_tags):
        return super().convert_th(el, text.replace("|", r"\|"), parent_tags)


def _prepare_markdown_soup(html: str) -> BeautifulSoup:
    """展开编辑器产生的冗余行内标签，避免 Markdown 转换时递归超限。"""
    soup = BeautifulSoup(html, "html.parser")
    styles = {
        "strong": "bold", "b": "bold",
        "em": "italic", "i": "italic",
        "s": "strike", "del": "strike",
    }
    # 显式栈遍历，清理过程本身也不依赖 Python 的递归深度。
    stack = [(soup, frozenset())]
    to_unwrap = []
    while stack:
        node, active_styles = stack.pop()
        style = styles.get(node.name)
        if node.name == "span" or (style and style in active_styles):
            to_unwrap.append(node)
        if style:
            active_styles = active_styles | {style}
        stack.extend(
            (child, active_styles) for child in node.children if isinstance(child, Tag)
        )

    # 先处理内层，保留标签中的文字、链接、图片和它们的原始顺序。
    for node in reversed(to_unwrap):
        node.unwrap()
    return soup


def _to_markdown(html: str) -> str:
    return _MarkdownConverter().convert_soup(_prepare_markdown_soup(html))


def _to_markdown_plain(html: str) -> str:
    """用于纯文本类内容（纯文本/转载/视频/轮播/全屏）的转换。

    这些内容由 <br> 承载换行，使用基础转换器保留换行。
    """
    return MarkdownConverter().convert_soup(_prepare_markdown_soup(html))


# ---------------------------------------------------------------------------
# 文本解码辅助函数
# ---------------------------------------------------------------------------

def _strip_html_tags(text: str) -> str:
    """移除文本中的 HTML 标签，只保留纯文本内容。"""
    return BeautifulSoup(text, "html.parser").get_text()


def _decode_hex_escapes(text: str) -> str:
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


def _decode_js_string(text: str) -> str:
    """解码 JS 字符串转义，保留 HTML 实体、百分号和正文中的空白。"""
    escapes = {
        "n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v",
        "0": "\0", "\n": "", "\r": "", "\r\n": "",
    }

    def decode(match: re.Match[str]) -> str:
        if match[1] or match[2]:
            return chr(int(match[1] or match[2], 16))
        return escapes.get(match[3], match[3])

    return re.sub(r"\\(?:x([\da-fA-F]{2})|u([\da-fA-F]{4})|(\r\n|[\s\S]))", decode, text)


def _decode_text(text: str, *, preserve_newlines: bool = False) -> str:
    if not text:
        return ""
    text = _decode_hex_escapes(text)
    text = html_module.unescape(text)
    text = text.replace("&amp;", "&")
    if preserve_newlines:
        text = text.replace("\r", "").replace("\n", "<br>")
    else:
        text = text.replace("\r", "").replace("\n", "")
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------------
# 图片链接标准化
# ---------------------------------------------------------------------------

def _normalize_image_url(url: str) -> str:
    """将微信图片链接标准化为 640px 宽度版本。"""
    parts = url.split("/")
    if len(parts) >= 5:
        return f"{'/'.join(parts[:5])}/640"
    return url


def _service_type_to_account_type(value: str) -> AccountType:
    """映射 WeChat new_service_type 到账号类型：0/1 → 订阅号，2 → 服务号。"""
    if value in ("0", "1"):
        return AccountType.SUBSCRIPTION
    if value == "2":
        return AccountType.SERVICE
    return AccountType.UNKNOWN


def _extract_picture_cdn_urls(script_text: str) -> list[str]:
    """读取图片数组条目的直接 cdn_url，排除数组外和嵌套对象中的地址。

    支持 window.picture_page_info_list = [...] 和 cgiDataNew 中的同名属性。
    页面数据是含表达式的 JS 对象字面量，因此只跟踪结构，不执行脚本。
    """
    if "picture_page_info_list" not in script_text:
        return []

    urls: list[str] = []
    seen: set[str] = set()
    stack: list[str] = []
    array_urls: list[str] = []
    previous = before_previous = ""
    for match in _JS_DATA_TOKEN_RE.finditer(script_text):
        if match.lastgroup == "comment":
            continue
        token = match.group()
        is_string = match.lastgroup == "string"

        if not stack:
            if (
                token == "["
                and previous in (":", "=")
                and before_previous == "picture_page_info_list"
            ):
                stack.append(token)
        elif token in ("[", "{"):
            stack.append(token)
        elif token in ("]", "}"):
            if stack[-1] != {"]": "[", "}": "{"}[token]:
                stack.clear()
                array_urls.clear()
            else:
                stack.pop()
                if not stack:
                    # 只提交完整数组，保留图片顺序并去重。
                    for url in array_urls:
                        if url not in seen:
                            seen.add(url)
                            urls.append(url)
                    array_urls.clear()
        elif (
            stack == ["[", "{"]
            and before_previous == "cdn_url"
            and previous == ":"
            and is_string
            and token[0] in ("'", '"')
        ):
            url = _decode_text(token[1:-1])
            if url:
                array_urls.append(_normalize_image_url(url))

        before_previous, previous = previous, token[1:-1] if is_string else token
    return urls


# ---------------------------------------------------------------------------
# 内部提取函数
# ---------------------------------------------------------------------------

def _extract_article_url_type(url: str) -> ArticleURLType:
    """识别输入链接；长链接的五个必需参数均须存在且非空白。"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ArticleURLType.UNKNOWN
    if (
        parts.scheme not in ("http", "https")
        or parts.hostname != "mp.weixin.qq.com"
        or parts.username is not None
        or parts.password is not None
    ):
        return ArticleURLType.UNKNOWN
    if re.fullmatch(r"/s/[A-Za-z0-9_-]{22}", parts.path):
        return ArticleURLType.SHORT
    if parts.path == "/s":
        params = parse_qs(parts.query, keep_blank_values=True)
        required = ("__biz", "mid", "idx", "sn", "chksm")
        # 保留空值，重复参数中出现空值也不能放行。
        if all(key in params and all(value.strip() for value in params[key]) for key in required):
            return ArticleURLType.LONG
    return ArticleURLType.UNKNOWN


def _extract_article_id(url: str) -> str:
    if _extract_article_url_type(url) == ArticleURLType.SHORT:
        return urlsplit(url).path.rsplit("/", 1)[1]
    return ""


def _extract_meta(soup: BeautifulSoup, result: ArticleResult) -> None:
    for prop, attr in [
        ("og:title", "article_title"),
        ("og:image", "article_cover_image"),
        ("og:description", "article_description"),
    ]:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            value = tag["content"]
            if attr != "article_cover_image":
                value = _decode_text(value)
                value = _strip_html_tags(value)
            if attr == "article_description" and len(value) > 2048:
                value = value[:2048]
            setattr(result, attr, value)


def _extract_item_show_type(scripts: list[Tag]) -> int | None:
    """只读取当前文章的全局类型赋值；0 是有效类型，缺失时返回 None。"""
    for script in scripts:
        if "item_show_type" not in script.text:
            continue
        history: deque[str] = deque(maxlen=5)
        brace_depth = 0
        for match in _JS_DATA_TOKEN_RE.finditer(script.text):
            if match.lastgroup == "comment":
                continue
            token = match.group()
            previous = tuple(history)
            is_global_var = (
                brace_depth == 0
                and previous[-3:] == ("var", "item_show_type", "=")
            )
            is_window_assignment = (
                previous[-4:] == ("window", ".", "item_show_type", "=")
                and (len(previous) < 5 or previous[-5] != ".")
            )
            if is_global_var or is_window_assignment:
                value = token[1:-1] if token.startswith(("'", '"')) else token
                if re.fullmatch(r"[0-9]+", value):
                    return int(value)
            if token == "{":
                brace_depth += 1
            elif token == "}":
                brace_depth -= 1
            history.append(token)
    return None


def _extract_is_paid(soup: BeautifulSoup, scripts: list[Tag]) -> bool:
    """识别当前文章的付费标记，排除正文外占位符和嵌套推荐文章的数据。"""
    if soup.select_one(
        "div.rich_media_content mp-pay-preview-filter, "
        "div.original_page mp-pay-preview-filter"
    ) is not None:
        return True

    for script in scripts:
        if "is_pay_subscribe" not in script.text:
            continue
        tokens = [
            match.group() for match in _JS_DATA_TOKEN_RE.finditer(script.text)
            if match.lastgroup != "comment"
        ]
        stack: list[str] = []
        cgi_depth: int | None = None
        for i, token in enumerate(tokens):
            if token == "{":
                if (
                    tokens[max(0, i - 4):i] == ["window", ".", "cgiDataNew", "="]
                    and (i < 5 or tokens[i - 5] != ".")
                ):
                    cgi_depth = len(stack) + 1
                stack.append(token)
            elif token in ("[", "("):
                stack.append(token)
            elif token in ("}", "]", ")"):
                if stack and stack[-1] == {"}": "{", "]": "[", ")": "("}[token]:
                    if len(stack) == cgi_depth:
                        cgi_depth = None
                    stack.pop()
            if token.strip("\"'") != "is_pay_subscribe":
                continue
            is_global = token == "is_pay_subscribe" and (
                (not stack and i > 0 and tokens[i - 1] in ("var", "let", "const"))
                or (
                    tokens[max(0, i - 2):i] == ["window", "."]
                    and (i < 3 or tokens[i - 3] != ".")
                )
            )
            is_cgi_field = (
                cgi_depth is not None and len(stack) == cgi_depth
                and i > 0 and tokens[i - 1] in ("{", ",")
            )
            separator = tokens[i + 1:i + 2]
            if not (
                (is_global and separator == ["="])
                or (is_cgi_field and separator == [":"])
            ):
                continue
            # 仅识别页面使用的字面量及乘 1 转数值写法，不执行 JS 表达式。
            value = tokens[i + 2:i + 3]
            if value not in (["1"], ["'1'"], ['"1"'], ["true"]):
                continue
            end = i + 3
            if value != ["true"] and tokens[end:end + 2] == ["*", "1"]:
                end += 2
            if end == len(tokens) or tokens[end] in (",", ";", "}"):
                return True
    return False


def _extract_user_name(scripts: list[Tag]) -> str:
    """读取全局 user_name，缺失时读取 window.cgiDataNew 的直接属性。

    文章元数据脚本中该变量位于 nickname、ct 附近；不依赖行号或账号值。
    使用词法标记跳过注释和字符串，不执行页面脚本。
    """
    for script in scripts:
        if "user_name" not in script.text:
            continue
        history: deque[str] = deque(maxlen=4)
        brace_depth = 0
        for match in _JS_DATA_TOKEN_RE.finditer(script.text):
            if match.lastgroup == "comment":
                continue
            token = match.group()
            previous = tuple(history)
            if (
                brace_depth == 0
                and token == ";"
                and previous[:3] == ("var", "user_name", "=")
                and len(previous) == 4
                and previous[3].startswith(("'", '"'))
            ):
                value = _decode_text(previous[3][1:-1])
                if value:
                    return value
            if token == "{":
                brace_depth += 1
            elif token == "}":
                brace_depth -= 1
            history.append(token)
    return _extract_cgi_user_name(scripts)


def _extract_cgi_user_name(scripts: list[Tag]) -> str:
    """从当前文章的 cgiDataNew 对象中读取 user_name，排除嵌套账号。"""
    return _decode_text(_extract_cgi_string(scripts, "user_name"))


def _extract_cgi_string(scripts: list[Tag], field: str) -> str:
    """读取当前 cgiDataNew 的直接字符串属性，不执行表达式或读取嵌套对象。"""
    for script in scripts:
        if "cgiDataNew" not in script.text or field not in script.text:
            continue
        history: deque[str] = deque(maxlen=5)
        stack: list[str] = []
        for match in _JS_DATA_TOKEN_RE.finditer(script.text):
            if match.lastgroup == "comment":
                continue
            token = match.group()
            previous = tuple(history)
            if not stack:
                if (
                    token == "{"
                    and previous[-4:] == ("window", ".", "cgiDataNew", "=")
                    and (len(previous) < 5 or previous[-5] != ".")
                ):
                    stack.append(token)
            else:
                # 只接受完整的字符串属性值，不读取表达式或嵌套对象的值。
                if (
                    stack == ["{"]
                    and token in (",", "}")
                    and len(previous) >= 4
                    and previous[-4] in ("{", ",")
                    and previous[-3].strip("\"'") == field
                    and previous[-2] == ":"
                    and previous[-1].startswith(("'", '"'))
                ):
                    value = previous[-1][1:-1]
                    if value.strip():
                        return value
                if token in ("{", "["):
                    stack.append(token)
                elif token in ("}", "]"):
                    if stack[-1] == {"}": "{", "]": "["}[token]:
                        stack.pop()
                    else:
                        stack.clear()
            history.append(token)
    return ""


def _extract_account_type(script_text: str, result: ArticleResult) -> None:
    """从 new_service_type 中提取账号类型：0/1 → 订阅号，2 → 服务号。"""
    if result.mp_account_type:
        return
    m = re.search(r"new_service_type:\s*'(\d+)'", script_text)
    if m:
        account_type = _service_type_to_account_type(m.group(1))
        if account_type != AccountType.UNKNOWN:
            result.mp_account_type = account_type


def _extract_rich_text_meta(script_text: str, result: ArticleResult) -> None:
    """从富文本文章的 script 标签中提取元数据。"""
    _extract_account_type(script_text, result)

    if "var hd_head_img" in script_text:
        m = re.search(r'var hd_head_img = "([^"]+)"', script_text)
        if m:
            result.mp_image = m.group(1)

        m = re.search(r"var nickname = htmlDecode\((.*)\);", script_text)
        if m:
            result.mp_name = m.group(1).strip('"').strip("'")

        m = re.search(r'var profile_signature = "([^"]+)"', script_text)
        if m:
            result.mp_description = m.group(1)

        m = re.search(r"alias: '([^']+)'", script_text)
        if m:
            result.mp_alias = m.group(1)

    if "var oriCreateTime" in script_text:
        m = re.search(r"var oriCreateTime = '(\d+)'", script_text)
        if m:
            result.article_publish_time = int(m.group(1))

    if "window.__allowLoadResFromMp" in script_text:
        variables: dict[str, str] = {}
        for m in re.finditer(r"var\s+(\w+)\s*=\s*(.*?);", script_text):
            literals = re.findall(r'"(.*?)"', m.group(2))
            variables[m.group(1)] = next((s for s in literals if s.strip()), "")

        biz = variables.get("biz", "")
        if biz:
            result.mp_id_b64 = biz
            try:
                result.mp_id = int(base64.b64decode(biz).decode())
            except Exception:
                pass
        result.article_msg_id = int(variables["mid"]) if variables.get("mid") else 0
        result.article_idx = int(variables["idx"]) if variables.get("idx") else 0
        result.article_sn = variables.get("sn", "")


def _extract_swiper_meta(script_text: str, result: ArticleResult) -> None:
    """从图片轮播 / 纯文本 / 视频分享页面的 script 标签中提取元数据。"""
    _extract_account_type(script_text, result)

    if "window.__initCgiDataConfig =" in script_text:
        m = re.search(r"d\.hd_head_img.*?:\s*'([^']+)'", script_text)
        if m:
            result.mp_image = m.group(1)

        m = re.search(r"d\.nick_name.*?:\s*'([^']+)'", script_text)
        if m:
            result.mp_name = m.group(1).strip('"').strip("'")

        m = re.search(r"d\.biz.*?:\s*'([^']+)'", script_text)
        if m:
            biz = m.group(1)
            result.mp_id_b64 = biz
            try:
                result.mp_id = int(base64.b64decode(biz).decode())
            except Exception:
                pass

        m = re.search(r"d\.mid.*?:\s*'([^']+)'", script_text)
        if m:
            result.article_msg_id = int(m.group(1))

        m = re.search(r"d\.idx.*?:\s*'([^']+)'", script_text)
        if m:
            result.article_idx = int(m.group(1))

        m = re.search(r"d\.sn.*?:\s*'([^']+)'", script_text)
        if m:
            result.article_sn = m.group(1)

        m = re.search(r"d\.create_time.*?:\s*'([^']+)'", script_text)
        if m:
            result.article_publish_time = int(m.group(1))

        if not result.article_id:
            m = re.search(r"d\.msg_link.*?:\s*'([^']+)'", script_text)
            if m:
                parts = m.group(1).split("/")
                if len(parts) == 5 and len(parts[4]) == 22:
                    result.article_id = parts[4]

    if "window.alias =" in script_text:
        m = re.search(r'window.alias = "([^"]+)"', script_text)
        if m:
            result.mp_alias = m.group(1)


# ---------------------------------------------------------------------------
# 内容提取
# ---------------------------------------------------------------------------

def _extract_rich_media_content(content_tag: Tag, result: ArticleResult) -> None:
    """将 rich_media_content 区块转换为 Markdown。"""
    # prettify 会在行内标签之间插入空白，改变代码和引用链接的内容。
    soup = BeautifulSoup(str(content_tag), "html.parser")
    if soup.find("mp-pay-preview-filter") is not None:
        result.article_is_paid = True
    has_video = soup.select_one(
        'mp-common-videosnap[data-type="video"], iframe.video_iframe, iframe.wx_video_iframe'
    ) is not None

    # 原生公众号卡片的正文保存在属性中，转换为“名称 + 简介”的独立段落。
    for profile in soup.find_all("mp-common-profile"):
        nickname = profile.get("data-nickname", "").strip()
        signature = profile.get("data-signature", "").strip()
        if not nickname and not signature:
            continue
        paragraph = soup.new_tag("p")
        if nickname:
            name = soup.new_tag("strong")
            name.string = nickname
            paragraph.append(name)
        if signature:
            if nickname:
                paragraph.append("：")
            paragraph.append(signature)
        profile.replace_with(paragraph)

    # 小程序卡片只保留公开文字和查看提示，不收集封面、头像或内部路径。
    for card in soup.find_all("mp-common-miniprogram"):
        title = card.get("data-miniprogram-title", "").strip()
        nickname = card.get("data-miniprogram-nickname", "").strip()
        paragraphs = []
        if title:
            paragraph = soup.new_tag("p")
            heading = soup.new_tag("strong")
            heading.string = title
            paragraph.append(heading)
            paragraphs.append(paragraph)
        if nickname:
            paragraph = soup.new_tag("p")
            paragraph.string = f"小程序：{nickname}"
            paragraphs.append(paragraph)
        notice = soup.new_tag("p")
        notice.string = "请在微信中打开小程序查看内容。"
        paragraphs.append(notice)
        card.replace_with(*paragraphs)

    # 处理 <img> 标签
    to_remove = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            normalized = _normalize_image_url(src)
            img["src"] = normalized
        else:
            to_remove.append(img)
    for tag in to_remove:
        tag.decompose()

    # SVG 可通过 background-image 或 foreignObject 内的 <img> 承载正文图片。
    # 按文档顺序收集两种图片，再统一替换外层 SVG，避免删除内部正文图片。
    to_remove = []
    for svg in soup.find_all("svg", recursive=True):
        # 跳过已被外层 SVG 处理过的嵌套 SVG（已脱离文档树）
        if not svg.parent:
            continue
        # 跳过嵌套在其他 SVG 内的 SVG，由外层统一处理
        if svg.find_parent("svg"):
            continue

        # 包含所有嵌套 SVG 和普通图片，保留正文中的重复图片及 alt 文本。
        image_elements = [svg] + svg.find_all(["svg", "img"])
        img_tags = []
        for element in image_elements:
            if element.name == "img":
                img_tags.append(soup.new_tag("img", attrs=element.attrs.copy()))
                continue
            style = element.get("style", "")
            if "background-image" not in style:
                continue
            m = re.search(r'url\("([^"]+)"\)', style)
            if not m:
                continue
            normalized = _normalize_image_url(m.group(1))
            img_tags.append(soup.new_tag("img", src=normalized))

        if img_tags:
            svg.replace_with(*img_tags)
        else:
            to_remove.append(svg)
    for tag in to_remove:
        tag.decompose()

    # 从最终正文收集图片，使列表顺序与 Markdown 一致，并只对列表去重。
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = img["src"]
        if src not in seen:
            seen.add(src)
            result.images.append(src)

    result.article_markdown = _to_markdown(str(soup))
    if not result.article_markdown.strip():
        if soup.find("mp-pay-preview-filter") is not None:
            result.article_markdown = "这是一篇付费内容，正文需付费后查看。"
        elif has_video:
            result.article_markdown = "这是一篇纯视频内容。"
        elif soup.find("mp-common-cpsad") is not None:
            result.article_markdown = "这是一篇商品推荐内容。"


def _extract_repost_content(
    content_tag: Tag, scripts: list[Tag], result: ArticleResult,
) -> None:
    """读取转载附言、cgiDataNew 中的富文本正文和原文链接。"""
    soup = BeautifulSoup(str(content_tag), "html.parser")
    parts: list[str] = []
    notice = soup.find("p", id="js_share_notice")
    if notice:
        m = re.search(
            r'''innerHTML\s*=\s*("(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*')''',
            str(notice),
        )
        if m:
            text = _decode_text(_decode_js_string(m[1][1:-1]), preserve_newlines=True)
            notice_markdown = _to_markdown_plain(f"<p>{text}</p>")
        else:
            for script in notice.find_all("script"):
                script.decompose()
            notice_markdown = _to_markdown_plain(str(notice))
        if notice_markdown.strip():
            parts.append(notice_markdown.strip())

    for field in ("content_noencode", "content"):
        body = _extract_cgi_string(scripts, field)
        if body:
            # 与普通富文本共用图片和 Markdown 处理，避免 data-src 变成空图片链接。
            body_soup = BeautifulSoup(_decode_js_string(body), "html.parser")
            _extract_rich_media_content(body_soup, result)
            if result.article_markdown.strip():
                parts.append(result.article_markdown.strip())
                break

    if not parts:
        return

    share_link = soup.find("span", id="js_share_source")
    if share_link:
        href = share_link.get("data-url")
        if href:
            link = soup.new_tag("a", href=href)
            link.string = "查看原文"
            parts.append(_to_markdown_plain(str(link)))

    result.article_markdown = "\n\n".join(parts)


def _extract_plain_text_content(soup: BeautifulSoup, result: ArticleResult) -> None:
    """从纯文本文章中提取内容。"""
    for script in soup.find_all("script", attrs={"type": "text/javascript"}):
        if "var TextContentNoEncode =" in script.text:
            m = re.search(
                r"var ContentNoEncode = window\.a_value_which_never_exists \|\| '([^']+)';",
                script.text,
            )
            if m:
                text = _decode_text(m.group(1), preserve_newlines=True)
                text = unquote(text)
                result.article_markdown = _to_markdown_plain(f"<p>{text}</p>")


def _extract_swiper_content(soup: BeautifulSoup, result: ArticleResult) -> None:
    """从小红书风格的图片轮播文章中提取内容。"""
    images: list[str] = []
    seen: set[str] = set()
    description = ""
    for script in soup.find_all("script", attrs={"type": "text/javascript"}):
        # 图片数据和 window.desc 可能位于不同的 script，分别收集。
        for url in _extract_picture_cdn_urls(script.text):
            if url not in seen:
                seen.add(url)
                images.append(url)

        m = re.search(r'window.desc = "([^"]+)"', script.text)
        if m:
            description = _decode_text(m.group(1), preserve_newlines=True)

    result.images = images
    html_parts = [f'<img src="{img}" /><br>' for img in images]
    if description:
        html_parts.append(f"<p>{description}</p>")
    if html_parts:
        result.article_markdown = _to_markdown_plain("".join(html_parts))


def _extract_fullscreen_content(soup: BeautifulSoup, result: ArticleResult) -> None:
    """从全屏布局文字消息中提取内容。

    此类文章的文本存储在 text_page_info.content 中，通过 JsDecode() 编码；
    图片存储在 picture_page_info_list 的 cdn_url 字段中。
    """
    for script in soup.find_all("script", attrs={"type": "text/javascript"}):
        if "picture_page_info_list" not in script.text:
            continue

        html_parts: list[str] = []

        # 从 picture_page_info_list 中提取图片
        result.images = _extract_picture_cdn_urls(script.text)
        for img in result.images:
            html_parts.append(f'<img src="{img}" /><br>')

        # 从 text_page_info.content_noencode 或 content 中提取文本
        # 文本可能被 JsDecode('...') 包裹，也可能是裸的单引号字符串，两种都要兼容
        for field in ("content_noencode", "content"):
            m = re.search(
                rf"{field}:\s*(?:JsDecode\(\s*)?'(.*?)'",
                script.text,
                re.DOTALL,
            )
            if m:
                text = _decode_text(m.group(1), preserve_newlines=True)
                text = unquote(text)
                html_parts.append(f"<p>{text}</p>")
                break

        if html_parts:
            result.article_markdown = _to_markdown_plain("".join(html_parts))
        return


# ---------------------------------------------------------------------------
# 主解析流程
# ---------------------------------------------------------------------------

# 顺序与原有 HTML 判断流程一致，用于未知类型及提取失败时的兜底。
_CONTENT_SELECTORS = {
    "rich_text": "div.rich_media_content",
    "repost": "div.original_page",
    "plain_text": "p#js_text_desc",
    "video": "div#js_common_share_desc_wrap",
    "swiper": "div.share_media_swiper_content",
    "fullscreen": "div#js_fullscreen_layout_padding",
}
_ITEM_SHOW_TYPE_BRANCHES = {
    0: ("rich_text", "repost"),
    5: ("video",),
    7: ("video",),  # 音频分享复用视频分享的文字附言提取。
    8: ("swiper",),
    10: ("plain_text", "fullscreen"),
}
_ARTICLE_DISPLAY_TYPES = {
    0: ArticleDisplayType.ARTICLE,
    5: ArticleDisplayType.VIDEO,
    7: ArticleDisplayType.AUDIO,
    8: ArticleDisplayType.IMAGE,
    10: ArticleDisplayType.TEXT,
}


def _try_content_branch(
    branch: str,
    soup: BeautifulSoup,
    scripts: list[Tag],
    result: ArticleResult,
    *,
    require_html: bool,
) -> ArticleResult | None:
    content = soup.select_one(_CONTENT_SELECTORS[branch])
    rich_text_template = branch in ("rich_text", "repost")
    if content is None and (require_html or rich_text_template):
        return None

    # 失败分支的图片、元数据和标题处理不能污染后续分支。
    candidate = replace(result, images=result.images.copy())
    extract_meta = _extract_rich_text_meta if rich_text_template else _extract_swiper_meta
    for script in scripts:
        extract_meta(script.text, candidate)

    if branch == "rich_text":
        _extract_rich_media_content(content, candidate)
    elif branch == "repost":
        _extract_repost_content(content, scripts, candidate)
    elif branch in ("plain_text", "video"):
        _extract_plain_text_content(soup, candidate)
    elif branch == "swiper":
        _extract_swiper_content(soup, candidate)
    elif branch == "fullscreen":
        _extract_fullscreen_content(soup, candidate)

    if not candidate.article_markdown.strip():
        return None
    if branch in ("plain_text", "fullscreen") and len(candidate.article_title) > 50:
        short = candidate.article_title.split("。")[0]
        candidate.article_title = short if len(short) <= 50 else candidate.article_title[:30]
    return candidate


def _parse_html(url: str, html: str) -> ArticleResult:
    """将原始 HTML 解析为 ArticleResult。"""
    # 检测微信验证码/人机验证页面
    if "secitptpage/template/verify.js" in html or "register_code" in html[:3000]:
        raise WeChatVerifyError(
            f"WeChat returned a verification page for {url}. "
            "This usually means the IP has been rate-limited. "
            "Try again later or use a different IP."
        )

    result = ArticleResult()
    soup = BeautifulSoup(html, "html.parser")

    result.article_url_type = _extract_article_url_type(url)
    result.article_id = _extract_article_id(url)
    _extract_meta(soup, result)

    scripts = soup.find_all("script", attrs={"type": "text/javascript"})

    all_scripts = soup.find_all("script")
    result.mp_user_name = _extract_user_name(all_scripts)
    result.article_is_paid = _extract_is_paid(soup, all_scripts)
    item_show_type = _extract_item_show_type(scripts)
    result.article_item_show_type = item_show_type
    result.article_display_type = _ARTICLE_DISPLAY_TYPES.get(
        item_show_type, ArticleDisplayType.UNKNOWN,
    )
    preferred = _ITEM_SHOW_TYPE_BRANCHES.get(item_show_type, ())
    attempted: set[str] = set()
    for branch in (*preferred, *_CONTENT_SELECTORS):
        if branch in attempted:
            continue
        attempted.add(branch)
        # 已知类型先用对应的 DOM 或脚本数据细分模板；失败后按原有 HTML 顺序兜底。
        candidate = _try_content_branch(
            branch,
            soup,
            scripts,
            result,
            require_html=branch not in preferred,
        )
        if candidate is not None:
            return candidate

    # 兜底：尽可能提取元数据
    for s in scripts:
        _extract_rich_text_meta(s.text, result)
        _extract_swiper_meta(s.text, result)

    return result


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def parse(
    url: str,
    *,
    timeout: int = _TIMEOUT,
    user_agent: str | None = None,
    proxy: str | None = None,
    include_raw_html: bool = False,
) -> ArticleResult:
    """抓取并解析微信公众号文章（同步方式）。

    Args:
        url: 微信文章链接。
        timeout: 请求超时时间（秒）。
        user_agent: 自定义 User-Agent，不传则使用内置默认值。
        proxy: HTTP/HTTPS 代理地址，例如 "http://user:pass@host:port"，不传则直连。
        include_raw_html: 是否在结果中返回原始 HTML 网页源代码，默认不返回。

    Returns:
        包含解析数据的 ArticleResult。
    """
    ua = user_agent or _USER_AGENT
    with httpx.Client(
        headers={"User-Agent": ua},
        timeout=timeout,
        follow_redirects=True,
        proxy=proxy,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        result = _parse_html(url, response.text)
        if include_raw_html:
            result.raw_html = response.text
        return result


async def parse_async(
    url: str,
    *,
    timeout: int = _TIMEOUT,
    user_agent: str | None = None,
    proxy: str | None = None,
    include_raw_html: bool = False,
) -> ArticleResult:
    """抓取并解析微信公众号文章（异步方式）。

    Args:
        url: 微信文章链接。
        timeout: 请求超时时间（秒）。
        user_agent: 自定义 User-Agent，不传则使用内置默认值。
        proxy: HTTP/HTTPS 代理地址，例如 "http://user:pass@host:port"，不传则直连。
        include_raw_html: 是否在结果中返回原始 HTML 网页源代码，默认不返回。

    Returns:
        包含解析数据的 ArticleResult。
    """
    ua = user_agent or _USER_AGENT
    async with httpx.AsyncClient(
        headers={"User-Agent": ua},
        timeout=timeout,
        follow_redirects=True,
        proxy=proxy,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        result = _parse_html(url, response.text)
        if include_raw_html:
            result.raw_html = response.text
        return result
