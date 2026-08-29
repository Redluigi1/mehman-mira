"""Vertex AI LLM backend using Google's Gen AI SDK.

Supports either Vertex AI Express mode with an API key, or standard Vertex AI
authentication through Application Default Credentials. Like the CLI clients,
this class only handles Mira's two narrow completions. It never owns the agent
loop or calls application tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google import genai
from google.auth import load_credentials_from_file
from google.genai import types
from pydantic import ValidationError

from app.llm.base import LLMClient, LLMError, TModel

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class VertexAIClient(LLMClient):
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        *,
        project: str | None = None,
        location: str = "global",
        api_key: str | None = None,
        credentials_file: Path | str | None = None,
        timeout_s: float = 90.0,
        max_retries: int = 1,
        client: Any | None = None,
    ):
        if api_key and credentials_file:
            raise ValueError("VERTEX_API_KEY and GOOGLE_APPLICATION_CREDENTIALS are mutually exclusive")
        if timeout_s <= 0:
            raise ValueError("Vertex timeout must be greater than zero")
        if max_retries < 0:
            raise ValueError("Vertex max_retries cannot be negative")

        self.model = model
        self.project = project
        self.location = location
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client = client or self._build_client(
            project=project,
            location=location,
            api_key=api_key,
            credentials_file=credentials_file,
        )

    def _build_client(
        self,
        *,
        project: str | None,
        location: str,
        api_key: str | None,
        credentials_file: Path | str | None,
    ) -> Any:
        http_options = types.HttpOptions(
            api_version="v1",
            timeout=max(1, int(self.timeout_s * 1000)),
        )

        if api_key:
            # Express mode uses the API key alone. Passing project/location as
            # well changes the SDK's authentication mode, so leave them out.
            return genai.Client(vertexai=True, api_key=api_key, http_options=http_options)

        credentials = None
        if credentials_file:
            credentials, detected_project = load_credentials_from_file(
                str(credentials_file), scopes=[_CLOUD_PLATFORM_SCOPE]
            )
            project = project or detected_project

        # With no explicit credential file the SDK uses ADC. It can obtain the
        # project from ADC too, though setting VERTEX_PROJECT is clearer.
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
            http_options=http_options,
        )

    def _generate(self, *, system: str, user: str, response_schema: type[TModel] | None = None) -> Any:
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": 0,
        }
        if response_schema is not None:
            config_kwargs.update(
                response_mime_type="application/json",
                # StateDelta contains free-form maps such as set_fields and
                # confidence. Vertex's JSON Schema field supports these via
                # additionalProperties; the narrower OpenAPI-style field may
                # not preserve them correctly.
                response_json_schema=response_schema.model_json_schema(),
            )

        config = types.GenerateContentConfig(**config_kwargs)
        last_error: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=config,
                )
            except Exception as exc:  # SDK transport/auth/API errors share no single stable base class
                last_error = exc

        raise LLMError(
            f"Vertex AI failed after {self.max_retries + 1} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _response_text(response: Any) -> str:
        try:
            text = response.text
        except Exception as exc:
            raise LLMError(f"Vertex AI response did not contain readable text: {exc}") from exc
        if not text or not text.strip():
            raise LLMError("Vertex AI returned an empty response")
        return text.strip()

    def complete_json(self, *, system: str, user: str, schema: type[TModel]) -> TModel:
        response = self._generate(system=system, user=user, response_schema=schema)
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            text = self._response_text(response)
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMError(f"Vertex AI did not return valid JSON: {exc}\n---\n{text[:500]}") from exc

        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise LLMError(f"Vertex AI JSON did not match schema {schema.__name__}: {exc}") from exc

    def complete_text(self, *, system: str, user: str) -> str:
        response = self._generate(system=system, user=user)
        return self._response_text(response)
