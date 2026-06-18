"""Chat loop 模型选择：角色专用模型优先于会话默认主模型。"""

from locus_agent.core.loop import _select_chat_model

_IMG_MSG = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ],
    }
]
_TEXT_MSG = [{"role": "user", "content": "hello"}]


def test_vision_model_wins_over_default_when_images_present():
    assert (
        _select_chat_model(
            _IMG_MSG,
            default_model="main-pro",
            main_model="main-pro",
            vision_model="vision-lite",
        )
        == "vision-lite"
    )


def test_default_model_used_for_text_only():
    assert (
        _select_chat_model(
            _TEXT_MSG,
            default_model="main-pro",
            main_model="main-pro",
            vision_model="vision-lite",
        )
        == "main-pro"
    )


def test_main_model_fallback_when_no_default():
    assert (
        _select_chat_model(
            _TEXT_MSG,
            default_model=None,
            main_model="main-pro",
            vision_model="vision-lite",
        )
        == "main-pro"
    )
