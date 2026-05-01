"""Short, JSON-safe messages when OpenAI / embedding calls fail behind proxies or filters."""


def format_openai_exception(exc: BaseException) -> str:
    raw = str(exc).strip()
    lower = raw.lower()
    if "<html" in lower or "web page blocked" in lower:
        return (
            "The embedding API was blocked by your network (often enterprise policy blocks "
            "public OpenAI). Set OPENAI_API_BASE to an approved OpenAI-compatible URL if your "
            "org provides one (e.g. internal gateway), use VPN/off-corporate Wi‑Fi for development, "
            "or ask IT to allow api.openai.com."
        )
    if len(raw) > 800:
        return raw[:800] + "…"
    return raw or type(exc).__name__
