from app.core.translation_router import TranslationConfig, TranslationRouter


def test_translation_router_none_provider_returns_input() -> None:
    router = TranslationRouter()
    cfg = TranslationConfig(provider="none", base_url=None, api_key=None, model_name="x")
    text = "hello"
    out = router.translate(text, "zh", cfg)
    assert out == text

