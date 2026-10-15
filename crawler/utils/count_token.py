import tiktoken

def get_token_count(text: str, model_name: str = "gemini-2.5-pro") -> int:
    """Đếm số token thực tế của chuỗi text."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))