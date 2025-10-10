import asyncio
import logging
import subprocess
import sys

from .aiogram import run

#subprocess.run(
#    [
#        '/usr/bin/curl',
#        '-k',
#        '"https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer"',
#        '-w',
#        '"\n"',
#        '>>',
#        f"'$({sys.executable} -m certifi)'",
#    ],
#    check=True,
#    capture_output=True,
#)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
asyncio.run(run())

