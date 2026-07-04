from google import genai
from google.genai import types


class GeminiProvider:
    # Effective default for this project. The spec names `gemini-2.0-flash`, but that
    # model 404s on the live API in this environment; `gemini-2.5-flash` is the current
    # cheap/low-latency flash model and is used as the working default. Overridable via
    # AGENT_LLM_MODEL.
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    @property
    def model(self) -> str:
        return self._model

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        text, _, _ = self.call_with_usage(prompt, system=system)
        return text

    def call_with_usage(
        self, prompt: str, *, system: str | None = None
    ) -> tuple[str, int, int]:
        config = (
            types.GenerateContentConfig(system_instruction=system) if system else None
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return (response.text or ""), int(input_tokens), int(output_tokens)
