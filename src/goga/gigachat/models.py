from dotenv import (
    find_dotenv,
    load_dotenv,
)
from langchain_gigachat.chat_models import GigaChat

load_dotenv(find_dotenv())

def create_gigachat_model():
    """Фабрика моделей GigaChat"""
    model = GigaChat(
        model='GigaChat-2-Max',
        verify_ssl_certs=False,
    )
    return model


