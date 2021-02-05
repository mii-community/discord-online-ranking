from os import getenv

from dotenv import load_dotenv

load_dotenv()

# get token from .env
DISCORD_BOT_TOKEN = getenv("DISCORD_BOT_TOKEN")

# setting
BOT_NAME = "MII ONLINE RANKING"
BOT_PREFIX = "!"
MONGO_URL = str(getenv("MONGO_URL"))
