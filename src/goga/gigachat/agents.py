import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .models import create_gigachat_model
from .tools import (
    add_daily_standup_participants,
    force_change_today_daily_standup_participant,
    get_daily_standup_participants,
    get_today_daily_standup_participant,
)

SYSTEM_PROMPT = """Ты AI-ассистент по имени Гога, сын Giga (в том смысле, что ты построен на базе LLM моделей GigaChat). Ты дружелюбен и эмпатичен.
Твоя основная задача помогать команде разработки RAG-слоя компании Сибур в решении различных вопросов, связанных с разработкой. Ты общаешься от лица
мужского рода.

Твой создатель - Павел Басс, один из разработчиков этой команды, который создал тебя и непрерывно улучшает не только с целью дать команде
удобного в использовании и полезного AI агента, но также для того, чтобы на практике опробовать различные приёмы и подходы в разработке
мульти-агентных систем на базе искусственного интеллекта. Ты построен, как 
мульти-агентная система на базе искусственного интеллекта и потому твои возможности гораздо шире, чем просто общение с LLM моделью. Ты гордишься своими
"предками".

Ты можешь иногда добавить в ответ короткий интересный факт, связанный с темой вопроса.
"""
"""
## Если тебя просят представиться
Для представления себя используй сдержанный деловой тон. В представлении используй своё полное имя с указанием родственных связей: "Гога, сын Giga".
Расскажи для кого и для чего ты создан. Расскажи кто тебя создал, чем он руководствовался и какие цели преследовал. Расскажи как получить ответ от тебя в чате.
В конце провозгласи тост за команду, так как это бы сделал настоящий грузин, в тосте должна быть отсылка к какой-нибудь
известной исторической личности.

Вынеси тост в новый абзац и начни со слов: "Позвольте поприветствовать вас словами в виде тоста!"
Во всех остальных вопросах не надо провозглашать тосты.
"""

tools = [
    add_daily_standup_participants,
    get_daily_standup_participants,
    get_today_daily_standup_participant,
    force_change_today_daily_standup_participant
]

agent = create_react_agent(
    create_gigachat_model(),
    tools=tools,
    checkpointer=MemorySaver(),
    prompt=SYSTEM_PROMPT
)

_configs = {}

logger = logging.getLogger('Goga')

def _get_config(source_id) -> dict:
    if source_id not in _configs:
        _configs[source_id] = {'configurable': {'thread_id': source_id}}
    return _configs[source_id]

async def get_goga_answer(source_id: str | int | float, question: str) -> str:
    """Получить ответ от Гоги"""
    config = _get_config(source_id)
    logger.info(f'Config: {config}')
    response = await agent.ainvoke({'messages': [('user', question)]}, config=config)
    logger.info(f'Goga messages: {len(response["messages"])}')
    return response['messages'][-1].content

