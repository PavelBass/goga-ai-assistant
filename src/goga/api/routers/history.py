"""Эндпоинты истории чата (только чтение, защищены Bearer-токеном)

Позволяют потребителю (командному сайту) отрисовать чат «как в Telegram»:
список чатов, последние сообщения либо N сообщений перед/после заданного
(листание истории), и отдача байтов медиафайлов.
"""

from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goga.api.schemas import (
    ChatOut,
    MessageOut,
    MessagesPage,
)
from goga.api.security import require_token
from goga.data.chat_history import ChatHistoryRepository
from goga.db.engine import get_session
from goga.db.models import Message
from goga.utils import get_data_directory

router = APIRouter(
    prefix='/api/v1/chats',
    tags=['chat history'],
    dependencies=[Depends(require_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _to_message_out(message: Message) -> MessageOut:
    """Преобразует ORM-сообщение в схему ответа, проставляя ссылку на медиа

    Args:
        message: ORM-объект сообщения (со связанным media)
    """
    out = MessageOut.model_validate(message)
    if out.media is not None:
        if out.media.downloaded:
            out.media.url = f'/api/v1/chats/{message.chat_id}/media/{out.media.file_unique_id}'
        else:
            out.media.url = None
    return out


@router.get('', response_model=list[ChatOut])
async def list_chats(session: SessionDep):
    """Возвращает список известных чатов"""
    chats = await ChatHistoryRepository(session).list_chats()
    return list(chats)


@router.get('/{chat_id}/messages', response_model=MessagesPage)
async def list_messages(
    chat_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query(description='Вернуть сообщения перед этим tg_message_id')] = None,
    after_id: Annotated[int | None, Query(description='Вернуть сообщения после этого tg_message_id')] = None,
):
    """Возвращает страницу сообщений чата в хронологическом порядке

    Без курсора — последние ``limit`` сообщений. С ``before_id`` — ``limit``
    сообщений перед указанным (листание вверх). С ``after_id`` — ``limit``
    сообщений после указанного (догрузка новых).
    """
    repository = ChatHistoryRepository(session)
    if before_id is not None:
        messages = await repository.messages_before(chat_id, before_id, limit)
    elif after_id is not None:
        messages = await repository.messages_after(chat_id, after_id, limit)
    else:
        messages = await repository.latest(chat_id, limit)

    oldest_id = messages[0].tg_message_id if messages else None
    newest_id = messages[-1].tg_message_id if messages else None
    has_more = await repository.has_before(chat_id, oldest_id) if oldest_id is not None else False
    return MessagesPage(
        messages=[_to_message_out(message) for message in messages],
        has_more=has_more,
        oldest_id=oldest_id,
        newest_id=newest_id,
    )


@router.get('/{chat_id}/media/{file_unique_id}')
async def get_media(chat_id: int, file_unique_id: str, session: SessionDep):
    """Отдаёт байты медиафайла сообщения

    Raises:
        fastapi.HTTPException: 404, если медиа не найдено, не скачано или файл
            отсутствует на диске
    """
    media = await ChatHistoryRepository(session).get_media(chat_id, file_unique_id)
    if media is None or not media.downloaded or not media.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Медиа не найдено')
    path = get_data_directory() / Path(media.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Файл медиа отсутствует на диске')
    return FileResponse(
        path,
        media_type=media.mime_type or 'application/octet-stream',
        filename=media.file_name or None,
    )
