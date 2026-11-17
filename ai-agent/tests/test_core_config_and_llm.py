"""Black-box tests cho cấu hình tập trung (core/config.py) & 1 Cloud Model duy nhất (core/llm.py)."""

from __future__ import annotations

from core import config as cfg
from core.llm import build_model, get_llm, reset_llm_cache
from domain.schemas import UserPreferenceState
from intelligence.nlu import TurnAnalysis, analyze_turn


def test_centralized_config_defaults_and_env_override(monkeypatch):
    assert cfg.DEFAULT_SEARCH_LIMIT == 5
    assert cfg.MAX_SEARCH_LIMIT == 50
    assert cfg.LLM_NLU_TEMPERATURE == 0.0
    assert cfg.LLM_NLU_RETRY_TEMPERATURE == 0.3
    assert cfg.LLM_GENERATION_TEMPERATURE == 0.3
    assert cfg.RESOLVE_LOCATION_MAX_RETRIES == 2

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://homigo.vn, https://app.homigo.vn")
    monkeypatch.setenv("SEARCH_ROOM_API_BASE", "https://api.homigo.vn/api/v1/")
    s = cfg.get_runtime_settings()
    assert s.cors_allowed_origins == ("https://homigo.vn", "https://app.homigo.vn")
    assert s.search_room_api_base == "https://api.homigo.vn/api/v1"
    assert not hasattr(s, "enable_main_thinking")


def test_single_cloud_model_temperatures_and_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("MODEL_NAME", "gemini-2.5-flash")
    reset_llm_cache()

    s, missing = cfg.load_settings()
    assert missing == [] and s is not None
    m_gen = build_model(s)
    m_nlu = build_model(s, temperature=cfg.LLM_NLU_TEMPERATURE)
    assert m_gen.temperature == cfg.LLM_GENERATION_TEMPERATURE == 0.3
    assert m_nlu.temperature == cfg.LLM_NLU_TEMPERATURE == 0.0

    # get_llm cache tách theo temperature nhưng dùng chung 1 model Cloud
    assert get_llm() is get_llm(temperature=0.3)
    assert get_llm(temperature=0.0) is not get_llm(temperature=0.3)
    reset_llm_cache()


def test_nlu_uses_default_temp_first_and_switches_to_retry_model_on_retry():
    calls: list[str] = []

    class _Bound:
        def __init__(self, tag: str, result):
            self.tag = tag
            self.result = result

        def invoke(self, _msgs):
            calls.append(self.tag)
            if callable(self.result):
                return self.result()
            return self.result

    class _FakeLLM:
        def __init__(self, tag: str, result):
            self.tag = tag
            self.result = result

        def with_structured_output(self, _schema, **_kw):
            return _Bound(self.tag, self.result)

    primary = _FakeLLM("temp_0.0", None)
    retry = _FakeLLM("temp_0.3", TurnAnalysis(intent="smalltalk"))

    out = analyze_turn(primary, "xin chào", UserPreferenceState(), retry_model=retry, skills={})
    assert out is not None and out.intent == "smalltalk"
    assert calls == ["temp_0.0", "temp_0.3"]


def test_invoke_with_retry_handles_503_high_demand(monkeypatch):
    import core.llm as llm_mod

    slept: list[float] = []
    monkeypatch.setattr(llm_mod.time, "sleep", lambda sec: slept.append(sec))

    attempts = 0

    def _flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("Error code: 503 - This model is currently experiencing high demand. UNAVAILABLE")
        return "ok"

    assert llm_mod.invoke_with_retry(_flaky, max_attempts=3, context="test") == "ok"
    assert attempts == 3
    assert slept == [2.0, 4.0]


def test_invoke_with_retry_skips_daily_quota_and_non_transient(monkeypatch):
    import pytest
    import core.llm as llm_mod

    slept: list[float] = []
    monkeypatch.setattr(llm_mod.time, "sleep", lambda sec: slept.append(sec))

    quota_calls = 0

    def _quota():
        nonlocal quota_calls
        quota_calls += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel")

    with pytest.raises(RuntimeError):
        llm_mod.invoke_with_retry(_quota, max_attempts=3, context="test")
    assert quota_calls == 1
    assert slept == []

    bad_calls = 0

    def _bad():
        nonlocal bad_calls
        bad_calls += 1
        raise ValueError("invalid argument")

    with pytest.raises(ValueError):
        llm_mod.invoke_with_retry(_bad, max_attempts=3, context="test")
    assert bad_calls == 1
    assert slept == []


def test_analyze_turn_retries_on_503(monkeypatch):
    import intelligence.nlu as nlu_mod
    from domain.schemas import UserPreferenceState
    from intelligence.nlu import TurnAnalysis, analyze_turn

    slept: list[float] = []
    monkeypatch.setattr(nlu_mod._time, "sleep", lambda sec: slept.append(sec))

    attempts = 0

    class _Bound:
        def invoke(self, _messages):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("Error code: 503 - UNAVAILABLE high demand")
            return TurnAnalysis(intent="smalltalk")

    class _FakeLLM:
        def with_structured_output(self, _schema, **_kw):
            return _Bound()

    out = analyze_turn(_FakeLLM(), "xin chào", UserPreferenceState(), skills={})
    assert out is not None and out.intent == "smalltalk"
    assert attempts == 2
    assert slept == [2.0]
