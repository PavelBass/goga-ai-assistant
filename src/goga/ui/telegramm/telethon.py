"""Взаимодействие с Гогой через Telegramm на базе Telethon"""
from telethon import TelegramClient, events

# Initialize bot and... just the bot!
bot = TelegramClient('goga_ai_assistant', 11111, 'a1b2c3d4').start(bot_token='123123')

@bot.on(events.NewMessage(pattern='/start'))
async def send_welcome(event):
    await event.reply('Howdy, how are you doing?')

@bot.on(events.NewMessage(pattern='(^cat[s]?$|puss)'))
async def cats(event):
    await event.reply('Cats is here 😺', file='data/cats.jpg')

@bot.on(events.NewMessage)
async def echo_all(event):
    await event.reply(event.text)

if __name__ == '__main__':
    bot.run_until_disconnected()
