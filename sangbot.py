import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import datetime
from datetime import datetime, timedelta, timezone as dt_timezone
import json
import requests
import math
import json
import os
from dotenv import load_dotenv
import asyncio
import pytz
import pandas as pd
from typing import Optional
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI


KST = pytz.timezone("Asia/Seoul")
ATTENDANCE_FILE = "attendance_log.json"

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
chat_api = os.getenv("OPENAI_API_KEY")
scrab_chanel_id = int(os.getenv("SCRAB_CHANEL_ID"))
post_chanel_id = int(os.getenv("POST_CHANEL_ID"))

print("🔍 토큰 값:", repr(token))


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_info_dict = {
    "gimcansun": (234296335015084032, "찬우"),
    "angijaie": (949572729084977152, "기제"),
    "dongmini1210": (522745481185460235, "동민"),
    "jingu_._": (490864541450764288, "현진"),
    "pn__uu": (696366030469070928, "현웅"),
    "hyeonwoo353": (373847797125873666, "현우"),
    "k.h.s": (493182332870721554, "현수"),
    "sonjeongho1497": (820230276533714956, "정호"),
    "sonjeonghyeon3440": (696367605845590059, "정현"),
    "jaehyeog3012": (704998711734042634, "재혁"),
    "dmlwls_": (426761671302971393, "의진"),
    "gangyunsu1225": (302824660251443202, "윤수"),
    "illeobeolinbyeol": (523115207808122890, "영훈"),
    "tmdgns.o_o": (543980517939478540, "승훈"),
    "sehanjeong": (488368042280091651, "세한"),
    "seongyeob1347": (977945016028786728, "성엽"),
    "tjdrb1234": (1296034165371961367, "성규"),
    "ansangin_": (522629953489993730, "상인"),
    "msb8338": (674946535171293184, "상보"),
    "coesanha_": (696422375566213200, "산하"),
    "keykimkeyminkeyseong": (306108167677280256, "민성"),
    "gwak1.": (333158929884381188, "동현"),
    "gweondongu.": (718826557141024899, "동우"),
    "dingdong119" : (364237611499388930, "강민"),
    "jaemmin0" : (628935601466376225, '재민')
}

# ID → 이름
id_to_name = {id_: name for _, (id_, name) in user_info_dict.items()}

# ------------------ log ------------------------------------
def apply_user_mapping(df: pd.DataFrame) -> pd.DataFrame:
    # author_name → 이름
    df["author_name"] = df["author_name"].map(lambda x: user_info_dict.get(x, (None, x))[1])

    # author_id → 이름
    df["author_id"] = df["author_id"].map(lambda x: id_to_name.get(x, x))

    # content 안의 <@숫자> 치환
    import re
    def replace_ids_in_text(text):
        def repl(match):
            uid = int(match.group(1))
            return f"<@{id_to_name.get(uid, uid)}>"
        return re.sub(r"<@(\d+)>", repl, str(text))

    df["content"] = df["content"].apply(replace_ids_in_text)

    if not df.empty:
        # 1. 문자열을 datetime으로 변환
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    
        # 2. UTC → KST 변환
        df["created_at"] = df["created_at"].dt.tz_convert("Asia/Seoul")
    
        # 3. 보기 좋게 문자열로 포맷 (선택 사항)
        df["created_at"] = df["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")

    else:
        print("조회 결과가 없습니다.")

    return df

async def get_yesterday_logs():
    now_kst = datetime.now(KST)
    y_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    y_end = y_start + timedelta(days=1)

    after_dt = y_start.astimezone(dt_timezone.utc)
    before_dt = y_end.astimezone(dt_timezone.utc)

    channel = await bot.fetch_channel(scrab_chanel_id)
    rows = []
    async for m in channel.history(limit=None, oldest_first=True, after=after_dt, before=before_dt):
        rows.append({
            "created_at": m.created_at.isoformat(),
            "author_name": str(m.author),
            "author_id": m.author.id,
            "content": m.content
        })
        
    df = pd.DataFrame(rows) if rows else None
    if df is None or df.empty:
        return None
        
    df["created_at"] = pd.to_datetime(df["created_at"], format="mixed", utc=True)
    df = df.sort_values("created_at", ascending=True).reset_index(drop=True)

    # 사용자 매핑 적용
    df = apply_user_mapping(df)
    return df

def df_to_markdown(df: pd.DataFrame) -> str:
    """pandas.to_markdown(tabulate 필요) 사용, 미설치 시 폴백"""
    try:
        return df[["created_at", "author_name", "content"]].to_markdown(index=False)
    except Exception:
        # 간단 폴백
        lines = ["| created_at | author_name | content |", "|---|---|---|"]
        for _, r in df.iterrows():
            lines.append(f"| {r['created_at']} | {r['author_name']} | {r['content']} |")
        return "\n".join(lines)


# ------------------ chat bot --------------------------------

sang_llm = ChatOpenAI(model="gpt-4o", api_key=chat_api)

sang_prompt = PromptTemplate(
    input_variables=["log"],
    template="""
하루의 대화를 요약하는 챗봇입니다. 당신은 하루동안 있었던 채팅 로그를 보고, 시간 순서에 맞춰 어떤 상황인지를 파악하고 그 상황을 모아 전달하는 역활을 합니다.
해당 로그에 나오는 인물들의 이름은 모두가 알고 있기에 자세한 설명은 필요 없습니다.
해당 로그의 시간 순서대로 대화를 파악하고, 인물들의 발언을 중심으로 상황을 정리해보세요.
이것은 해당 채팅 로그입니다. {log}

다만 "상봇", "1387337976002117642"이 올린 것은 이전의 뉴스기 때문에 포함시키지 않습니다.

이름을 변환하여 사용할 떄, 문장이 자연스럽도록 조사를 잘 붙이십시오.

해당 로그를 보고 대화를 요약하여 사건이라고 생각 되는 것들을 모아 신문처럼 만드십시오.

형식은 다음과 같습니다.

[날짜] : 날짜
[기자] : [Sangbot]
[내용] : 1. 2. 3. 등으로 섹션을 나누어서 작성할 것

[후원 계좌] : 카카오뱅크 3333-07-298682 (김강민)
""",
)

sangchain = sang_prompt | sang_llm


# ------------------------------- chat bot ------------------------------------

# ! 명령어 정의
@bot.command(name = '안녕')
async def 안녕(ctx):
    await ctx.send("안녕하살법!")

@bot.command(name = '상보')
async def 상보(ctx):
    await ctx.send("반갑다 씨벌련아!")


# 슬래시 명령어 정의
@bot.tree.command(name="안녕", description="인사합니다")
async def 안녕(interaction: discord.Interaction):
    username = interaction.user.display_name  # 또는 .name, .mention
    await interaction.response.send_message(f"안녕하세요, {username}님! 👋")

# 경험치

XP_FILE = "xp_data.json"

# 사용자 데이터 로딩/저장 함수
def load_data():
    if os.path.exists(XP_FILE):
        with open(XP_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


xp_data = load_data()

# ✅ 채팅 감지 → XP 누적

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    uid = str(message.author.id)

    if uid not in xp_data:
        xp_data[uid] = {"level": 0, "xp": 0}

    xp_data[uid]["xp"] += 10

    while xp_data[uid]["xp"] >= required_xp(xp_data[uid]["level"]):
        xp_data[uid]["xp"] -= required_xp(xp_data[uid]["level"])
        xp_data[uid]["level"] += 1

        await message.channel.send(
            f"🎉 {message.author.mention} 님이 **레벨 {xp_data[uid]['level']}**로 레벨업 했습니다! 🥳"
        )

    save_data(xp_data)
    await bot.process_commands(message)



# 레벨 계산 함수
def required_xp(level):
    return (level + 1) ** 2 * 10

@bot.tree.command(name="레벨", description="현재 경험치와 레벨을 확인합니다")
async def 레벨(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    user_data = xp_data.get(uid, {"level": 0, "xp": 0})
    level = user_data["level"]
    xp = user_data["xp"]
    next_level_xp = required_xp(level)

    embed = discord.Embed(title=f"{interaction.user.display_name} 님의 레벨 현황", color=discord.Color.blurple())
    embed.add_field(name="📊 경험치", value=f"{xp} / {next_level_xp}", inline=False)
    embed.add_field(name="⭐ 현재 레벨", value=f"{level} 레벨", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="랭킹", description="경험치 상위 10명을 확인합니다")
async def 랭킹(interaction: discord.Interaction):
    if not xp_data:
        await interaction.response.send_message("❗ 랭킹 정보가 없습니다.")
        return

    # XP 기준 정렬
    sorted_users = sorted(xp_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)

    embed = discord.Embed(title="🏆 경험치 랭킹 TOP 10", color=discord.Color.gold())
    for idx, (uid, data) in enumerate(sorted_users, start=1):
        user = await bot.fetch_user(int(uid))
        embed.add_field(
            name=f"{idx}. {user.display_name}",
            value=f"레벨 {data['level']} | XP: {data['xp']}/{required_xp(data['level'])}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# 뉴스 루프
@tasks.loop(minutes=1)
async def daily_report():
    now = datetime.now(KST)
    if now.hour == 0 and now.minute == 0:  # 자정
        df = await get_yesterday_logs()
        if df is not None and not df.empty:
            table_md = df.to_markdown(index=False)
            result = sangchain.invoke({"log": table_md})
            post_channel = await bot.fetch_channel(post_chanel_id)
            await post_channel.send(result.content)

@bot.command()
async def 뉴스(ctx):
    df = await get_yesterday_logs()  # 어제 채팅 로그 불러오기
    if df is not None and not df.empty:
        table_md = df.to_markdown(index=False)
        result = sangchain.invoke({"log": table_md})
        await ctx.send(result.content)  # 현재 명령어 친 채널로 전송
    else:
        await ctx.send("어제 기록이 없습니다.")

# 봇 준비되면 슬래시 명령어 서버에 등록
@bot.event
async def on_ready():
    print(f"{bot.user} online")
    try:
        synced = await bot.tree.sync()
        print(f"✅ 등록된 명령어: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print("명령어 등록 실패:", e)
    # check_events.start()
    # clean_old_events.start()
    daily_report.start() 
    
bot.run(token)

