from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = 1.0
    top_p: float | None = 1.0
    n: int | None = 1
    stream: bool | None = False
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = 0
    frequency_penalty: float | None = 0
    logit_bias: dict[str, float] | None = None
    user: str | None = None

    class Config:
        extra = "allow"  # Allow extra fields (like 'tools', 'functions') to pass through
