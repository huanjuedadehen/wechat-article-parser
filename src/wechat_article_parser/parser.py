"""微信公众号文章解析器核心模块。"""

from __future__ import annotations

import base64
import html as html_module
import re
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

from .models import ArticleResult, WeChatVerifyError

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)
_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Markdown 转换器
# ---------------------------------------------------------------------------

class _MarkdownConverter(MarkdownConverter):
    def convert_span(self, el, text, parent_tags):
        return text.strip()

    def convert_p(self, el, text, parent_tags):
        text = " ".join(text.split())
        return super().convert_p(el, text, parent_tags)


def _to_markdown(html: str) -> str:
    return _MarkdownConverter().convert(html)


# ---------------------------------------------------------------------------
# 文本解码辅助函数
# ---------------------------------------------------------------------------

def _strip_html_tags(text: str) -> str:
    """移除文本中的 HTML 标签，只保留纯文本内容。"""
    return BeautifulSoup(text, "html.parser").get_text()


def _decode_hex_escapes(text: str) -> str:
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


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


def _extract_picture_cdn_urls(script_text: str) -> list[str]:
    """从 picture_page_info_list 中只提取正文图片的 cdn_url，排除 watermark_info 和 share_cover 中的。"""
    urls: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"(watermark_info|share_cover)?\s*(?::\s*\{[^}]*?)?\bcdn_url:\s*'([^']*)'", script_text):
        prefix = m.group(1)
        url = m.group(2)
        if prefix or not url:
            continue
        normalized = _normalize_image_url(url)
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


# ---------------------------------------------------------------------------
# 内部提取函数
# ---------------------------------------------------------------------------

def _extract_article_id(url: str) -> str:
    parts = url.split("/")
    if len(parts) == 5 and len(parts[4]) == 22:
        return parts[4]
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


def _extract_rich_text_meta(script_text: str, result: ArticleResult) -> None:
    """从富文本文章的 script 标签中提取元数据。"""
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
    soup = BeautifulSoup(content_tag.prettify(), "html.parser")
    seen: set[str] = set()

    # 处理 <img> 标签
    to_remove = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            normalized = _normalize_image_url(src)
            img["src"] = normalized
            if normalized not in seen:
                seen.add(normalized)
                result.images.append(normalized)
        else:
            to_remove.append(img)
    for tag in to_remove:
        tag.decompose()

    # 处理含有 background-image 的 <svg> 标签
    # 部分文章用嵌套 SVG（外层 SVG > foreignobject > 内层 SVG）承载正文图片，
    # 需从外向内收集所有图片 URL，一次性替换为多个 <img> 标签
    to_remove = []
    for svg in soup.find_all("svg", recursive=True):
        # 跳过已被外层 SVG 处理过的嵌套 SVG（已脱离文档树）
        if not svg.parent:
            continue
        # 跳过嵌套在其他 SVG 内的 SVG，由外层统一处理
        if svg.find_parent("svg"):
            continue

        # 收集本 SVG 及所有后代 SVG 中的 background-image 图片
        all_svgs = [svg] + svg.find_all("svg")
        img_tags = []
        for s in all_svgs:
            style = s.get("style", "")
            if "background-image" not in style:
                continue
            m = re.search(r'url\("([^"]+)"\)', style)
            if not m:
                continue
            normalized = _normalize_image_url(m.group(1))
            img_tags.append(soup.new_tag("img", src=normalized))
            if normalized not in seen:
                seen.add(normalized)
                result.images.append(normalized)

        if img_tags:
            svg.replace_with(*img_tags)
        else:
            to_remove.append(svg)
    for tag in to_remove:
        tag.decompose()

    result.article_markdown = _to_markdown(soup.prettify())


def _extract_repost_content(content_tag: Tag, result: ArticleResult) -> None:
    """从转载式文章中提取内容。"""
    soup = BeautifulSoup(content_tag.prettify(), "html.parser")
    notice = soup.find("p", id="js_share_notice")
    if not notice:
        return

    m = re.search(r'innerHTML = "([^"]+)"', str(notice))
    if not m:
        return

    text = _decode_text(m.group(1), preserve_newlines=True)
    html_content = f"<p>{text}</p>"

    share_link = soup.find("span", id="js_share_source")
    if share_link:
        href = share_link.get("data-url")
        if href:
            html_content += f'<p><a href="{href}">查看原文</a></p>'

    result.article_markdown = _to_markdown(html_content)


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
                result.article_markdown = _to_markdown(f"<p>{text}</p>")


def _extract_swiper_content(soup: BeautifulSoup, result: ArticleResult) -> None:
    """从小红书风格的图片轮播文章中提取内容。"""
    for script in soup.find_all("script", attrs={"type": "text/javascript"}):
        if "window.picture_page_info_list =" not in script.text:
            continue

        result.images = _extract_picture_cdn_urls(script.text)

        html_parts = [f'<img src="{img}" /><br>' for img in result.images]

        m = re.search(r'window.desc = "([^"]+)"', script.text)
        if m:
            text = _decode_text(m.group(1), preserve_newlines=True)
            html_parts.append(f"<p>{text}</p>")

        if html_parts:
            result.article_markdown = _to_markdown("".join(html_parts))


def _extract_fullscreen_content(soup: BeautifulSoup, result: ArticleResult) -> None:
    """从全屏布局文章中提取内容（appmsg_type 10002）。

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
        for field in ("content_noencode", "content"):
            m = re.search(
                rf"{field}:\s*JsDecode\('(.*?)'\)",
                script.text,
                re.DOTALL,
            )
            if m:
                text = _decode_text(m.group(1), preserve_newlines=True)
                text = unquote(text)
                html_parts.append(f"<p>{text}</p>")
                break

        if html_parts:
            result.article_markdown = _to_markdown("".join(html_parts))
        return


# ---------------------------------------------------------------------------
# 主解析流程
# ---------------------------------------------------------------------------

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

    result.article_id = _extract_article_id(url)
    _extract_meta(soup, result)

    scripts = soup.find_all("script", attrs={"type": "text/javascript"})

    # 尝试解析标准富文本文章
    content = soup.find("div", class_="rich_media_content")
    if content:
        for s in scripts:
            _extract_rich_text_meta(s.text, result)
        _extract_rich_media_content(content, result)
        return result

    # 尝试解析转载式文章
    content = soup.find("div", class_="original_page")
    if content:
        for s in scripts:
            _extract_rich_text_meta(s.text, result)
        _extract_repost_content(content, result)
        return result

    # 尝试解析纯文本文章
    content = soup.find("p", id="js_text_desc")
    if content:
        for s in scripts:
            _extract_swiper_meta(s.text, result)
        _extract_plain_text_content(soup, result)
        if result.article_title and len(result.article_title) > 50:
            short = result.article_title.split("。")[0]
            result.article_title = short if len(short) <= 50 else result.article_title[:30]
        return result

    # 尝试解析视频分享类文章
    content = soup.find("div", id="js_common_share_desc_wrap")
    if content:
        for s in scripts:
            _extract_swiper_meta(s.text, result)
        _extract_plain_text_content(soup, result)
        return result

    # 尝试解析小红书风格图片轮播文章
    content = soup.find("div", class_="share_media_swiper_content")
    if content:
        for s in scripts:
            _extract_swiper_meta(s.text, result)
        _extract_swiper_content(soup, result)
        return result

    # 尝试解析全屏布局文章（如短文本帖子，appmsg_type 10002）
    content = soup.find("div", id="js_fullscreen_layout_padding")
    if content:
        for s in scripts:
            _extract_swiper_meta(s.text, result)
        _extract_fullscreen_content(soup, result)
        if result.article_title and len(result.article_title) > 50:
            short = result.article_title.split("。")[0]
            result.article_title = short if len(short) <= 50 else result.article_title[:30]
        return result

    # 兜底：尽可能提取元数据
    for s in scripts:
        _extract_rich_text_meta(s.text, result)
        _extract_swiper_meta(s.text, result)

    return result


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def parse(url: str, *, timeout: int = _TIMEOUT, user_agent: str | None = None) -> ArticleResult:
    """抓取并解析微信公众号文章（同步方式）。

    Args:
        url: 微信文章链接。
        timeout: 请求超时时间（秒）。
        user_agent: 自定义 User-Agent，不传则使用内置默认值。

    Returns:
        包含解析数据的 ArticleResult。
    """
    ua = user_agent or _USER_AGENT
    response = httpx.get(url, headers={"User-Agent": ua}, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return _parse_html(url, response.text)


async def parse_async(url: str, *, timeout: int = _TIMEOUT, user_agent: str | None = None) -> ArticleResult:
    """抓取并解析微信公众号文章（异步方式）。

    Args:
        url: 微信文章链接。
        timeout: 请求超时时间（秒）。
        user_agent: 自定义 User-Agent，不传则使用内置默认值。

    Returns:
        包含解析数据的 ArticleResult。
    """
    ua = user_agent or _USER_AGENT
    async with httpx.AsyncClient(
        headers={"User-Agent": ua},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return _parse_html(url, response.text)
