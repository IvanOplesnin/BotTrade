from types import SimpleNamespace

import pytest

from bots.tg_bot.messages.formatting import split_message
from bots.tg_bot.sending import answer_text, send_text


class FakeMessage:
    def __init__(self):
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append({"text": text, "kwargs": kwargs})


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})


def test_split_message_prefers_paragraph_boundaries():
    chunks = split_message("one\n\nsecond block\n\nthird", limit=18)

    assert chunks == ["one\n\n", "second block\n\n", "third"]


def test_split_message_falls_back_to_line_boundaries():
    chunks = split_message("header\nline-1\nline-2\nline-3", limit=14)

    assert chunks == ["header\nline-1\n", "line-2\nline-3"]


def test_split_message_hard_splits_oversized_line():
    chunks = split_message("abcdef", limit=2)

    assert chunks == ["ab", "cd", "ef"]


@pytest.mark.asyncio
async def test_answer_text_sends_reply_markup_only_with_last_chunk():
    message = FakeMessage()
    markup = SimpleNamespace(name="keyboard")

    await answer_text(message, "one\n\ntwo\n\nthree", limit=8, reply_markup=markup)

    assert [item["text"] for item in message.answers] == ["one\n\n", "two\n\n", "three"]
    assert message.answers[0]["kwargs"] == {}
    assert message.answers[1]["kwargs"] == {}
    assert message.answers[2]["kwargs"] == {"reply_markup": markup}


@pytest.mark.asyncio
async def test_send_text_passes_common_kwargs_to_each_chunk():
    bot = FakeBot()
    option = SimpleNamespace(is_disabled=True)

    await send_text(bot, 123, "one\n\ntwo", limit=6, link_preview_options=option)

    assert [item["text"] for item in bot.sent] == ["one\n\n", "two"]
    assert bot.sent[0]["kwargs"] == {"link_preview_options": option}
    assert bot.sent[1]["kwargs"] == {"link_preview_options": option}
