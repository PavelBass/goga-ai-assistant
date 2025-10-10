import asyncio
import logging
import sys

from .aiogram import main

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
asyncio.run(main())
