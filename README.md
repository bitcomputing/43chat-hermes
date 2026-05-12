# 43Chat Hermes Adapter

Python Hermes platform adapter for routing 43Chat realtime messages into Hermes sessions.

## Shape

```text
43Chat SSE /open/events/stream
  -> Chat43Adapter.build_message_event()
  -> BasePlatformAdapter.handle_message(MessageEvent)
  -> Hermes gateway/session/agent
  -> Chat43Adapter.send()
  -> 43Chat send_private_message / send_group_message
```

## Install As A Hermes Plugin

Copy or symlink this directory into Hermes' plugin directory:

```text
plugins/platforms/43chat/
```

to:

```text
~/.hermes/plugins/43chat/
```

Install the only runtime dependency:

```bash
pip install aiohttp
```

Configure Hermes:

```yaml
gateway:
  platforms:
    43chat:
      enabled: true
      extra:
        api_key: "sk-..."
        base_url: "https://43chat.cn"
        agent_user_id: "12445"
        owner_user_id: "12445"
        allow_self_messages: false
```

Or use environment variables:

```bash
export CHAT43_API_KEY=sk-...
export CHAT43_AGENT_USER_ID=12445
export CHAT43_OWNER_USER_ID=12445
export CHAT43_ALLOW_ALL_USERS=false
export CHAT43_ALLOWED_USERS=12445,12461
```

Only owner private messages are dispatched as normal Hermes user input. Non-owner private messages, group messages, and group notices are converted into concise 43Chat notifications and skipped from gateway agent dispatch.

## Event Mapping

Private message:

```text
chat_id = private:<user_id>
chat_type = dm
user_id = sender user id
```

Group message:

```text
chat_id = group:<group_id>
chat_type = group
user_id = sender user id
```
