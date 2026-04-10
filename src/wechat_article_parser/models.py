from __future__ import annotations

from dataclasses import dataclass, field


class WeChatVerifyError(Exception):
    """微信返回了验证码/人机验证页面，而非文章内容时抛出此异常。"""


@dataclass
class ArticleResult:
    """微信公众号文章的解析结果。"""

    # 公众号信息
    mp_id_b64: str = ""
    mp_id: int = 0
    mp_name: str = ""
    mp_alias: str = ""
    mp_image: str = ""
    mp_description: str = ""

    # 文章信息
    article_id: str = ""
    article_msg_id: int = 0
    article_idx: int = 0
    article_sn: str = ""
    article_title: str = ""
    article_cover_image: str = ""
    article_description: str = ""
    article_markdown: str = ""
    article_publish_time: int = 0

    # 文章中提取的图片列表
    images: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """检查关键字段是否解析成功。"""
        return bool(
            self.mp_id
            and self.mp_name
            and self.article_id
            and self.article_msg_id
            and self.article_idx
            and self.article_sn
            and self.article_title
            and self.article_markdown
            and self.article_publish_time
        )
