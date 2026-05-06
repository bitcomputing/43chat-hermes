from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "platforms" / "43chat"
sys.path.insert(0, str(PLUGIN_DIR))

spec = importlib.util.spec_from_file_location("chat43_adapter", PLUGIN_DIR / "adapter.py")
adapter_mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = adapter_mod
spec.loader.exec_module(adapter_mod)


class Config:
    extra = {"api_key": "sk-test", "agent_user_id": "999"}


def test_private_message_maps_to_dm_event():
    adapter = adapter_mod.Chat43Adapter(Config())
    event = adapter.build_message_event(
        {
            "id": "evt-1",
            "event_type": "private_message",
            "data": {"message_id": "msg-1", "from_user_id": 12461, "content": "hello"},
        }
    )

    assert event is not None
    assert "<im_message" in event.text
    assert "hello" in event.text
    assert 'chat_type="direct"' in event.text
    assert 'sender_is_owner="false"' in event.text
    assert event.channel_prompt is not None
    assert "私聊安全补充" in event.channel_prompt
    assert event.message_id == "msg-1"
    assert event.source.chat_id == "private:12461"
    assert event.source.chat_type == "dm"
    assert event.source.user_id == "12461"


def test_group_message_maps_to_group_event():
    adapter = adapter_mod.Chat43Adapter(Config())
    event = adapter.build_message_event(
        {
            "id": "evt-2",
            "event_type": "group_message",
            "data": {
                "message_id": "msg-2",
                "group_id": 100,
                "from_user_id": 12461,
                "content": "hello group",
            },
        }
    )

    assert event is not None
    assert "<im_message" in event.text
    assert 'chat_type="group"' in event.text
    assert event.channel_prompt is not None
    assert "群聊安全补充" in event.channel_prompt
    assert event.source.chat_id == "group:100"
    assert event.source.chat_type == "group"
    assert event.source.user_id == "12461"


def test_self_message_is_filtered():
    adapter = adapter_mod.Chat43Adapter(Config())
    event = adapter.build_message_event(
        {
            "event_type": "private_message",
            "data": {"message_id": "msg-self", "from_user_id": 999, "content": "loop"},
        }
    )

    assert event is None


def test_owner_message_marks_owner_boundary():
    adapter = adapter_mod.Chat43Adapter(Config())
    event = adapter.build_message_event(
        {
            "id": "evt-owner",
            "event_type": "private_message",
            "data": {
                "message_id": "msg-owner",
                "from_user_id": 12461,
                "from_nickname": "owner",
                "content": "do it",
                "is_from_owner": True,
            },
        }
    )

    assert event is not None
    assert 'sender_is_owner="true"' in event.text
    assert "当前发言者标记为主人" in event.channel_prompt
