"""Тесты ежедневного объявления: режим «ведущий + новости» и news-only

Режим переключается настройкой [daily].announce_moderator в config.toml.
LLM и Telegram замоканы: проверяются выбор промпта, обращение к очереди
ведущих и экранирование username в ответе.
"""

import pytest

from goga import config
from goga.ui.telegram import tasks

pytestmark = pytest.mark.asyncio


@pytest.fixture
def base_config(monkeypatch):
    """Минимальный конфиг без секции [daily] (режим по умолчанию)

    Args:
        monkeypatch: фикстура pytest для подмены атрибутов

    Returns:
        словарь конфига, который можно дополнять в тесте
    """
    cfg = {
        'general': {'mode': 'development'},
        'chats': {'development': [101], 'production': [202]},
    }
    monkeypatch.setattr(config, 'CONFIG', cfg)
    return cfg


@pytest.fixture
def bot(mocker):
    """Мок Телеграм-бота с асинхронным send_message"""
    fake = mocker.Mock()
    fake.send_message = mocker.AsyncMock()
    return fake


@pytest.fixture
def repository_factory(mocker):
    """Мок фабрики DailyRepository: ведущий pavel_bass по имени Павел"""
    repository = mocker.Mock()
    repository.today_daily_standup_moderator = 'pavel_bass'
    repository.get_name.return_value = 'Павел'
    return mocker.patch.object(tasks, 'get_or_create_repository', return_value=repository)


@pytest.fixture
def answer_mock(mocker):
    """Мок LLM-ответа Гоги"""
    return mocker.patch.object(tasks, 'get_goga_answer', mocker.AsyncMock(return_value='Доброе утро!'))


async def test_default_mode_announces_moderator(base_config, bot, repository_factory, answer_mock):
    """Без секции [daily] ведущий выбирается и упоминается в промпте"""
    answer_mock.return_value = 'Сегодня ведёт pavel_bass'
    answer = await tasks.say_about_daily_standup_leader(bot)

    repository_factory.assert_called_once()
    prompt = answer_mock.call_args.args[1]
    assert '@pavel_bass' in prompt
    assert 'get_news' in prompt
    assert answer == 'Сегодня ведёт pavel\\_bass'
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.args[0] == 101


async def test_explicit_true_announces_moderator(base_config, bot, repository_factory, answer_mock):
    """announce_moderator = true эквивалентен режиму по умолчанию"""
    base_config['daily'] = {'announce_moderator': True}
    await tasks.say_about_daily_standup_leader(bot)

    repository_factory.assert_called_once()
    assert '@pavel_bass' in answer_mock.call_args.args[1]


async def test_news_only_skips_moderator(base_config, bot, repository_factory, answer_mock):
    """announce_moderator = false: очередь ведущих не трогается, промпт без упоминаний"""
    base_config['daily'] = {'announce_moderator': False}
    answer = await tasks.say_about_daily_standup_leader(bot)

    repository_factory.assert_not_called()
    prompt = answer_mock.call_args.args[1]
    assert 'get_news' in prompt
    assert '@' not in prompt
    assert 'Не выбирай и не упоминай ведущего' in prompt
    assert answer == 'Доброе утро!'
    bot.send_message.assert_awaited_once()


async def test_news_only_production_recipients(base_config, bot, repository_factory, answer_mock):
    """В production news-only объявление уходит в боевые чаты"""
    base_config['general']['mode'] = 'production'
    base_config['daily'] = {'announce_moderator': False}
    await tasks.say_about_daily_standup_leader(bot)

    assert answer_mock.call_args.args[0] == 202
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.args[0] == 202
