import base64

from lumi.llm.base import LLMImagePart, LLMMessage, LLMTextPart, content_to_text
from lumi.llm.minimax import MiniMaxProvider


def test_minimax_serializes_image_parts_as_base64_data_url():
    provider = MiniMaxProvider(api_key="test-key")

    payload_messages = provider._build_messages(
        [
            LLMMessage(
                role="user",
                content=[
                    LLMTextPart(text="Что на фото?"),
                    LLMImagePart(data=b"fake-image", mime_type="image/png", detail="low"),
                ],
            )
        ],
        system="system text",
    )

    assert payload_messages[0] == {"role": "system", "content": "system text"}
    content = payload_messages[1]["content"]
    assert content[0] == {"type": "text", "text": "Что на фото?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["detail"] == "low"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == b"fake-image"


def test_content_to_text_keeps_text_and_redacts_image_bytes():
    text = content_to_text([
        LLMTextPart(text="Опиши"),
        LLMImagePart(data=b"secret-bytes", mime_type="image/jpeg"),
    ])

    assert "Опиши" in text
    assert "image/jpeg" in text
    assert "secret-bytes" not in text
