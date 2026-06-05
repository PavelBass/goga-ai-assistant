"""Периодические задачи"""

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions

from goga import config
from goga.gigachat.agents import get_goga_answer
from goga.gigachat.tools import (
    get_or_create_repository,
    news_mark_shown,
)


async def say_about_daily_standup_leader(
    bot: Bot,
    chats: list[int] | None = None,
    *,
    mark_news_shown: bool = True,
) -> str:
    """Сказать кто сегодня ведущий Daily Standup

    Замеченные особенности:
        - Он может говорить от лица женского пола, реальный пример:
            "Сегодня наш ежедневный утренний ритуал проведет Сергей.
             Уверена, у нас будет продуктивный и вдохновляющий день!"
        - В первых версиях промпта предполагалось, что Гога самостоятельно будет вызывать
            функцию на Python. Он это делал не всегда, используя имя "Павел",
            по всей видимости, взятое из системного промпта. Полагаю, что
            это из-за формулировки "Представь...". Помимо того, что
            он не всегда вызывал функцию, он тратил большое количество запросов в API, а один
            раз ушёл в рекурсию.

    :param bot: экземпляр Телеграм бота
    :param chats: список chat_id для отправки; None — выбрать по режиму
        (production → боевые чаты, иначе — dev-чаты)
    :param mark_news_shown: помечать ли показанные новости как Shown; False —
        режим предпросмотра (тест-показ в dev-чат), новости не «сжигаются»
    :returns: сгенерированный текст объявления (один и тот же для всех чатов)
    :raises Exception: ошибки LLM (get_goga_answer) или отправки в Telegram
        (bot.send_message)
    """
    repository = get_or_create_repository()
    username = repository.today_daily_standup_moderator
    safe_username = username.replace('_', '\\_')
    name = repository.get_name(username)
    mention = f'@{username}'
    leader_display = f'**{name}** ({mention})' if name else f'**{mention}**'
    prompt = 'Гога, необходимо в 8 часов утра, за два часа до Daily Standup, который начинается в 10:00, '
    prompt += 'рассказывать команде о том кто ведущий сегодняшнего Daily Standup в командном чате. '
    prompt += 'Представь, что сейчас утро, 8:00, и твоя очередь сказать команде, '
    prompt += f'что {leader_display} сегодня ведёт Daily Standup. '
    prompt += f'Обязательно укажи в ответе упоминание {mention}, чтобы пользователь получил уведомление. '
    prompt += 'Будь вежливым, приветливым, позитивным и вдохновляющим. '
    prompt += 'Вызови инструмент get_news, чтобы получить новости. '
    prompt += 'Если новости есть, предложи команде ознакомиться с ними: '
    prompt += 'Каждая новость должна быть состоять из ссылки-заголовка и описания. Подробнее:\n'
    prompt += '1. Заголовок должен быть оформлен как ссылка на оригинальную статью и представлен отдельной строкой. Например: [Заголовок новости](ссылка). Перед заголовком можно добавить эмодзи\n'
    prompt += '2. Описание новости должно быть в точности как было получено, без сокращений и спрятано под спойлером (символ ::). Например: :: Описание новости ::\n'
    prompt += 'Если новостей нет, расскажи интересный факт о любой технологии связанной '
    prompt += 'с искусственным интеллектом. Используй эмодзи для оформления.'
    recipients = chats
    if recipients is None:
        recipients = config.CONFIG['chats']['development']
        if config.CONFIG['general']['mode'] == 'production':
            recipients = config.CONFIG['chats']['production']

    token = news_mark_shown.set(mark_news_shown)
    try:
        answer = await get_goga_answer(recipients[0], prompt)
    finally:
        news_mark_shown.reset(token)

    answer = answer.replace(username, safe_username)
    print(answer)
    for chat_id in recipients:
        await bot.send_message(
            chat_id,
            answer,
            parse_mode=ParseMode.MARKDOWN,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    return answer
