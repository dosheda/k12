"""Helpers for API response and error handling."""


def extract_chat_content(response) -> str:
    """Return response.choices[0].message.content with structure checks."""
    choices = getattr(response, "choices", None)
    if not choices:
        raise ValueError("empty API response")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not content:
        raise ValueError("empty API response content")
    return content


def classify_api_error(error: Exception) -> str:
    """Map SDK/network errors to safe user-facing messages."""
    message = str(error)
    if "401" in message or "Invalid API key" in message or "AuthenticationError" in message:
        return "API Key 无效（401 认证失败），请检查 DEEPSEEK_API_KEY。"
    if "402" in message or "Insufficient Balance" in message:
        return "账户余额不足（402），请充值后再试。"
    if "404" in message:
        return "请求的资源不存在（404），请检查模型名称或 API 地址。"
    if "429" in message or "Rate limit" in message:
        return "请求太频繁（429 速率限制），请稍等几秒后再试。"
    if any(code in message for code in ["500", "502", "503", "Server Error"]):
        return "DeepSeek 服务器暂时出错，请稍后重试。"
    if any(word in message for word in ["Connection", "connect", "Network", "timeout"]):
        return "网络连接失败，请检查网络后再试。"
    return "发生未知错误，请稍后重试；如果持续出现，请检查本地配置和网络。"
