from datetime import datetime

import const
from discord import Member
from discord.ext.commands import Bot, Cog, Context, command
from pymongo import MongoClient


class OnlineRanking(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.cluster = MongoClient(const.MONGO_URL)
        self.datetimes = self.cluster["discord"]["datetime"]
        self.records = self.cluster["discord"]["record"]

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if after.bot:
            return

        state = str(before.status)
        if state == "offline":
            return

        before_datetime = self.datetimes.find_one({"user_id": after.id})
        now_datetime = datetime.now()
        if before_datetime is None:
            self.datetimes.insert_one({"user_id": after.id, "datetime": now_datetime})
            return
        self.datetimes.update_one(
            {"user_id": after.id}, {"$set": {"datetime": now_datetime}}
        )

        record = self.records.find_one({"user_id": after.id})
        delta_sec = (now_datetime - before_datetime["datetime"]).seconds
        if record is None:
            self.records.insert_one({"user_id": after.id, state: delta_sec})
            return
        try:
            new_record = record[state] + delta_sec
        except KeyError:
            new_record = delta_sec
        self.records.update_one({"user_id": after.id}, {"$set": {state: new_record}})


def setup(bot: Bot):
    bot.add_cog(OnlineRanking(bot))
