"""Тесты управления списком ведущих дейли (DailyState и Daily)

Раньше тесты ссылались на класс Pretendents, которого больше нет: логика
переехала в DailyState (очередь претендентов) и Daily (менеджер участников).
"""

from goga.data.daily import (
    Daily,
    DailyState,
)


def test_daily_state_add_member_and_current():
    """add_member добавляет претендентов, current/next_pretendent читают очередь"""
    state = DailyState()
    assert state.has_members is False
    assert state.current_pretendent is None
    assert state.next_pretendent is None

    state.add_member('p1')
    state.add_member('p2')

    assert state.has_members is True
    assert state.current_pretendent == 'p1'
    assert state.next_pretendent == 'p2'


def test_daily_state_pop_order():
    """Извлечение претендентов слева (pop); на пустой очереди возвращает None"""
    state = DailyState()
    for member in ('p1', 'p2', 'p3'):
        state.add_member(member)

    assert state.pop() == 'p1'
    assert state.current_pretendent == 'p2'
    assert state.pop() == 'p2'
    assert state.pop() == 'p3'

    assert state.pop() is None
    assert state.has_members is False


def test_daily_participants_management():
    """Daily хранит участников и отдаёт имя по username"""
    daily = Daily()
    daily.add_participants({'ivan': 'Иван', 'petr': 'Пётр'})

    assert daily.get_all_participants() == {'ivan': 'Иван', 'petr': 'Пётр'}
    assert daily.get_name('ivan') == 'Иван'
    assert daily.get_name('unknown') is None


def test_daily_change_moderator_picks_participant():
    """Смена ведущего назначает кого-то из участников и держит список полным"""
    daily = Daily()
    daily.add_participants({'a': 'A', 'b': 'B', 'c': 'C'})

    daily.change_daily_standup_moderator()

    assert daily.daily_standup_moderator in {'a', 'b', 'c'}
    # после смены всегда известен и следующий ведущий
    assert daily.next_daily_standup_moderator in {'a', 'b', 'c'}
