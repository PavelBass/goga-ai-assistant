import asyncio
import logging
import sys

from goga.ui.telegram.aiogram import run


def main():
    """Точка входа в CLI-приложение"""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(run())

if __name__ == '__main__':
    main()

