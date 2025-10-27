"""Взаимодействие с Гогой через Telegramm на базе aiogram"""
import logging

from rich.logging import RichHandler


def _init_goga_aiogram_logger():
    """Настройка логгера 'Goga aiogram'"""
    _logger = logging.getLogger('Goga aiogram')
    _logger.addHandler(RichHandler())


_init_goga_aiogram_logger()

