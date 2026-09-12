from app.core.config import Settings, settings
from app.core.llm import _sync_http_client, chat_model


def test_default_llm_model_is_minimax_m3() -> None:
    assert Settings.model_fields["llm_model"].default == "MiniMax-M3"


def test_http_client_does_not_accept_brotli() -> None:
    encoding = str(_sync_http_client().headers.get("Accept-Encoding") or "")
    assert "gzip" in encoding
    assert "br" not in encoding.lower()


def test_chat_model_uses_shared_http_client_and_configured_model() -> None:
    model = chat_model()
    assert model.http_client is _sync_http_client()
    assert model.model_name == settings.llm_model
