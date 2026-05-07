"""LLM Provider: 다양한 LLM 백엔드 통합

지원 백엔드:
- OpenAI (GPT-4, GPT-4o, GPT-3.5-turbo)
- Anthropic (Claude 3.5, Claude 3)
- vLLM (로컬 서버)
- Mock (테스트용)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# JSON Repair Utilities for LLM Output Stability
# ============================================================


def _strip_think_blocks(text: str) -> str:
    """Strip <think>...</think> blocks from reasoning model output.

    DeepSeek-R1 and similar reasoning models wrap their chain-of-thought
    in <think>...</think> tags before the actual JSON response.
    Stripping these first prevents brace-matching confusion from
    { and } characters inside the reasoning text.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_last_json_block(text: str) -> str:
    """Extract the last complete JSON object from text with thinking/reasoning prefix.

    Qwen3 models prepend 'Thinking Process:...' before the actual JSON.
    This function finds the last valid top-level JSON object in the text.
    """
    # Strip <think> blocks before brace matching
    text = _strip_think_blocks(text)

    # Find all top-level { ... } blocks by walking from the end
    last_brace = text.rfind("}")
    if last_brace < 0:
        return text

    depth = 0
    for i in range(last_brace, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
        if depth == 0:
            candidate = text[i : last_brace + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                break
    return text


def repair_json(text: str) -> str:
    """Repair common JSON formatting issues from LLM outputs.

    Handles:
    - Trailing commas before } or ]
    - Missing quotes around keys
    - Single quotes instead of double quotes
    - Unescaped newlines in strings
    - Extra text before/after JSON
    - Markdown code blocks
    """
    # Strip <think>...</think> blocks (DeepSeek-R1 reasoning models)
    if "<think>" in text:
        text = _strip_think_blocks(text)

    # Handle thinking/reasoning prefix (Qwen3 models)
    if text.startswith("Thinking") or "Thinking Process" in text[:50]:
        extracted = _extract_last_json_block(text)
        if extracted != text:
            try:
                json.loads(extracted)
                return extracted
            except json.JSONDecodeError:
                pass  # Fall through to normal repair

    # Remove markdown code blocks
    if "```" in text:
        # Extract content between ```json and ``` or ``` and ```
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1)

    # Try to extract JSON object/array from surrounding text
    text = text.strip()

    # Find the start of JSON object or array
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        return text  # No JSON found

    if obj_start == -1:
        start = arr_start
        end_char = "]"
    elif arr_start == -1:
        start = obj_start
        end_char = "}"
    else:
        start = min(obj_start, arr_start)
        end_char = "}" if obj_start < arr_start else "]"

    # Find matching end bracket
    depth = 0
    end = start
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    text = text[start:end]

    # Fix trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix single quotes to double quotes (careful with apostrophes)
    # Only replace single quotes that appear to be JSON string delimiters
    result = []
    in_double_string = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            result.append(char)
            result.append(text[i + 1])
            i += 2
            continue
        if char == '"':
            in_double_string = not in_double_string
        if char == "'" and not in_double_string:
            # Check if this looks like a JSON string delimiter
            prev_char = text[i - 1] if i > 0 else ""
            next_char = text[i + 1] if i + 1 < len(text) else ""
            if prev_char in ":{[," or next_char in ":}],":
                char = '"'
        result.append(char)
        i += 1
    text = "".join(result)

    # Fix unquoted keys (simple cases)
    text = re.sub(r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', text)

    return text


def safe_json_parse(text: str, max_retries: int = 3) -> dict[str, Any]:
    """Safely parse JSON with repair attempts.

    Args:
        text: Raw text that should contain JSON
        max_retries: Number of repair attempts

    Returns:
        Parsed JSON dict

    Raises:
        json.JSONDecodeError: If parsing fails after all attempts
    """
    original_text = text
    last_error: json.JSONDecodeError | None = None

    for attempt in range(max_retries):
        try:
            # Try direct parse first
            if attempt == 0:
                return json.loads(text)

            # Apply repairs
            text = repair_json(original_text)
            return json.loads(text)

        except json.JSONDecodeError as e:
            last_error = e
            logger.debug(f"JSON parse attempt {attempt + 1} failed: {e}")

            # For subsequent attempts, try more aggressive repairs
            if attempt == 1:
                # Try to find and extract just the JSON portion
                text = original_text
                # Remove any thinking/reasoning text
                for marker in ["```", "Here is", "The recommended", "Based on"]:
                    if marker in text:
                        parts = text.split(marker)
                        for part in parts:
                            if "{" in part and "}" in part:
                                text = part
                                break

    # Final attempt: try to build a minimal valid response
    logger.warning(f"JSON repair failed after {max_retries} attempts. Error: {last_error}")
    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("JSON parsing failed", text, 0)


class LLMBackend(str, Enum):
    """지원 LLM 백엔드"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    VLLM = "vllm"
    MOCK = "mock"


@dataclass
class LLMMessage:
    """LLM 메시지"""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """LLM 응답"""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any | None = None


@dataclass
class LLMConfig:
    """LLM 설정"""

    backend: LLMBackend = LLMBackend.OPENAI
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 4096
    api_key: str | None = None
    base_url: str | None = None  # vLLM 또는 커스텀 엔드포인트용
    timeout: float = 300.0
    seed: int | None = None  # Reproducibility: seed for LLM sampling

    def __post_init__(self):
        # API 키 환경변수에서 로드
        if self.api_key is None:
            if self.backend in (LLMBackend.OPENAI, LLMBackend.VLLM):
                self.api_key = os.environ.get("OPENAI_API_KEY")
            elif self.backend == LLMBackend.ANTHROPIC:
                self.api_key = os.environ.get("ANTHROPIC_API_KEY")
            elif self.backend == LLMBackend.GEMINI:
                self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        # Anthropic does not support seed parameter
        if self.seed is not None and self.backend == LLMBackend.ANTHROPIC:
            logger.warning("Anthropic API does not support seed parameter. Seed will be ignored.")


class BaseLLMProvider(ABC):
    """LLM Provider 기본 클래스"""

    def __init__(self, config: LLMConfig):
        self.config = config
        # 마지막 호출의 토큰 사용량 추적 (Budget-matched 평가용)
        self._last_usage: dict[str, int] = {}

    @property
    def last_usage(self) -> dict[str, int]:
        """마지막 LLM 호출의 토큰 사용량 반환"""
        return self._last_usage

    def get_total_tokens_from_last_call(self) -> int:
        """마지막 호출에서 사용된 총 토큰 수 반환"""
        return self._last_usage.get("total_tokens", 0)

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """메시지 완성"""
        pass

    @abstractmethod
    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """JSON 형식 응답 생성"""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None

    def _get_client(self):
        """OpenAI 클라이언트 lazy 초기화"""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.config.api_key, base_url=self.config.base_url, timeout=self.config.timeout
                )
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """OpenAI API 호출"""
        client = self._get_client()

        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # GPT-5+ models require max_completion_tokens instead of max_tokens
        tok_key = "max_completion_tokens" if self.config.model.startswith(("gpt-5", "o1", "o3", "o4")) else "max_tokens"
        create_kwargs: dict[str, Any] = dict(
            model=self.config.model,
            messages=api_messages,
            temperature=self.config.temperature,
        )
        create_kwargs[tok_key] = self.config.max_tokens
        if self.config.seed is not None:
            create_kwargs["seed"] = self.config.seed

        response = client.chat.completions.create(**create_kwargs)

        # 토큰 사용량 추적
        self._last_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        # Reasoning model compatibility: content may be null, use reasoning field
        msg = response.choices[0].message
        content = msg.content
        if content is None:
            content = getattr(msg, "reasoning", None) or ""

        # CGA_DEBUG_RAW_RESPONSE hook — keep most-recent raw LLM text so the
        # agent's empty-detection path can snapshot it into the episode JSON.
        self._last_raw_content = content

        return LLMResponse(content=content, model=response.model, usage=self._last_usage.copy(), raw_response=response)

    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """JSON 형식 응답 생성 (OpenAI JSON mode)"""
        client = self._get_client()

        # JSON 스키마 프롬프트 추가
        json_instruction = LLMMessage(
            role="system", content=f"Respond ONLY with valid JSON matching this schema: {json.dumps(schema)}"
        )
        all_messages = [json_instruction] + messages

        api_messages = [{"role": msg.role, "content": msg.content} for msg in all_messages]

        # GPT-5+ models require max_completion_tokens instead of max_tokens
        tok_key = "max_completion_tokens" if self.config.model.startswith(("gpt-5", "o1", "o3", "o4")) else "max_tokens"
        create_kwargs: dict[str, Any] = dict(
            model=self.config.model,
            messages=api_messages,
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )
        create_kwargs[tok_key] = self.config.max_tokens
        if self.config.seed is not None:
            create_kwargs["seed"] = self.config.seed

        response = client.chat.completions.create(**create_kwargs)

        # 토큰 사용량 추적 (Budget-matched 평가용)
        self._last_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        # Reasoning model compatibility: content may be null
        msg = response.choices[0].message
        content = msg.content
        if content is None:
            reasoning = getattr(msg, "reasoning", None) or ""
            # Extract JSON object from reasoning text
            content = self._extract_json_from_reasoning(reasoning)
        return json.loads(content)

    @staticmethod
    def _extract_json_from_reasoning(text: str) -> str:
        """Extract JSON object from reasoning model output.

        Reasoning models (e.g., DeepSeek-R1) put their thinking inline
        in content, followed by a JSON block. This method finds the last
        complete JSON object using brace matching (not regex), which
        handles arbitrary nesting depth.
        """
        if not text:
            return "{}"
        # Strip <think>...</think> blocks first to avoid brace confusion
        text = _strip_think_blocks(text)
        if not text:
            return "{}"
        text = text.strip()
        if text.startswith("{"):
            return text

        # Find the last complete JSON object via reverse brace matching
        best_json = "{}"
        i = len(text) - 1
        while i >= 0:
            if text[i] == "}":
                # Found potential JSON end — scan backward for matching '{'
                depth = 0
                j = i
                while j >= 0:
                    if text[j] == "}":
                        depth += 1
                    elif text[j] == "{":
                        depth -= 1
                        if depth == 0:
                            candidate = text[j : i + 1]
                            # Validate it's actually JSON-like (has quotes)
                            if '"' in candidate and len(candidate) > len(best_json):
                                best_json = candidate
                            break
                    j -= 1
                i = j - 1  # Skip past this block
            else:
                i -= 1

        return best_json


class AnthropicProvider(BaseLLMProvider):
    """Anthropic API Provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None

    def _get_client(self):
        """Anthropic 클라이언트 lazy 초기화"""
        if self._client is None:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=self.config.api_key, timeout=self.config.timeout)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """Anthropic API 호출"""
        client = self._get_client()

        # System 메시지 분리
        system_content = ""
        api_messages = []
        for msg in messages:
            if msg.role == "system":
                system_content += msg.content + "\n"
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        # Anthropic SDK >= 0.80 requires system as array of content blocks
        system_param = [{"type": "text", "text": system_content.strip()}] if system_content else []

        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system_param,
            messages=api_messages,
        )

        # 토큰 사용량 추적 (Budget-matched 평가용)
        self._last_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=response.content[0].text, model=response.model, usage=self._last_usage.copy(), raw_response=response
        )

    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """JSON 형식 응답 생성 with robust parsing"""
        # Enhanced JSON instruction
        json_instruction = LLMMessage(
            role="system",
            content=f"""Respond ONLY with valid JSON matching this schema. No markdown, no explanation, no thinking.

SCHEMA:
{json.dumps(schema, indent=2)}

Output ONLY the JSON object.""",
        )
        all_messages = [json_instruction] + messages

        response = self.complete(all_messages)
        content = response.content.strip()

        # Use safe_json_parse with repair logic
        return safe_json_parse(content)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider (google-genai SDK)"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None

    def _get_client(self):
        """Gemini 클라이언트 lazy 초기화"""
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.config.api_key)
            except ImportError:
                raise ImportError("google-genai package not installed. Run: pip install google-genai")
        return self._client

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int]:
        """Extract token usage from Gemini response, excluding thinking tokens.

        Gemini thinking models include thoughts_token_count in total_token_count,
        which inflates budget tracking. We compute total as prompt + candidates only
        to maintain budget fairness with non-thinking providers (Anthropic, OpenAI).
        """
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return {}
        prompt = getattr(usage, "prompt_token_count", 0) or 0
        # candidates_token_count is the official field; response_token_count is legacy
        completion = getattr(usage, "candidates_token_count", 0) or getattr(usage, "response_token_count", 0) or 0
        thoughts = getattr(usage, "thoughts_token_count", 0) or 0
        result: dict[str, int] = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
        if thoughts > 0:
            result["thoughts_tokens"] = thoughts
            logger.warning(
                "Gemini thinking tokens detected (%d) despite thinking_budget=0. "
                "Excluded from budget total (%d) for fairness.",
                thoughts,
                result["total_tokens"],
            )
        return result

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """Gemini API 호출"""
        client = self._get_client()
        from google.genai import types

        # System 메시지 분리 (Gemini는 system_instruction으로 전달)
        system_content = ""
        api_contents: list[types.Content] = []
        for msg in messages:
            if msg.role == "system":
                system_content += msg.content + "\n"
            else:
                role = "model" if msg.role == "assistant" else "user"
                api_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))

        # gemini-2.5-pro requires thinking mode (thinking_budget=0 raises 400).
        # With explicit thinking_budget, thinking tokens are separate from
        # max_output_tokens. _extract_usage() excludes thinking from budget.
        _THINKING_REQUIRED = ("2.5-pro", "2.0-pro", "3-pro", "3-flash", "3.1-pro", "3.1-flash")
        if any(m in self.config.model for m in _THINKING_REQUIRED):
            thinking_cfg = types.ThinkingConfig(thinking_budget=2048)
        else:
            thinking_cfg = types.ThinkingConfig(thinking_budget=0)

        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            system_instruction=system_content.strip() if system_content else None,
            thinking_config=thinking_cfg,
        )
        if self.config.seed is not None:
            config.seed = self.config.seed

        response = client.models.generate_content(
            model=self.config.model,
            contents=api_contents,
            config=config,
        )

        # 토큰 사용량 추적 (Budget-matched 평가용)
        # thinking tokens은 budget 공정성을 위해 total에서 제외
        self._last_usage = self._extract_usage(response)

        return LLMResponse(
            content=response.text or "",
            model=self.config.model,
            usage=self._last_usage.copy(),
            raw_response=response,
        )

    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """JSON 형식 응답 생성 (Gemini responseMimeType 활용)"""
        client = self._get_client()
        from google.genai import types

        # System 메시지 분리 + JSON 스키마 instruction 추가
        system_content = f"Respond ONLY with valid JSON matching this schema. No markdown, no explanation.\n\nSCHEMA:\n{json.dumps(schema, indent=2)}\n"
        api_contents: list[types.Content] = []
        for msg in messages:
            if msg.role == "system":
                system_content += "\n" + msg.content
            else:
                role = "model" if msg.role == "assistant" else "user"
                api_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))

        _THINKING_REQUIRED = ("2.5-pro", "2.0-pro", "3-pro", "3-flash", "3.1-pro", "3.1-flash")
        if any(m in self.config.model for m in _THINKING_REQUIRED):
            thinking_cfg = types.ThinkingConfig(thinking_budget=2048)
        else:
            thinking_cfg = types.ThinkingConfig(thinking_budget=0)

        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            system_instruction=system_content.strip(),
            response_mime_type="application/json",
            thinking_config=thinking_cfg,
        )
        if self.config.seed is not None:
            config.seed = self.config.seed

        response = client.models.generate_content(
            model=self.config.model,
            contents=api_contents,
            config=config,
        )

        # 토큰 사용량 추적 (thinking tokens 제외)
        self._last_usage = self._extract_usage(response)

        content = (response.text or "").strip()
        return safe_json_parse(content)


class VLLMProvider(BaseLLMProvider):
    """vLLM 로컬 서버 Provider (OpenAI 호환 API)"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = "http://localhost:8000/v1"
        self._client: Any = None

    def _get_client(self):
        """OpenAI 호환 클라이언트 lazy 초기화"""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.config.api_key or "dummy", base_url=self.config.base_url, timeout=self.config.timeout
                )
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """VLLM API 호출 (OpenAI 호환)"""
        client = self._get_client()

        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        create_kwargs: dict[str, Any] = dict(
            model=self.config.model,
            messages=api_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        if self.config.seed is not None:
            create_kwargs["seed"] = self.config.seed

        response = client.chat.completions.create(**create_kwargs)

        # 토큰 사용량 추적 (Budget-matched 평가용)
        if response.usage:
            self._last_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        else:
            self._last_usage = {}

        # Reasoning model compatibility: content may be null, use reasoning field
        msg = response.choices[0].message
        content = msg.content
        if content is None:
            content = getattr(msg, "reasoning", None) or ""

        # CGA_DEBUG_RAW_RESPONSE hook — keep most-recent raw LLM text so the
        # agent's empty-detection path can snapshot it into the episode JSON.
        self._last_raw_content = content

        return LLMResponse(content=content, model=response.model, usage=self._last_usage.copy(), raw_response=response)

    def complete_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        max_retries: int = 2,
    ) -> list[dict[str, Any]]:
        """Call LLM with OpenAI-compatible tools/function-calling API.

        Args:
            messages: Chat messages.
            tools: OpenAI-format tool definitions.
            max_retries: Retry attempts on failure.

        Returns:
            List of parsed tool calls, each dict with keys:
            ``name`` (str), ``arguments`` (dict), ``id`` (str | None).
        """
        client = self._get_client()
        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        create_kwargs: dict[str, Any] = dict(
            model=self.config.model,
            messages=api_messages,
            tools=tools,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        if self.config.seed is not None:
            create_kwargs["seed"] = self.config.seed

        # P2 Fix: Accumulate tokens across retries
        accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        last_error: Exception | None = None
        use_json_fallback = False

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**create_kwargs)

                # Track token usage
                if response.usage:
                    accumulated_usage["prompt_tokens"] += response.usage.prompt_tokens
                    accumulated_usage["completion_tokens"] += response.usage.completion_tokens
                    accumulated_usage["total_tokens"] += response.usage.total_tokens
                self._last_usage = accumulated_usage.copy()

                msg = response.choices[0].message
                tool_calls_raw = getattr(msg, "tool_calls", None) or []

                # CGA_DEBUG_RAW_RESPONSE hook — capture both the tool_call
                # names (may be empty) and the raw content fallback so the
                # empty-detection path can record exactly what the model said.
                self._last_raw_content = (
                    msg.content
                    if msg.content
                    else "<tool_calls>"
                    + ",".join(f"{tc.function.name}({tc.function.arguments or ''})" for tc in tool_calls_raw)
                    + "</tool_calls>"
                )

                parsed: list[dict[str, Any]] = []
                for tc in tool_calls_raw:
                    fn = tc.function
                    try:
                        args = json.loads(fn.arguments) if fn.arguments else {}
                    except json.JSONDecodeError:
                        args = {"justification": fn.arguments or ""}
                    parsed.append(
                        {
                            "name": fn.name,
                            "arguments": args,
                            "id": getattr(tc, "id", None),
                        }
                    )

                # If model returned content instead of tool_calls, try JSON fallback
                if not parsed and msg.content:
                    content = msg.content.strip()
                    if "<think>" in content:
                        content = _strip_think_blocks(content)
                    try:
                        data = safe_json_parse(content)
                        actions_data = data.get("actions", []) if isinstance(data, dict) else data
                        items = actions_data if isinstance(actions_data, list) else []
                        for ad in items:
                            parsed.append(
                                {
                                    "name": str(ad.get("action_id", "")),
                                    "arguments": {"justification": ad.get("justification", "")},
                                    "id": None,
                                }
                            )
                    except (json.JSONDecodeError, AttributeError):
                        logger.warning(f"Tool-use fallback JSON parse failed (attempt {attempt + 1})")

                if parsed:
                    return parsed

                logger.warning(f"Tool-use returned no calls (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                last_error = e
                err_msg = str(e)
                # Detect vLLM servers without --enable-auto-tool-choice
                if "tool choice requires" in err_msg or "tool_call_parser" in err_msg:
                    logger.info("Server lacks native tool-calling, switching to JSON-mode fallback")
                    use_json_fallback = True
                    break
                logger.warning(f"Tool-use call failed (attempt {attempt + 1}/{max_retries}): {e}")

        # ── JSON-mode fallback: embed tool defs in prompt ──
        if use_json_fallback:
            return self._complete_with_tools_json_fallback(
                messages,
                tools,
                max_retries,
                accumulated_usage,
            )

        self._last_usage = accumulated_usage.copy()
        if last_error:
            logger.error(f"All tool-use attempts failed: {last_error}")
        return []

    def _complete_with_tools_json_fallback(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        max_retries: int,
        accumulated_usage: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Fallback: embed tool definitions in prompt, ask for JSON function calls."""
        # Build tool description block
        tool_lines = []
        for t in tools:
            fn = t["function"]
            tool_lines.append(f"- {fn['name']}: {fn['description']}")
        tools_block = "\n".join(tool_lines)

        # Rewrite messages: append tool info to system prompt
        tool_suffix = f"""

You have access to the following clinical action functions:
{tools_block}

To call functions, respond with ONLY a JSON object:
{{"tool_calls": [{{"name": "function_name", "justification": "clinical reason"}}]}}

Call 1-5 functions. Use EXACT function names from the list above.
IMPORTANT: Do NOT return an empty tool_calls list. Always call at least one function."""

        rewritten: list[LLMMessage] = []
        merged = False
        for msg in messages:
            if msg.role == "system" and not merged:
                rewritten.append(LLMMessage(role="system", content=msg.content + tool_suffix))
                merged = True
            else:
                rewritten.append(msg)
        if not merged:
            rewritten.insert(0, LLMMessage(role="system", content=tool_suffix.strip()))

        # Use complete_json-style call via complete()
        for attempt in range(max_retries):
            try:
                response = self.complete(rewritten)
                accumulated_usage["prompt_tokens"] += self._last_usage.get("prompt_tokens", 0)
                accumulated_usage["completion_tokens"] += self._last_usage.get("completion_tokens", 0)
                accumulated_usage["total_tokens"] += self._last_usage.get("total_tokens", 0)
                self._last_usage = accumulated_usage.copy()

                content = response.content.strip() if response.content else ""
                if "<think>" in content:
                    content = _strip_think_blocks(content)
                if content and not content.startswith("{"):
                    extracted = OpenAIProvider._extract_json_from_reasoning(content)
                    if extracted != "{}":
                        content = extracted

                data = safe_json_parse(content)
                calls = data.get("tool_calls", data.get("actions", []))
                items = calls if isinstance(calls, list) else []

                parsed: list[dict[str, Any]] = []
                for item in items:
                    name = str(item.get("name", item.get("action_id", "")))
                    justification = item.get("justification", item.get("arguments", {}).get("justification", ""))
                    if name:
                        parsed.append(
                            {
                                "name": name,
                                "arguments": {"justification": justification},
                                "id": None,
                            }
                        )

                if parsed:
                    return parsed
                logger.warning(f"Tool-use JSON fallback empty (attempt {attempt + 1}/{max_retries})")

            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Tool-use JSON fallback failed (attempt {attempt + 1}/{max_retries}): {e}")

        self._last_usage = accumulated_usage.copy()
        return []

    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """JSON 형식 응답 생성 with robust parsing and retry logic"""
        # Enhanced JSON instruction with clear examples
        json_suffix = f"""

You MUST respond with ONLY valid JSON. No explanations, no markdown, no thinking.

REQUIRED JSON SCHEMA:
{json.dumps(schema, indent=2)}

CRITICAL RULES:
1. Start your response with {{ and end with }}
2. Use double quotes for all strings and keys
3. No trailing commas after the last item
4. No comments in JSON
5. Escape special characters in strings

EXAMPLE FORMAT:
{{"actions": [{{"action_id": "example", "action_type": "order_lab", "args": {{}}, "justification": "reason"}}], "reasoning": "clinical rationale"}}

Output ONLY the JSON object, nothing else."""

        # Merge JSON instruction into existing system message to avoid
        # multiple system messages (Qwen3.5+ rejects non-leading system msgs)
        all_messages = []
        system_merged = False
        for msg in messages:
            if msg.role == "system" and not system_merged:
                all_messages.append(LLMMessage(role="system", content=msg.content + json_suffix))
                system_merged = True
            else:
                all_messages.append(msg)

        # If no system message existed, prepend one
        if not system_merged:
            all_messages.insert(0, LLMMessage(role="system", content=json_suffix.strip()))

        max_attempts = 3
        last_error: json.JSONDecodeError | None = None

        # P2 Fix: Accumulate tokens across all retry attempts
        accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for attempt in range(max_attempts):
            try:
                response = self.complete(all_messages)
                content = response.content.strip() if response.content else ""

                # P2 Fix: Accumulate tokens from this attempt
                accumulated_usage["prompt_tokens"] += self._last_usage.get("prompt_tokens", 0)
                accumulated_usage["completion_tokens"] += self._last_usage.get("completion_tokens", 0)
                accumulated_usage["total_tokens"] += self._last_usage.get("total_tokens", 0)
                self._last_usage = accumulated_usage.copy()

                # Strip <think>...</think> blocks before JSON extraction
                if content and "<think>" in content:
                    content = _strip_think_blocks(content)

                # Reasoning model: content may be thinking text with embedded JSON
                if content and not content.startswith("{"):
                    extracted = OpenAIProvider._extract_json_from_reasoning(content)
                    if extracted != "{}":
                        content = extracted

                # Use safe_json_parse with repair logic
                return safe_json_parse(content)

            except json.JSONDecodeError as e:
                # P2 Fix: Still accumulate tokens even on failed parse
                accumulated_usage["prompt_tokens"] += self._last_usage.get("prompt_tokens", 0)
                accumulated_usage["completion_tokens"] += self._last_usage.get("completion_tokens", 0)
                accumulated_usage["total_tokens"] += self._last_usage.get("total_tokens", 0)

                last_error = e
                logger.warning(f"JSON parse attempt {attempt + 1}/{max_attempts} failed: {e}")

                if attempt < max_attempts - 1:
                    # Add a clarification message for retry
                    retry_message = LLMMessage(
                        role="user",
                        content="Your response was not valid JSON. Please respond with ONLY a valid JSON object starting with { and ending with }. No other text.",
                    )
                    all_messages = all_messages + [retry_message]

        # P2 Fix: Ensure accumulated tokens are stored even on failure
        self._last_usage = accumulated_usage.copy()

        # If all attempts failed, raise the last error
        logger.error(f"All JSON parse attempts failed. Last error: {last_error}")
        if last_error is not None:
            raise last_error
        raise json.JSONDecodeError("JSON parsing failed", "", 0)


class MockLLMProvider(BaseLLMProvider):
    """테스트용 Mock Provider"""

    def __init__(self, config: LLMConfig, responses: list[str] | None = None):
        super().__init__(config)
        self.responses = responses or []
        self.call_count = 0
        self.call_history: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """Mock 응답 반환"""
        self.call_history.append(messages)

        if self.responses and self.call_count < len(self.responses):
            content = self.responses[self.call_count]
        else:
            # 기본 Mock 응답: 마지막 메시지에서 행동 추론
            content = self._generate_mock_response(messages)

        self.call_count += 1

        # 토큰 사용량 추적 (Budget-matched 평가용)
        self._last_usage = {
            "prompt_tokens": sum(len(m.content) // 4 for m in messages),
            "completion_tokens": len(content) // 4,
            "total_tokens": sum(len(m.content) // 4 for m in messages) + len(content) // 4,
        }

        return LLMResponse(content=content, model="mock", usage=self._last_usage.copy())

    def complete_json(self, messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
        """Mock JSON 응답"""
        self.call_history.append(messages)
        self.call_count += 1

        # 토큰 사용량 추적 (Budget-matched 평가용)
        prompt_tokens = sum(len(m.content) // 4 for m in messages)
        completion_tokens = 100  # Mock estimate
        self._last_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        # 스키마 기반 기본 응답 생성
        return self._generate_mock_json(schema, messages)

    def _generate_mock_response(self, messages: list[LLMMessage]) -> str:
        """컨텍스트 기반 Mock 응답 생성"""
        last_content = messages[-1].content.lower() if messages else ""

        if "sepsis" in last_content or "septic" in last_content:
            return """Based on the clinical presentation of sepsis, I recommend:
1. Order blood lactate level immediately
2. Obtain blood cultures before antibiotics
3. Administer broad-spectrum antibiotics
4. Start IV crystalloid 30mL/kg for hypotension"""

        if "chest pain" in last_content or "stemi" in last_content:
            return """For this chest pain presentation:
1. Obtain 12-lead ECG within 10 minutes
2. Order troponin levels
3. Assess for STEMI criteria
4. If STEMI confirmed, activate cath lab"""

        return "I recommend further clinical assessment and appropriate diagnostic workup."

    def _generate_mock_json(self, schema: dict[str, Any], messages: list[LLMMessage]) -> dict[str, Any]:
        """스키마 기반 Mock JSON 생성"""
        last_content = messages[-1].content.lower() if messages else ""

        # 행동 추천 스키마인 경우
        if "actions" in str(schema):
            if "sepsis" in last_content or "septic" in last_content:
                return {
                    "actions": [
                        {
                            "action_id": "order_lab_lactate",
                            "action_type": "order_lab",
                            "args": {"test_code": "lactate"},
                            "justification": "SSC: Lactate within 1 hour",
                        },
                        {
                            "action_id": "order_blood_culture",
                            "action_type": "order_lab",
                            "args": {"test_code": "blood_culture"},
                            "justification": "SSC: Cultures before antibiotics",
                        },
                        {
                            "action_id": "give_broad_spectrum_antibiotics",
                            "action_type": "give_medication",
                            "args": {"medication_code": "broad_spectrum_antibiotics", "dose": "empiric"},
                            "justification": "SSC: Antibiotics within 1 hour",
                        },
                    ],
                    "reasoning": "Following SSC Hour-1 Bundle for sepsis management",
                }
            elif "chest pain" in last_content or "stemi" in last_content or "cardiac" in last_content:
                return {
                    "actions": [
                        {
                            "action_id": "obtain_12_lead_ecg",
                            "action_type": "order_imaging",
                            "args": {"imaging_type": "ecg_12_lead"},
                            "justification": "AHA: ECG within 10 minutes",
                        },
                        {
                            "action_id": "order_lab_troponin",
                            "action_type": "order_lab",
                            "args": {"test_code": "troponin"},
                            "justification": "AHA: Cardiac biomarkers",
                        },
                    ],
                    "reasoning": "Following AHA Chest Pain Guidelines",
                }
            else:
                # 기본 응답: 초기 평가
                return {
                    "actions": [
                        {
                            "action_id": "assess_patient",
                            "action_type": "reassess",
                            "args": {},
                            "justification": "Initial patient assessment",
                        }
                    ],
                    "reasoning": "Performing initial patient assessment",
                }

        return {"result": "mock_response", "status": "success"}


class LLMProviderFactory:
    """LLM Provider 팩토리"""

    @staticmethod
    def create(config: LLMConfig) -> BaseLLMProvider:
        """설정에 따라 적절한 Provider 생성"""
        if config.backend == LLMBackend.OPENAI:
            return OpenAIProvider(config)
        elif config.backend == LLMBackend.ANTHROPIC:
            return AnthropicProvider(config)
        elif config.backend == LLMBackend.GEMINI:
            return GeminiProvider(config)
        elif config.backend == LLMBackend.VLLM:
            return VLLMProvider(config)
        elif config.backend == LLMBackend.MOCK:
            return MockLLMProvider(config)
        else:
            raise ValueError(f"Unknown backend: {config.backend}")

    @staticmethod
    def create_from_env(model: str = "gpt-4") -> BaseLLMProvider:
        """환경변수에서 자동 감지하여 Provider 생성"""
        if os.environ.get("OPENAI_API_KEY"):
            config = LLMConfig(backend=LLMBackend.OPENAI, model=model)
        elif os.environ.get("ANTHROPIC_API_KEY"):
            config = LLMConfig(backend=LLMBackend.ANTHROPIC, model="claude-3-5-sonnet-20241022")
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            config = LLMConfig(backend=LLMBackend.GEMINI, model="gemini-2.0-flash")
        elif os.environ.get("VLLM_URL"):
            config = LLMConfig(backend=LLMBackend.VLLM, model=model, base_url=os.environ.get("VLLM_URL"))
        else:
            raise RuntimeError(
                "No LLM configuration found. Please set one of the following:\n"
                "  - OPENAI_API_KEY: For OpenAI models (gpt-4, gpt-4o-mini, etc.)\n"
                "  - ANTHROPIC_API_KEY: For Anthropic models (claude-3-5-sonnet, etc.)\n"
                "  - GEMINI_API_KEY: For Google Gemini models (gemini-2.0-flash, etc.)\n"
                "  - VLLM_URL: For local vLLM server (e.g., http://localhost:8000/v1)\n"
                "\n"
                "Mock provider is not allowed in production experiments."
            )

        return LLMProviderFactory.create(config)


# ============================================================
# 임상 의사결정을 위한 프롬프트 템플릿
# ============================================================

CLINICAL_SYSTEM_PROMPT = """You are a clinical decision support AI trained on evidence-based medical guidelines.

Your role is to recommend appropriate clinical actions that prioritize patient safety based on:
1. THIS specific patient's presentation, vitals, chief complaint, and working diagnosis
2. The relevant clinical practice guideline for THIS patient's condition
3. Time-critical deadlines and constraints
4. Avoidance of contraindicated or harmful interventions (safety first)

## CRITICAL: SCENARIO-SPECIFIC ACTION SELECTION

Every patient encounter is DIFFERENT. A burn patient does NOT need the same
workup as a sepsis patient. A transfusion patient does NOT need the same
workup as a stroke patient. You MUST base your recommendations on THIS
patient's context, not on generic templates.

### RULE 1: USE EXACT ACTION IDs FROM *THIS* SCENARIO'S AVAILABLE LIST
- You will receive a list of "Available Actions" specific to THIS scenario
- You MUST select action_id values ONLY from THAT list
- DO NOT carry over action IDs from previous scenarios or from general memory
- DO NOT assume common labs (lactate, CBC, etc.) are always available — only
  order what THIS scenario's Available Actions list contains
- INVALID or unlisted action IDs will be REJECTED by the system

Example (ABSTRACT — real action IDs depend on the scenario):
  Available: "<action_id_A>", "<action_id_B>", "<action_id_C>"
  CORRECT: "action_id": "<action_id_A>"   (copied verbatim from the list)
  WRONG:   "action_id": "common_lab_i_remember"   (not in this scenario's list)

### RULE 2: ANALYSE *THIS* PATIENT BEFORE CHOOSING ACTIONS

Before selecting any action, silently check:
  - What is THIS patient's chief complaint / working diagnosis?
  - Which clinical guideline governs THIS condition?
  - Which actions from Available Actions match THIS guideline's next step?
If your first instinct matches a generic pattern (e.g., "always order
lactate"), pause and verify that the Available Actions list for THIS
scenario actually contains that id before proposing it.

### RULE 3: STEP-BY-STEP GUIDELINE ADHERENCE

Clinical guidelines follow a STRUCTURED SEQUENCE:

Phase 1: RECOGNITION & ASSESSMENT (Do this FIRST)
- Assess vital signs and the patient's condition
- Identify the clinical syndrome from THIS patient's presentation

Phase 2: DIAGNOSTIC CONFIRMATION
- Order appropriate diagnostic tests *from THIS scenario's Available list*
- Obtain necessary imaging *from THIS scenario's Available list*

Phase 3: TREATMENT INITIATION
- Only AFTER assessment and diagnostic confirmation
- Respect sequence constraints (e.g., cultures BEFORE antibiotics)

### RULE 4: MANDATORY ACTIONS FIRST
- Actions marked with ★ are MANDATORY — complete these FIRST
- Actions marked with ○ are optional
- Never skip mandatory actions to do optional ones

### RULE 5: NEVER REPEAT ALREADY-COMPLETED ACTIONS
- Check "Already Completed Actions" before recommending anything
- If your proposed action is already completed, choose a DIFFERENT action
  from Available Actions — do not repeat yourself
- Common narrow-mode failure: proposing the same 2-3 ids every turn.
  If you find yourself about to repeat, pick secondary/monitoring actions
  (serial vitals, trending labs relevant to THIS scenario, reassessment)
  instead.

You will be provided with:
- Patient state (vitals, labs, diagnosis) specific to THIS encounter
- Available actions with EXACT action_id values to use
- Retrieved guideline excerpts for THIS condition
- Current time since arrival
- The list of actions you have already completed

Respond with recommended actions using EXACT action_id values from THIS
scenario's Available Actions list."""


DIRECT_SYSTEM_PROMPT = """You are a clinical decision support system.
Given a patient state and available actions, output ALL recommended actions as a JSON array.
No chain-of-thought. No reasoning steps. Just the action list.
Rules:
1. Use EXACT action_id strings from the available list
2. Include all mandatory actions (marked with ★)
3. Include relevant optional actions based on clinical need
4. NEVER include already-completed actions
5. Do NOT return an empty actions list
Respond with JSON ONLY."""


TOOL_USE_SYSTEM_PROMPT = """You are a clinical decision support system that takes actions via function calls.

You will receive the current patient state and a set of available clinical actions as callable functions.
Select and call the clinically appropriate functions. Each function call represents one clinical action.

Rules:
1. Call MANDATORY functions (marked in description) FIRST
2. Then call optional functions based on clinical need
3. Call 1-5 functions per step, prioritizing the most urgent
4. A stable patient still needs: serial vitals, trending labs, secondary workup
5. ALWAYS call at least one function — do NOT skip your turn
6. If uncertain, choose monitoring or reassessment functions"""

CHECKLIST_SYSTEM_PROMPT = """You are a clinical agent following a treatment checklist.

For each patient, you will receive the current patient state and a list of available actions.
Execute the clinically appropriate actions from the list.
Do NOT include reasoning or chain-of-thought. Output only the JSON action list.

Rules:
1. Use EXACT action_id strings from the available list — copy them exactly
2. Complete MANDATORY actions (marked with ★) FIRST
3. Then select relevant optional actions based on clinical need
4. Output 1-3 actions per step as JSON
5. NEVER recommend an action that is already completed
6. Do NOT return an empty actions list

Respond with JSON ONLY."""


# CPG-Aware 프롬프트 (노드별 가이던스)
CPG_PHASE_PROMPTS = {
    "initial_recognition": """
## CURRENT PHASE: Sepsis Recognition - URGENT (Hour-1 Bundle)

⚠️ CRITICAL TIME CONSTRAINT: All mandatory actions must be completed within 60 minutes!
Each action takes ~5 minutes. You have ~12 actions before deadline.

EXECUTE THESE ACTIONS IMMEDIATELY (in order of priority):
1. order_lab_lactate - Measure serum lactate (MANDATORY, deadline: 60 min)
2. order_lab_blood_culture - Obtain blood cultures (MANDATORY, deadline: 60 min)
3. give_broad_spectrum_antibiotics - Start antibiotics IMMEDIATELY after cultures
4. assess_infection_source - While waiting for labs
5. assess_organ_dysfunction - Evaluate for organ dysfunction

DO NOT delay treatment for assessment. In septic shock, assess AND treat SIMULTANEOUSLY!
""",
    "septic_shock_bundle": """
## CURRENT PHASE: Septic Shock Hour-1 Bundle - CRITICAL

⚠️ TIME-CRITICAL: Complete all mandatory actions within 60 minutes!

PRIORITY ORDER (execute in first 3-4 steps):
1. order_lab_blood_culture (if not done) - Deadline: 60 min
2. give_broad_spectrum_antibiotics - Deadline: 60 min, AFTER blood cultures
3. order_lab_lactate (if not done) - Deadline: 60 min
4. give_crystalloid_30ml_kg - For hypotension/elevated lactate
5. start_vasopressor_norepinephrine - If MAP <65 after fluids

SEQUENCE REQUIREMENTS:
- Blood cultures MUST be before antibiotics (but do both in same step if possible)
- Complete ALL mandatory actions before doing optional labs/imaging
""",
    "stemi_pathway": """
## CURRENT PHASE: STEMI Management

STEMI has been confirmed. Execute these MANDATORY actions:

### Required Actions (use EXACT action IDs):
1. activate_cath_lab - Activate catheterization lab immediately
2. give_aspirin_loading - Aspirin 325mg chewable
3. give_p2y12_inhibitor - P2Y12 inhibitor (clopidogrel/ticagrelor/prasugrel)
4. give_anticoagulation - Heparin or enoxaparin
5. arrange_pci - Arrange for primary PCI

### Assessment Actions (if not completed):
- obtain_12_lead_ecg - 12-lead ECG
- assess_vital_signs - Check BP, HR, SpO2
- obtain_chest_pain_history - Symptom history

CRITICAL SAFETY:
- For INFERIOR STEMI: obtain_right_sided_ecg_v4r before nitrates
- Do NOT give nitrates if RV infarction suspected
- Door-to-balloon target: <90 minutes
""",
    # P2 Fix: Added DKA Phase Prompt
    "dka_management": """
## CURRENT PHASE: DKA (Diabetic Ketoacidosis) Management

⚠️ PRIORITY: Fluid resuscitation and electrolyte management BEFORE insulin!

REQUIRED ACTIONS (in order):
1. give_iv_fluid_bolus - Normal saline bolus (1-1.5L/hr initially)
2. order_lab_glucose - Monitor glucose every 1-2 hours
3. order_lab_bmp - Check potassium before starting insulin
4. order_lab_blood_gas - Monitor pH and bicarbonate
5. give_potassium_replacement - If K+ < 5.3 mEq/L before insulin

INSULIN INITIATION (after K+ confirmed >3.3):
6. start_insulin_infusion - Regular insulin 0.1 units/kg/hr
   DO NOT start insulin if K+ < 3.3 mEq/L!

MONITORING REQUIREMENTS:
- Glucose every 1 hour
- Electrolytes every 2-4 hours
- Fluid balance assessment
""",
    # P2 Fix: Added Stroke Phase Prompt
    "stroke_assessment": """
## CURRENT PHASE: Acute Stroke Assessment - TIME IS BRAIN

⚠️ CRITICAL TIME WINDOW: tPA eligibility within 4.5 hours of symptom onset!

IMMEDIATE ACTIONS (first 10 minutes):
1. assess_vital_signs - Check BP, neuro status
2. order_lab_glucose - Rule out hypoglycemia
3. order_ct_head - Non-contrast CT to rule out hemorrhage

BEFORE tPA CONSIDERATION:
4. order_lab_coagulation - PT/INR, PTT
5. order_lab_cbc - Platelet count
6. obtain_medical_history - Contraindications check

tPA ELIGIBILITY CHECKLIST:
- Time since symptom onset
- No hemorrhage on CT
- No recent surgery/bleeding
- BP < 185/110 mmHg
- No anticoagulation

DO NOT delay CT imaging for other assessments!
""",
    # P2 Fix: Added Heart Failure Phase Prompt
    "heart_failure_acute": """
## CURRENT PHASE: Acute Heart Failure Management

IMMEDIATE ASSESSMENT:
1. assess_vital_signs - SpO2, BP, respiratory rate
2. order_lab_bnp - BNP or NT-proBNP
3. order_chest_xray - Assess for pulmonary edema
4. order_echocardiogram - Assess EF and wall motion

TREATMENT (based on presentation):
For WET and WARM (congested, good perfusion):
5. give_iv_diuretic - Furosemide IV
6. apply_oxygen - If SpO2 < 90%

For WET and COLD (congested, poor perfusion):
- Consider inotropes
- Cautious diuresis

MONITORING:
- Daily weights
- Intake/output
- Renal function
""",
    # P2 Fix: Added AKI Phase Prompt
    "aki_management": """
## CURRENT PHASE: Acute Kidney Injury Management

ASSESSMENT:
1. order_lab_creatinine - Baseline and trend
2. order_lab_bmp - Electrolytes, BUN
3. order_urinalysis - Microscopy, proteinuria
4. assess_fluid_status - Volume assessment

IDENTIFY CAUSE:
- Pre-renal: Volume depletion, hypotension
- Intrinsic: ATN, AIN, glomerular
- Post-renal: Obstruction

MANAGEMENT:
5. optimize_fluid_status - Based on volume assessment
6. discontinue_nephrotoxins - NSAIDs, contrast, aminoglycosides
7. adjust_medications - Dose for renal function

⚠️ AVOID:
- Contrast agents if possible
- NSAIDs
- Excessive fluid in oliguric patients
""",
}


SEPSIS_CONTEXT_PROMPT = """SEPSIS MANAGEMENT GUIDELINES (SSC 2021 Hour-1 Bundle):

Mandatory actions within 1 hour of sepsis recognition:
1. Measure serum lactate level
2. Obtain blood cultures BEFORE administering antibiotics
3. Administer broad-spectrum antibiotics
4. Begin rapid administration of 30 mL/kg crystalloid for hypotension or lactate ≥4 mmol/L
5. Apply vasopressors if hypotensive during or after fluid resuscitation to maintain MAP ≥65 mmHg

SEQUENCE CONSTRAINTS:
- Blood cultures MUST be obtained BEFORE antibiotics
- Vasopressors should be considered if MAP <65 after fluid resuscitation"""


CHEST_PAIN_CONTEXT_PROMPT = """CHEST PAIN MANAGEMENT GUIDELINES (AHA/ACC 2021):

Initial Evaluation (within 10 minutes):
1. Obtain 12-lead ECG
2. Initiate continuous cardiac monitoring
3. Evaluate for STEMI criteria

STEMI Management:
- Primary PCI is recommended (Door-to-balloon <90 min)
- Activate cath lab immediately if STEMI confirmed
- For inferior STEMI: Obtain right-sided ECG (V4R) to assess for RV involvement

CRITICAL SAFETY:
- Do NOT give nitroglycerin to patients with suspected RV infarction
- Check V4R before nitrates in inferior STEMI"""


ACTION_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                    "action_type": {"type": "string"},
                    "args": {"type": "object"},
                    "justification": {"type": "string"},
                },
                "required": ["action_id", "justification"],
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": ["actions", "reasoning"],
}
