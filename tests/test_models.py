"""按展示类型检查解析结果的有效性。"""

from dataclasses import replace

import pytest

from wechat_article_parser import ArticleResult


_COMPLETE = ArticleResult(
    mp_id=123,
    mp_name="测试公众号",
    article_id="ncPoZnxKdvDRLM_s4DBgmA",
    article_msg_id=456,
    article_idx=1,
    article_sn="signature",
    article_title="测试文章",
    article_publish_time=1788860293,
)


@pytest.mark.parametrize("item_show_type", [None, 0, 5, 8, 10, 999])
@pytest.mark.parametrize("markdown", ["", "正文"])
def test_only_video_can_be_valid_without_markdown(
    item_show_type: int | None, markdown: str,
) -> None:
    result = replace(
        _COMPLETE, item_show_type=item_show_type, article_markdown=markdown,
    )

    assert result.is_valid is (bool(markdown) or item_show_type == 5)


@pytest.mark.parametrize(
    ("field_name", "empty_value"),
    [
        ("mp_id", 0),
        ("mp_name", ""),
        ("article_id", ""),
        ("article_msg_id", 0),
        ("article_idx", 0),
        ("article_sn", ""),
        ("article_title", ""),
        ("article_publish_time", 0),
    ],
)
@pytest.mark.parametrize("markdown", ["", "视频附言"])
def test_video_still_requires_all_key_metadata(
    field_name: str, empty_value: str | int, markdown: str,
) -> None:
    result = replace(
        _COMPLETE,
        item_show_type=5,
        article_markdown=markdown,
        **{field_name: empty_value},
    )

    assert not result.is_valid
