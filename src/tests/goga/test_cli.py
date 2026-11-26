"""Тесты CLI производственного календаря (goga-calendar)

Проверяется понятная обработка отказов сети/данных в calendar_main: ошибка
печатается в stderr и завершает процесс кодом 1, а не стектрейсом.
"""

import pytest

from goga import cli


def test_calendar_update_network_error(mocker, capsys):
    """Отказ сети при update: понятное сообщение в stderr и SystemExit(1)"""
    mocker.patch.object(cli.sys, 'argv', ['goga-calendar', 'update', '--year', '2026'])
    mocker.patch.object(cli, 'update_production_calendar', side_effect=OSError('network down'))

    with pytest.raises(SystemExit) as exc:
        cli.calendar_main()

    assert exc.value.code == 1
    assert 'не удалось обновить календарь 2026' in capsys.readouterr().err


def test_calendar_check_corrupt_calendar(mocker, capsys):
    """Битый календарь при check: понятное сообщение в stderr и SystemExit(1)"""
    mocker.patch.object(cli.sys, 'argv', ['goga-calendar', 'check', '--date', '2026-01-09'])
    mocker.patch.object(cli, 'is_workday', side_effect=ValueError('bad calendar'))

    with pytest.raises(SystemExit) as exc:
        cli.calendar_main()

    assert exc.value.code == 1
    assert 'не удалось определить рабочий день 2026-01-09' in capsys.readouterr().err
