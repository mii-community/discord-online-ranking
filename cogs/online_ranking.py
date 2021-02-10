from datetime import datetime, timezone
from textwrap import dedent

import const
from discord import Embed, Member
from discord.ext.commands import Bot, Cog, Context, command
from discord.ext.tasks import loop
from pymongo import MongoClient


class OnlineRanking(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.cluster = MongoClient(const.MONGO_URL)
        self.datetimes = self.cluster["discord"]["datetime"]
        self.records = self.cluster["discord"]["record"]
        self.send_ranking.start()

    @command(name="setd")
    async def setup_db(self, ctx: Context):
        now = datetime.now()
        for member in self.guild.members:
            if member.bot:
                continue
            uid = member.id
            before_datetime = self.datetimes.find_one({"user_id": uid})
            if before_datetime is None:
                self.datetimes.insert_one({"user_id": uid, "datetime": now})
            record = self.records.find_one({"user_id": uid})
            if record is None:
                self.records.insert_one(
                    {"user_id": uid, "online": 0, "idle": 0, "dnd": 0}
                )
        await ctx.send("done")

    @command(name="remd")
    async def remove_db(self, ctx: Context):
        self.datetimes.remove({})
        self.records.remove({})
        await ctx.send("done")

    def update_db(self):
        now = datetime.now()
        self.datetimes.update_many({}, {"$set": {"datetime": now}})
        self.records.update_many({}, {"$set": {"online": 0, "idle": 0, "dnd": 0}})

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if member.bot:
            return
        uid = member.id
        datetime = self.datetimes.find_one({"user_id": uid})
        now = datetime.now()
        if datetime is None:
            self.datetimes.insert_one({"user_id": uid, "datetime": now})
        record = self.records.find_one({"user_id": uid})
        if record is None:
            self.records.insert_one({"user_id": uid, "online": 0, "idle": 0, "dnd": 0})

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if after.bot:
            return
        state = str(before.status)
        if state == "offline":
            return
        uid = after.id
        before_datetime = self.datetimes.find_one({"user_id": uid})
        now = datetime.now()
        self.datetimes.update_one({"user_id": uid}, {"$set": {"datetime": now}})
        delta_sec = (now - before_datetime["datetime"]).seconds
        record = self.records.find_one({"user_id": uid})
        new_record = delta_sec + record[state]
        self.records.update_one({"user_id": uid}, {"$set": {state: new_record}})

    @loop(seconds=60)
    async def send_ranking(self):
        check_time = datetime.now(timezone.utc).strftime("%H:%M")
        if check_time != "15:00":
            return
        datetimes = self.datetimes.find()
        now = datetime.now()
        for before_datetime in datetimes:
            delta_sec = (now - before_datetime["datetime"]).seconds
            uid = before_datetime["user_id"]
            record = self.records.find_one({"user_id": uid})
            state = str(self.guild.get_member(uid).status)
            if state == "offline":
                continue
            new_record = delta_sec + record[state]
            self.records.update_one({"user_id": uid}, {"$set": {state: new_record}})

        # create the ranking embed
        rankings = self.records.find().sort([("online", -1)])
        content = ""
        for i, record in enumerate(rankings, 1):
            online = record["online"] / 60
            if int(online) == 0:
                continue
            user = self.guild.get_member(record["user_id"])
            idle = record["idle"] / 60
            dnd = record["dnd"] / 60
            content += dedent(
                f"""\
                {i}位 {user.mention} {int(online)} 分
                    IDLEは {int(idle)} 分, DNDは {int(dnd)} 分

                """
            )
            if len(content) >= 1920:
                break
        online_ranking = self.bot.get_channel(const.CH_ONLINE_RANKING)
        embed = Embed(
            title=f"{datetime.now(timezone.utc).strftime('%Y年%m月%d日')} のオンライン時間ランキング",
            description=content,
        )
        await online_ranking.send(embed=embed)
        self.update_db()

    @send_ranking.before_loop
    async def before_send_ranking(self):
        print("waiting...")
        await self.bot.wait_until_ready()
        self.guild = self.bot.get_guild(const.GUILD_ID)


def setup(bot: Bot):
    bot.add_cog(OnlineRanking(bot))
