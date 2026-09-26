"""Offline schema, request-serialization, and credential-presence checks."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import inspect
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
LABELS = ("standard-codex", "cheat-codex", "standard-deepseek", "cheat-deepseek")
PIN = "0.23.1.dev202609170426"
# Do not fetch a model-price map as a side effect of importing LiteLLM.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"


def no_network(*args, **kwargs):
    raise RuntimeError("Network is prohibited in this offline preflight")


socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network


async def check_deepseek_serialization(kwargs):
    """Intercept Harbor's actual LiteLLM call before any HTTP dispatch."""
    from harbor.llms.lite_llm import LiteLLM
    from litellm.llms.custom_httpx.llm_http_handler import BaseLLMHTTPHandler
    from litellm.llms.deepseek.chat.transformation import DeepSeekChatConfig
    from litellm.utils import get_optional_params

    # Harbor's call constructor supplies these values to LiteLLM; no completion runs.
    llm = LiteLLM("deepseek/deepseek-flash", api_base=kwargs["api_base"],
                  reasoning_effort=kwargs["reasoning_effort"])
    optional = get_optional_params(
        model="deepseek-flash", custom_llm_provider="deepseek", drop_params=True,
        reasoning_effort=llm._reasoning_effort, **kwargs["llm_call_kwargs"],
    )
    captured = {}

    async def intercept(**request):
        captured.update(request["data"])
        return None

    handler = BaseLLMHTTPHandler()
    handler.async_completion = intercept
    logger = SimpleNamespace(pre_call=lambda **unused: None, model_call_details={})
    prepared = handler.completion(
        model="deepseek-flash", messages=[{"role": "user", "content": "offline check"}],
        api_base="https://api.deepseek.com", custom_llm_provider="deepseek",
        model_response=None, encoding=None, logging_obj=logger, optional_params=optional,
        timeout=1.0, litellm_params={}, acompletion=True, stream=False,
        api_key="offline-placeholder-not-a-real-key", provider_config=DeepSeekChatConfig(),
    )
    if inspect.isawaitable(prepared):
        await prepared
    assert captured["model"] == "deepseek-flash"
    assert captured["reasoning_effort"] == "max"
    assert captured["thinking"] == {"type": "enabled"}
    assert "extra_body" not in captured
    return {"model": captured["model"], "reasoning_effort": captured["reasoning_effort"],
            "thinking": captured["thinking"], "network_requests": 0}


def validate_configs():
    from harbor.agents.installed.codex import CodexOptions
    from harbor.agents.terminus_2.terminus_2 import Terminus2Options
    from harbor.models.job.config import JobConfig

    assert version("harbor") == PIN, "Harbor version does not match upstream pin"
    prompt = (ROOT / "evaluation/hack-trial-prompt.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "evaluation/manifest.json").read_text())
    assert hashlib.sha256(prompt.encode()).hexdigest() == manifest["cheat_prompt_sha256"]
    configs = {}
    for label in LABELS:
        raw = json.loads((ROOT / "evaluation" / f"{label}.json").read_text())
        assert not set(raw).difference(JobConfig.model_fields), f"Unknown job field: {label}"
        config = JobConfig.model_validate(raw)
        assert config.n_attempts == (1 if label.startswith("cheat") else 3)
        assert config.n_concurrent_trials == 1 and config.retry.max_retries == 0
        assert config.environment.type.value == "docker"
        assert len(config.agents) == 1 and len(config.tasks) == 1
        assert (ROOT / config.tasks[0].path).is_dir()
        assert config.extra_instructions == ([prompt] if label.startswith("cheat") else [])
        agent = config.agents[0]
        assert not agent.env, "Credentials must be supplied by the local environment"
        if label.endswith("codex"):
            assert agent.name == "codex" and agent.model_name == "openai/gpt-6-astra"
            assert CodexOptions.model_validate(agent.kwargs).reasoning_effort == "xhigh"
            assert agent.override_setup_timeout_sec == 1800
            assert agent.override_timeout_sec is None and agent.max_timeout_sec is None
            assert config.agent_timeout_multiplier is None and config.timeout_multiplier == 1.0
        else:
            assert agent.name == "terminus-2" and agent.model_name == "deepseek/deepseek-flash"
            options = Terminus2Options.model_validate(agent.kwargs)
            assert options.reasoning_effort == "max" and options.interleaved_thinking
            assert options.api_base == "https://api.deepseek.com"
        configs[label] = agent.kwargs
    wire = asyncio.run(check_deepseek_serialization(configs["standard-deepseek"]))
    return {"templates_valid": list(LABELS), "harbor_version": PIN,
            "litellm_version": version("litellm"), "deepseek_serialized_request": wire}


def codex_credential():
    from harbor.utils.env import parse_bool_env_value

    explicit = os.getenv("CODEX_AUTH_JSON_PATH")
    force = False if explicit else parse_bool_env_value(
        os.getenv("CODEX_FORCE_AUTH_JSON"), name="CODEX_FORCE_AUTH_JSON", default=False)
    selected = Path(explicit) if explicit else Path.home() / ".codex/auth.json" if force else None
    if selected is not None:
        if not selected.is_file() or not os.access(selected, os.R_OK):
            return {"present": False, "status": "selected_auth_file_missing_or_unreadable"}
        # Inspect only the nonsecret authentication-mode label. Never output file contents.
        try:
            mode = json.loads(selected.read_text(encoding="utf-8")).get("auth_mode")
        except (OSError, UnicodeError, ValueError, AttributeError):
            return {"present": False, "status": "selected_auth_file_invalid_json"}
        mode = mode if mode in ("chatgpt", "apikey", "api_key", "api") else "unknown"
        return {"present": True, "status": "auth_file_present_unvalidated", "auth_mode": mode}
    if os.getenv("OPENAI_API_KEY"):
        return {"present": True, "status": "api_key_present_unvalidated"}
    candidate = Path("/mnt/c/Users/MSN/.codex/auth.json").is_file()
    return {"present": False, "status": "no_selected_credential",
            "windows_auth_cache_exists": candidate,
            "action": "Set CODEX_AUTH_JSON_PATH to a readable auth.json, or set OPENAI_API_KEY."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("all", "codex", "deepseek"), default="all")
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "offline_only; no authentication, entitlement, balance, or model call",
              "provider": args.provider}
    try:
        report.update(validate_configs())
    except Exception as error:
        report["validation_error"] = f"{type(error).__name__}: {error}"
        print(json.dumps(report, indent=2))
        return 1
    if not args.config_only:
        credentials = {}
        if args.provider in ("all", "codex"):
            credentials["codex"] = codex_credential()
            if os.getenv("OPENAI_BASE_URL"):
                credentials["codex"] = {"present": False, "status": "OPENAI_BASE_URL_override_requires_review",
                                        "action": "Unset OPENAI_BASE_URL for the standard OpenAI configuration."}
        if args.provider in ("all", "deepseek"):
            present = bool(os.getenv("DEEPSEEK_API_KEY"))
            credentials["deepseek"] = {"present": present, "status": "api_key_present_unvalidated" if present else "DEEPSEEK_API_KEY_missing"}
        report["credentials"] = credentials
        report["local_prerequisites_present"] = all(item["present"] for item in credentials.values())
    output = ROOT / "artifacts/environment/model-preflight.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    label = "config-only" if args.config_only else args.provider
    output.with_name(f"model-preflight-{label}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if args.config_only or report["local_prerequisites_present"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
