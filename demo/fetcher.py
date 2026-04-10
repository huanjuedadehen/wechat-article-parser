import re
import html
import base64
import aiohttp
from enum import Enum
from urllib.parse import unquote

from markdownify import MarkdownConverter
from bs4 import BeautifulSoup


class ArticleStyle(Enum):
    RICH_TEXT = "rich_text"  # 传统富文本
    REPOST = "repost"  # 转载式
    PLAIN_TEXT = "plain_text"  # 纯文本
    VIDEO_SHARE = "video_share"  # 视频分享
    XIAOHONGSHU_STYLE = "xiaohongshu_style"  # 小红书风格图文


class CustomMarkdownConverter(MarkdownConverter):
    """自定义 Markdown 转换器,减少不必要的换行"""

    def convert_span(self, el, text, parent_tags):
        return text.strip()

    def convert_p(self, el, text, parent_tags):
        # 移除段落中的多余空白
        text = " ".join(text.split())
        return super().convert_p(el, text, parent_tags)


def custom_markdownify(html, **options):
    return CustomMarkdownConverter(**options).convert(html)


class Fetcher:
    def __init__(self, url):
        self.url = url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
        }
        self.mp_id_b64 = ""  # 公众号的唯一标识（Base64 编码了的）
        self.mp_id = 0  # 公众号的唯一标识（解码后的整数形式）
        self.mp_alias = ""
        self.mp_name = ""
        self.mp_img = ""
        self.mp_description = ""

        self.article_id = None
        self.article_msg_id = None  # 这篇文章所在的群发消息 ID（Message ID）
        self.article_idx = None  # 群发图文中的第几篇（从1开始）
        self.article_sn = None  # 文章的签名（用于防伪校验）
        self.article_raw_content = ""
        self.article_md_content = ""
        self.article_title = ""
        self.article_cover_img = ""
        self.article_description = ""
        self.article_type = ""
        self.article_publish_time = None
        self.images = []
        self.article_style = (
            ""  # 文章风格：传统富文本、转载式、纯文本、视频分享、小红书风格图文等
        )

    async def fetch(self) -> None:
        async with aiohttp.ClientSession(
            headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.get(self.url) as response:
                response.raise_for_status()
                self.article_raw_content = await response.text()

        soup = BeautifulSoup(self.article_raw_content, "html.parser")
        self._get_article_id()
        self._get_article_meta_info(soup)
        content = soup.find("div", class_="rich_media_content")
        if content:
            # 传统富文本文章内容
            self.article_style = ArticleStyle.RICH_TEXT.value
            self._get_media_content_meta_info(soup)
            self._get_md_content(content.prettify())
            return

        content = soup.find("div", class_="original_page")
        if content:
            # 转载式的文章内容，例如：https://mp.weixin.qq.com/s/80bysSCadvy9VbaovXBv2g
            self.article_style = ArticleStyle.REPOST.value
            self._get_media_content_meta_info(soup)
            self._get_shared_content(content.prettify())
            return

        content = soup.find("p", id="js_text_desc")
        if content:
            # 纯文本内容，例如：https://mp.weixin.qq.com/s/lVBBIFTnUs24mnmOy6oGLQ
            self.article_style = ArticleStyle.PLAIN_TEXT.value
            self._get_img_swiper_content_meta_info(soup)
            self._get_plain_text_content(soup)
            if len(self.article_title) > 50:
                new_title = self.article_title.split("。")[0]
                if len(new_title) > 50:
                    new_title = self.article_title[:30]
                self.article_title = new_title

        content = soup.find("div", id="js_common_share_desc_wrap")
        if content:
            # 视频分享类的文章内容，例如：https://mp.weixin.qq.com/s/xTEluwBU91Hf4fpwG_UF8g
            self.article_style = ArticleStyle.VIDEO_SHARE.value
            self._get_img_swiper_content_meta_info(soup)
            self._get_plain_text_content(soup)

        content = soup.find("div", class_="share_media_swiper_content")
        if content:
            # 小红书风格图文
            self.article_style = ArticleStyle.XIAOHONGSHU_STYLE.value
            self._get_img_swiper_content_meta_info(soup)
            self._get_img_swiper_content(soup)
            return

    def fetch_result(self) -> bool:
        if not self.mp_id_b64:
            return False
        if not self.mp_name:
            return False
        if not self.article_id:
            return False
        if not self.article_msg_id:
            return False
        if not self.article_idx:
            return False
        if not self.article_sn:
            return False
        if not self.article_raw_content:
            return False
        if not self.article_md_content:
            return False
        if not self.article_title:
            return False
        if not self.article_publish_time:
            return False
        return True

    def _get_media_content_meta_info(self, soup: BeautifulSoup) -> None:
        script_tags = soup.find_all("script", attrs={"type": "text/javascript"})
        for script_tag in script_tags:
            if "var hd_head_img" in script_tag.text:
                match = re.search(r'var hd_head_img = "([^"]+)"', script_tag.text)
                if match:
                    self.mp_img = match.group(1)

                match = re.search(
                    r"var nickname = htmlDecode\((.*)\);", script_tag.text
                )
                if match:
                    self.mp_name = match.group(1).strip('"').strip("'")

                match = re.search(r'var profile_signature = "([^"]+)"', script_tag.text)
                if match:
                    self.mp_description = match.group(1)

                match = re.search(r"alias: '([^']+)'", script_tag.text)
                if match:
                    self.mp_alias = match.group(1)
            elif "var oriCreateTime" in script_tag.text:
                match = re.search(r"var oriCreateTime = '(\d+)'", script_tag.text)
                if match:
                    self.article_publish_time = int(match.group(1))
            elif "window.__allowLoadResFromMp" in script_tag.text:
                pattern = r"var\s+(\w+)\s*=\s*(.*?);"
                result = {}
                for match in re.finditer(pattern, script_tag.text):
                    var_name = match.group(1)
                    expr = match.group(2)
                    string_literals = re.findall(r'"(.*?)"', expr)
                    value = next((s for s in string_literals if s.strip()), "")
                    result[var_name] = value
                self.mp_id_b64 = result["biz"] if "biz" in result else ""
                self.mp_id = (
                    int(base64.b64decode(self.mp_id_b64).decode())
                    if self.mp_id_b64
                    else 0
                )
                self.article_msg_id = int(result["mid"]) if "mid" in result else 0
                self.article_idx = int(result["idx"]) if "idx" in result else 0
                self.article_sn = result["sn"] if "sn" in result else ""

    def _get_img_swiper_content_meta_info(self, soup: BeautifulSoup) -> None:
        script_tags = soup.find_all("script", attrs={"type": "text/javascript"})
        for script_tag in script_tags:
            if "window.__initCgiDataConfig =" in script_tag.text:
                match = re.search(r"d\.hd_head_img.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.mp_img = match.group(1)

                match = re.search(r"d\.nick_name.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.mp_name = match.group(1).strip('"').strip("'")

                match = re.search(r"d\.biz.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.mp_id_b64 = match.group(1)
                    self.mp_id = (
                        int(base64.b64decode(self.mp_id_b64).decode())
                        if self.mp_id_b64
                        else 0
                    )

                match = re.search(r"d\.mid.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.article_msg_id = int(match.group(1))

                match = re.search(r"d\.idx.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.article_idx = int(match.group(1))

                match = re.search(r"d\.sn.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.article_sn = match.group(1)

                match = re.search(r"d\.create_time.*?:\s*'([^']+)'", script_tag.text)
                if match:
                    self.article_publish_time = int(match.group(1))

                if not self.article_id:
                    match = re.search(r"d\.msg_link.*?:\s*'([^']+)'", script_tag.text)
                    if match:
                        url_parts = match.group(1).split("/")
                        if len(url_parts) == 5 and len(url_parts[4]) == 22:
                            self.article_id = url_parts[4]
            elif "window.alias =" in script_tag.text:
                match = re.search(r'window.alias = "([^"]+)"', script_tag.text)
                if match:
                    self.mp_alias = match.group(1)

    def _get_article_id(self) -> None:
        url_parts = self.url.split("/")
        if len(url_parts) == 5 and len(url_parts[4]) == 22:
            self.article_id = url_parts[4]

    def _get_article_meta_info(self, soup: BeautifulSoup) -> None:
        meta_tag = soup.find("meta", attrs={"property": "og:title"})
        if meta_tag:
            content = meta_tag.get("content")
            self.article_title = self._decode_text(content, "clean")

        meta_tag = soup.find("meta", attrs={"property": "og:image"})
        if meta_tag:
            self.article_cover_img = meta_tag.get("content")

        meta_tag = soup.find("meta", attrs={"property": "og:description"})
        if meta_tag:
            content = meta_tag.get("content")
            self.article_description = self._decode_text(content, "clean")
            if len(content) > 2048:
                self.article_description = content[:2048]

        meta_tag = soup.find("meta", attrs={"property": "og:type"})
        if meta_tag:
            self.article_type = meta_tag.get("content")

    def _get_md_content(self, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")

        want_to_delete = []
        image_tags = soup.find_all("img")
        for image_tag in image_tags:
            src = image_tag.get("src")
            if src and src.startswith("http"):
                part = src.split("/")
                src = f"{'/'.join(part[:5])}/640"
                image_tag["src"] = src
                self.images.append(src)
                continue

            src = image_tag.get("data-src")
            if src and src.startswith("http"):
                part = src.split("/")
                src = f"{'/'.join(part[:5])}/640"
                image_tag["src"] = src
                self.images.append(src)
                continue
            want_to_delete.append(image_tag)
        for tag in want_to_delete:
            tag.decompose()

        want_to_delete = []
        svg_tags = soup.find_all("svg")
        for svg_tag in svg_tags:
            svg_style = svg_tag.get("style", "")
            if "background-image" in svg_style:
                match = re.search(r'url\("([^"]+)"\)', svg_style)
                if match:
                    part = match.group(1).split("/")
                    src = f"{'/'.join(part[:5])}/640"
                    new_img_tag = soup.new_tag("img", src=src)
                    svg_tag.replace_with(new_img_tag)
                    self.images.append(src)
                    continue
            # 删除所有其他 SVG 标签
            want_to_delete.append(svg_tag)
        for tag in want_to_delete:
            tag.decompose()

        self.article_md_content = custom_markdownify(soup.prettify())

    def _get_img_swiper_content(self, soup: BeautifulSoup) -> None:
        html_content = ""
        script_tags = soup.find_all("script", attrs={"type": "text/javascript"})
        for script_tag in script_tags:
            if "window.picture_page_info_list =" in script_tag.text:
                images = re.findall(r"cdn_url:\s*'([^']+)'", script_tag.text)
                if images:
                    for image in images:
                        part = image.split("/")
                        self.images.append(f"{'/'.join(part[:5])}/640")

                if self.images:
                    for image in self.images:
                        html_content += f'<img src="{image}" /><br>'

                match = re.search(r'window.desc = "([^"]+)"', script_tag.text)
                if match:
                    content = self._decode_text(match.group(1), "html")
                    html_content += f"<p>{content}</p>"

                if html_content:
                    self.article_md_content = custom_markdownify(html_content)

    def _get_shared_content(self, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")
        content = soup.find("p", id="js_share_notice")
        if not content:
            return

        match = re.search(r'innerHTML = "([^"]+)"', str(content))
        if match:
            content = self._decode_text(match.group(1), "html")
            html_content = f"<p>{content}</p>"

            share_link = soup.find("span", id="js_share_source")
            if share_link:
                href = share_link.get("data-url")
                if href:
                    html_content += f'<p><a href="{href}">查看原文</a></p>'
            self.article_md_content = custom_markdownify(html_content)

    def _get_plain_text_content(self, soup: BeautifulSoup) -> None:
        script_tags = soup.find_all("script", attrs={"type": "text/javascript"})
        for script_tag in script_tags:
            if "var TextContentNoEncode =" in script_tag.text:
                match = re.search(
                    r"var ContentNoEncode = window.a_value_which_never_exists \|\| '([^']+)';",
                    script_tag.text,
                )
                if match:
                    content = self._decode_text(match.group(1), "html")
                    content = unquote(content)
                    self.article_md_content = custom_markdownify(f"<p>{content}</p>")

    def _decode_text(self, text: str, mode: str = "clean") -> str:
        """
        统一的文本解码和清洗方法

        Args:
            text: 原始文本
            mode: 处理模式
                - "clean": 清除换行，压缩空白（用于标题等）
                - "html": 换行转<br>，压缩空白（用于正文内容）
                - "raw": 仅解码，保留原始格式（用于描述等）
        """
        if not text:
            return ""

        # 1. Hex 转义还原 (\xNN -> 字符)
        def hex_to_char(match):
            return chr(int(match.group(1), 16))

        text = re.sub(r"\\x([0-9a-fA-F]{2})", hex_to_char, text)

        # 2. HTML 实体还原
        text = html.unescape(text)
        text = text.replace("&amp;", "&")

        # 3. 根据模式处理换行和空白
        if mode == "clean":
            text = text.replace("\r", "").replace("\n", "")
            text = re.sub(r"\s+", " ", text)
        elif mode == "html":
            text = text.replace("\r", "")
            text = text.replace("\n", "<br>")
            text = re.sub(r"\s+", " ", text)
        # mode == "raw" 不做额外处理

        return text
