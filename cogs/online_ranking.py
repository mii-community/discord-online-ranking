from datetime import datetime, timezone
from textwrap import dedent

import const
from discord import Embed, Member
from discord.ext.commands import Bot, Cog, Context, command, has_permissions
from discord.ext.tasks import loop
from pymongo import MongoClient


class OnlineRanking(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.cluster = MongoClient(const.MONGO_URL)
        self.datetimes = self.cluster["discord"]["datetime"]
        self.records = self.cluster["discord"]["record"]
        self.send_ranking.start()

    def insert_datetime_now(self, uid, now):
        before_datetime = self.datetimes.find_one({"user_id": uid})
        if before_datetime is None:
            self.datetimes.insert_one({"user_id": uid, "datetime": now})

    def insert_record(self, uid):
        record = self.records.find_one({"user_id": uid})
        if record is None:
            self.records.insert_one({"user_id": uid, "online": 0, "idle": 0, "dnd": 0})

    def setup_db(self):
        now = datetime.now(timezone.utc)
        for member in self.guild.members:
            if member.bot:
                continue
            uid = member.id
            self.insert_datetime_now(uid, now)
            self.insert_record(uid)

    def remove_db(self):
        self.datetimes.remove({})
        self.records.remove({})

    def reset_db(self):
        now = datetime.now(timezone.utc)
        self.datetimes.update_many({}, {"$set": {"datetime": now}})
        self.records.update_many({}, {"$set": {"online": 0, "idle": 0, "dnd": 0}})

    @command()
    @has_permissions(administrator=True)
    async def setd(self, ctx: Context):
        self.setup_db()
        await ctx.send("done")

    @command()
    @has_permissions(administrator=True)
    async def remd(self, ctx: Context):
        self.remove_db()
        await ctx.send("done")

    @command()
    @has_permissions(administrator=True)
    async def resd(self, ctx: Context):
        self.reset_db()
        await ctx.send("done")

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if member.bot:
            return
        uid = member.id
        now = datetime.now(timezone.utc)
        self.insert_datetime_now(uid, now)
        self.insert_record(uid)

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        state = str(before.status)
        if after.bot or state == "offline":
            return
        uid = after.id
        utc = timezone.utc
        now = datetime.now(utc)
        delta = (
            now
            - self.datetimes.find_one({"user_id": uid})["datetime"].replace(tzinfo=utc)
        ).seconds
        new_record = delta + self.records.find_one({"user_id": uid})[state]
        self.datetimes.update_one({"user_id": uid}, {"$set": {"datetime": now}})
        self.records.update_one({"user_id": uid}, {"$set": {state: new_record}})

    @loop(seconds=60)
    async def send_ranking(self):
        # 15:00 in UTC is 0:00 in JST.
        utc = timezone.utc
        now = datetime.now(utc)
        if now.strftime("%H:%M") != "15:00":
            return

        # Forcibly update all databases.
        datetimes = self.datetimes.find()
        for before_datetime in datetimes:
            uid = before_datetime["user_id"]
            try:
                state = str(self.guild.get_member(uid).status)
            except Exception:
                self.datetimes.remove({"user_id": uid})
                self.records.remove({"user_id": uid})
                continue
            if state == "offline":
                continue
            record = self.records.find_one({"user_id": uid})
            delta = (now - before_datetime["datetime"].replace(tzinfo=utc)).seconds
            new_record = record[state] + delta
            self.records.update_one({"user_id": uid}, {"$set": {state: new_record}})

        # Create the ranking embed,
        content = ""
        for rank, record in enumerate(self.records.find().sort([("online", -1)]), 1):
            if len(content) >= 1900:
                break
            online = int(record["online"] / 60)
            if online == 0:
                continue
            content += dedent(
                f"""\
                **{rank} 位** {self.guild.get_member(record['user_id']).mention} **{online} 分**
                IDLE {int(record['idle'] / 60)} 分, DND {int(record['dnd'] / 60)} 分

                """
            )
        embed = Embed(
            title=now.strftime("%Y年%m月%d日"), description=content, timestamp=now
        )
        await self.bot.get_channel(const.CH_ONLINE_RANKING).send(embed=embed)

        self.reset_db()

    @send_ranking.before_loop
    async def before_send_ranking(self):
        # If self.guild is not got after the bot is ready, None is assigned.
        await self.bot.wait_until_ready()
        self.guild = self.bot.get_guild(const.GUILD_ID)


def setup(bot: Bot):
    bot.add_cog(OnlineRanking(bot))
