"""Modelo de razonamiento intercambiable (mismo contrato que bi-selfservice-agents).

AGENT_MODEL_PROVIDER: gemini | claude | claude_native | anthropic
Se puede sobreescribir por agente con <AGENT>_MODEL_PROVIDER.
"""

import os


def get_model(agent_name: str = ""):
    provider = os.environ.get(
        f"{agent_name.upper()}_MODEL_PROVIDER",
        os.environ.get("AGENT_MODEL_PROVIDER", "gemini"),
    )

    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    if provider == "claude":
        from google.adk.models.lite_llm import LiteLlm

        return LiteLlm(
            model=f"vertex_ai/{os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')}",
            vertex_location=os.environ.get("CLAUDE_LOCATION", "us-east5"),
        )

    if provider == "claude_native":
        from google.adk.models.anthropic_llm import Claude

        return Claude(model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"))

    if provider == "anthropic":
        from google.adk.models.lite_llm import LiteLlm

        return LiteLlm(
            model=f"anthropic/{os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')}"
        )

    raise ValueError(f"AGENT_MODEL_PROVIDER desconocido: {provider}")
