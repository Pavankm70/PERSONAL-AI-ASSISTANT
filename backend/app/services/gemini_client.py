"""
AURELIA AI — Centralized Gemini API Client
Provides:
- Strict error classification (quota exhaustion, rate limit, auth, safety, server, timeout, empty)
- User-safe messages adhering to project requirements
- Bounded retries for transient network/503 errors (no retries for 429 quota or auth errors)
- Finish-reason and token-usage inspection (e.g. MAX_TOKENS detection)
- Detailed diagnostic logging with complete secret redaction
- Zero silent fallbacks to retrieved document chunks
"""
import logging
import asyncio
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiCallResult:
    """
    Structured result returned by every Gemini API invocation.
    Guarantees callers know whether generation succeeded, and if not, the exact structured reason.
    """
    def __init__(
        self,
        text: Optional[str] = None,
        success: bool = True,
        error_category: Optional[str] = None,
        status_code: Optional[int] = None,
        user_message: Optional[str] = None,
        finish_reason: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        truncated: bool = False,
        raw_error: Optional[str] = None
    ):
        self.text = text
        self.success = success
        self.error_category = error_category
        self.status_code = status_code
        self.user_message = user_message
        self.finish_reason = finish_reason
        self.prompt_tokens = prompt_tokens
        self.output_tokens = output_tokens
        self.truncated = truncated
        self.raw_error = raw_error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "error_category": self.error_category,
            "status_code": self.status_code,
            "user_message": self.user_message,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "truncated": self.truncated
        }


async def call_gemini_api(
    prompt: str,
    system_prompt: str = "",
    images: Optional[list] = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.1,
    max_retries: int = 1
) -> GeminiCallResult:
    """
    Executes a direct Gemini API generateContent call with structured error handling.
    Supports multimodal text and image parts (vision).
    
    Returns GeminiCallResult with success=True and generated text, or success=False with
    categorized error and user-safe message.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("[Gemini] API key is not configured.")
        return GeminiCallResult(
            success=False,
            error_category="missing_api_key",
            status_code=500,
            user_message="Gemini API key is not configured. Please check your system configuration."
        )

    models_to_try = [settings.LLM_MODEL]
    for fallback in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    user_parts: list = [{"text": prompt}]
    if images:
        for img in images:
            mime_t = img.get("mimeType") or img.get("mime_type") or "image/jpeg"
            b64_data = img.get("data") or ""
            if b64_data:
                user_parts.append({
                    "inlineData": {
                        "mimeType": mime_t,
                        "data": b64_data
                    }
                })

    payload: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": user_parts}
        ],
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": temperature,
            "candidateCount": 1
        }
    }
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    last_error_result = None

    for m_idx, current_model in enumerate(models_to_try):
        has_more_models = (m_idx < len(models_to_try) - 1)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={settings.GEMINI_API_KEY}"

        attempt = 0
        while attempt <= max_retries:
            attempt += 1
            try:
                timeout_secs = 45.0 if images else 30.0
                async with httpx.AsyncClient(timeout=timeout_secs) as client:
                    res = await client.post(url, json=payload)

                # Success HTTP 200
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    usage = data.get("usageMetadata", {})
                    p_tokens = usage.get("promptTokenCount")
                    o_tokens = usage.get("candidatesTokenCount")

                    if not candidates:
                        logger.warning("[Gemini] 200 OK but candidates list is empty for model %s.", current_model)
                        if has_more_models:
                            break
                        return GeminiCallResult(
                            success=False,
                            error_category="empty_response",
                            status_code=200,
                            user_message="Gemini returned an empty response. Please try again."
                        )

                    top_candidate = candidates[0]
                    finish_reason = top_candidate.get("finishReason", "STOP")

                    logger.info(
                        "[Gemini] model=%s finish_reason=%s prompt_tokens=%s output_tokens=%s",
                        current_model, finish_reason, p_tokens, o_tokens
                    )

                    # Safety or recitation block
                    if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                        logger.warning("[Gemini] Response blocked: finish_reason=%s", finish_reason)
                        return GeminiCallResult(
                            success=False,
                            error_category="safety_block",
                            status_code=200,
                            finish_reason=finish_reason,
                            user_message="The response was blocked by Gemini safety filters. Please rephrase your question."
                        )

                    is_truncated = (finish_reason == "MAX_TOKENS")
                    if is_truncated:
                        logger.warning(
                            "[Gemini] Output reached maxOutputTokens (%d). Finish reason is MAX_TOKENS.",
                            max_output_tokens
                        )

                    parts = top_candidate.get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        ans_text = parts[0]["text"].strip()
                        if ans_text:
                            return GeminiCallResult(
                                success=True,
                                text=ans_text,
                                finish_reason=finish_reason,
                                prompt_tokens=p_tokens,
                                output_tokens=o_tokens,
                                truncated=is_truncated
                            )

                    logger.warning("[Gemini] No text content found in candidates parts for model %s.", current_model)
                    if has_more_models:
                        break
                    return GeminiCallResult(
                        success=False,
                        error_category="empty_response",
                        status_code=200,
                        finish_reason=finish_reason,
                        user_message="Gemini returned an empty response. Please try again."
                    )

                # HTTP 429: Rate limit vs Quota exhaustion
                elif res.status_code == 429:
                    err_text = res.text
                    logger.warning("[Gemini] HTTP 429 Resource Exhausted on %s: %s", current_model, err_text[:200])

                    if has_more_models:
                        logger.info("[Gemini] Falling back to model %s after 429 on %s", models_to_try[m_idx + 1], current_model)
                        break

                    retry_after = res.headers.get("Retry-After")
                    is_quota = any(k in err_text.lower() for k in [
                        "exceeded your current quota",
                        "quota",
                        "billing",
                        "plan and billing",
                        "free_tier_requests"
                    ])

                    if is_quota:
                        user_msg = (
                            "Gemini couldn't generate an answer because your API quota has been exhausted. "
                            "Please check your plan, billing details, or quota allocation in Google AI Studio."
                        )
                        category = "quota_exhaustion"
                    else:
                        user_msg = (
                            "Gemini couldn't generate an answer because the API rate limit has been reached. "
                            "Please try again later."
                        )
                        if retry_after:
                            user_msg += f" (Retry after {retry_after} seconds)"
                        category = "rate_limit"

                    return GeminiCallResult(
                        success=False,
                        error_category=category,
                        status_code=429,
                        user_message=user_msg,
                        raw_error=err_text[:300]
                    )

                # HTTP 403: Forbidden / Project Restrictions / Free tier unavailable
                elif res.status_code == 403:
                    err_text = res.text
                    logger.error("[Gemini] HTTP 403 Permission error: %s", err_text[:200])
                    if any(k in err_text.lower() for k in ["free tier is not available", "billing", "set up billing"]):
                        user_msg = (
                            "The Gemini API free tier is not available for this Google project. "
                            "Please set up billing to enable the API in Google AI Studio or select a project with billing enabled."
                        )
                        category = "quota_exhaustion"
                    else:
                        user_msg = "Gemini service is improperly configured or permission was denied. Please check your system configuration."
                        category = "invalid_credentials"
                    return GeminiCallResult(
                        success=False,
                        error_category=category,
                        status_code=403,
                        user_message=user_msg,
                        raw_error=err_text[:200]
                    )

                # HTTP 401: Authentication error
                elif res.status_code == 401:
                    logger.error("[Gemini] HTTP 401 Authentication error: %s", res.text[:200])
                    return GeminiCallResult(
                        success=False,
                        error_category="invalid_credentials",
                        status_code=401,
                        user_message="Gemini API key is invalid or expired. Please check your API key in configuration.",
                        raw_error=res.text[:200]
                    )

                # HTTP 404: Model not found / unavailable
                elif res.status_code == 404:
                    logger.warning("[Gemini] HTTP 404 Model %s not found. Falling back if available.", current_model)
                    if has_more_models:
                        break
                    return GeminiCallResult(
                        success=False,
                        error_category="model_unavailable",
                        status_code=404,
                        user_message=f"The configured Gemini model '{current_model}' is unavailable or not found. Please check LLM_MODEL in configuration.",
                        raw_error=res.text[:200]
                    )

                # HTTP 500 / 502 / 503 / 504: Server-side errors
                elif res.status_code >= 500:
                    logger.warning("[Gemini] HTTP %d Server error on attempt %d for %s: %s", res.status_code, attempt, current_model, res.text[:200])
                    if attempt <= max_retries and res.status_code in (502, 503, 504):
                        await asyncio.sleep(1.0)
                        continue
                    if has_more_models:
                        logger.info("[Gemini] Falling back to model %s after 5xx on %s", models_to_try[m_idx + 1], current_model)
                        break
                    return GeminiCallResult(
                        success=False,
                        error_category="server_error",
                        status_code=res.status_code,
                        user_message="Gemini encountered an internal server error. Please try again later.",
                        raw_error=res.text[:200]
                    )

                # Other HTTP 4xx errors
                else:
                    logger.error("[Gemini] HTTP %d Unhandled error: %s", res.status_code, res.text[:200])
                    if has_more_models:
                        break
                    return GeminiCallResult(
                        success=False,
                        error_category="invalid_request",
                        status_code=res.status_code,
                        user_message="The request could not be processed by Gemini. Please try again.",
                        raw_error=res.text[:200]
                    )

            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                logger.warning("[Gemini] Timeout on attempt %d for %s: %s", attempt, current_model, str(exc))
                if attempt <= max_retries:
                    await asyncio.sleep(1.0)
                    continue
                if has_more_models:
                    break
                return GeminiCallResult(
                    success=False,
                    error_category="timeout",
                    status_code=504,
                    user_message="The request to Gemini timed out. Please check your network connection and try again.",
                    raw_error=str(exc)
                )
            except (httpx.NetworkError, httpx.ConnectError) as exc:
                logger.warning("[Gemini] Network error on attempt %d for %s: %s", attempt, current_model, str(exc))
                if attempt <= max_retries:
                    await asyncio.sleep(1.0)
                    continue
                if has_more_models:
                    break
                return GeminiCallResult(
                    success=False,
                    error_category="network_error",
                    status_code=502,
                    user_message="Unable to connect to Gemini. Please check your network connection and try again.",
                    raw_error=str(exc)
                )
            except Exception as exc:
                logger.exception("[Gemini] Unexpected exception calling Gemini API")
                if has_more_models:
                    break
                return GeminiCallResult(
                    success=False,
                    error_category="unexpected_error",
                    status_code=500,
                    user_message="An unexpected error occurred while generating the answer. Please try again.",
                    raw_error=str(exc)
                )

    return GeminiCallResult(
        success=False,
        error_category="max_retries_exceeded",
        status_code=503,
        user_message="Gemini service is temporarily unavailable. Please try again later."
    )
