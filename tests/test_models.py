"""按展示类型检查解析结果的有效性。"""

from dataclasses import asdict, replace
import json

import pytest

from wechat_article_parser import ArticleDisplayType, ArticleResult


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


@pytest.mark.parametrize("display_type", list(ArticleDisplayType))
@pytest.mark.parametrize("markdown", ["", "正文"])
def test_only_video_and_audio_can_be_valid_without_markdown(
    display_type: ArticleDisplayType, markdown: str,
) -> None:
    result = replace(
        _COMPLETE, article_display_type=display_type, article_markdown=markdown,
    )

    assert result.is_valid is (
        bool(markdown) or display_type in (ArticleDisplayType.VIDEO, ArticleDisplayType.AUDIO)
    )


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
@pytest.mark.parametrize("markdown", ["", "媒体附言"])
@pytest.mark.parametrize("display_type", [ArticleDisplayType.VIDEO, ArticleDisplayType.AUDIO])
def test_video_and_audio_still_require_all_key_metadata(
    field_name: str, empty_value: str | int, markdown: str, display_type: ArticleDisplayType,
) -> None:
    result = replace(
        _COMPLETE,
        article_display_type=display_type,
        article_markdown=markdown,
        **{field_name: empty_value},
    )

    assert not result.is_valid


@pytest.mark.parametrize(
    "expected",
    [
        "article",
        "video",
        "audio",
        "image",
        "text",
        "unknown",
    ],
)
def test_display_type_has_semantic_string_values(expected: str) -> None:
    result = ArticleResult(article_display_type=ArticleDisplayType(expected))

    assert result.article_display_type is ArticleDisplayType(expected)
    assert result.article_display_type == expected
    assert str(result.article_display_type) == expected
    assert f"{result.article_display_type:>10}" == f"{expected:>10}"
    assert json.dumps(result.article_display_type) == json.dumps(expected)
    serialized = json.loads(json.dumps(asdict(result)))
    assert serialized["article_display_type"] == expected
    assert serialized["article_item_show_type"] is None


def test_default_display_type_is_unknown() -> None:
    result = ArticleResult()
    assert result.article_display_type is ArticleDisplayType.UNKNOWN
    assert result.article_item_show_type is None
    assert not result.is_valid
