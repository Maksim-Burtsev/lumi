from lumi.bot.formatting import telegram_plain_text


def test_telegram_plain_text_strips_markdown_markers():
    raw = """# Возможности

📋 **Задачи**
- Создавать `create_task`

```text
**сырой блок**
```
"""

    assert telegram_plain_text(raw) == (
        "Возможности\n\n"
        "📋 Задачи\n"
        "• Создавать create_task\n\n"
        "сырой блок"
    )
