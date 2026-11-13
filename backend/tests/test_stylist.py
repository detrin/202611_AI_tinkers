import pytest

from backend.app.services.stylist import Stylist, parse_json


@pytest.mark.parametrize("text, expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here it is: {"a": [1, 2]} hope it helps', {"a": [1, 2]}),
    ('[{"id": 0}]', [{"id": 0}]),
])
def test_parse_json_handles_llm_noise(text, expected):
    assert parse_json(text) == expected


def test_parse_json_raises_on_garbage():
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_retries_once_on_bad_json(env):
    replies = iter(["oops", '{"season": "Winter"}'])
    env.chat.complete = lambda prompt, images=(): next(replies)
    assert Stylist(env.chat).color_analysis("data:x") == {"season": "Winter"}


def test_gives_up_after_retries(env):
    env.chat.answers["color"] = "never json"
    with pytest.raises(ValueError):
        Stylist(env.chat, retries=1).color_analysis("data:x")


def test_vision_calls_pass_images_and_text_calls_do_not(env):
    s = Stylist(env.chat)
    s.tag_item("data:img")
    s.profile({"wardrobe": []})
    assert env.chat.calls[0][2] == ["data:img"]
    assert env.chat.calls[1][2] == []


def test_style_summary_uses_at_most_three_images(env):
    Stylist(env.chat).summarise_style("x", [f"u{i}" for i in range(6)])
    assert len(env.chat.calls[0][2]) == 3
