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

# # 롤 ck
# @bot.tree.command(name="ck", description="ck 뽑기 (라인 고정 가능)")
# @app_commands.describe(명단="10명의 이름을 입력하세요. 고정할 경우 이름 뒤에 *를 붙이세요.")
# async def ck(interaction: discord.Interaction, 명단: str):
#     names = 명단.strip().split()

#     if len(names) != 10:
#         await interaction.response.send_message("❗ 정확히 10명을 입력해주세요.", ephemeral=True)
#         return

#     positions = ["TOP", "JUNGLE", "MID", "AD", "SUPPORT"]
#     red_fixed = [None] * 5
#     blue_fixed = [None] * 5
#     red_pool = []
#     blue_pool = []

#     # 0~4: Red팀, 5~9: Blue팀
#     for i, raw_name in enumerate(names):
#         fixed = raw_name.endswith("*")
#         name = raw_name.rstrip("*")
#         team = "red" if i < 5 else "blue"
#         idx = i % 5  # 포지션 인덱스

#         if fixed:
#             if team == "red":
#                 red_fixed[idx] = name
#             else:
#                 blue_fixed[idx] = name
#         else:
#             if team == "red":
#                 red_pool.append(name)
#             else:
#                 blue_pool.append(name)

#     # 섞고 고정되지 않은 자리 채우기
#     random.shuffle(red_pool)
#     random.shuffle(blue_pool)

#     for i in range(5):
#         if red_fixed[i] is None:
#             red_fixed[i] = red_pool.pop()
#         if blue_fixed[i] is None:
#             blue_fixed[i] = blue_pool.pop()

#     # 출력 포맷
#     lines = []
#     for i, pos in enumerate(positions):
#         lines.append(f"Red팀 {pos} : {red_fixed[i]} - Blue팀 {pos} : {blue_fixed[i]}")

#     await interaction.response.send_message("\n".join(lines))

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


# 렌덤 추첨

# class RerollView(discord.ui.View):
#     def __init__(self, names: list[str], k: int, allow_duplicate: bool):
#         super().__init__(timeout=60)  # 60초 뒤 자동 비활성화
#         self.names = names
#         self.k = k
#         self.allow_duplicate = allow_duplicate

#     @discord.ui.button(label="🔁 다시 뽑기", style=discord.ButtonStyle.primary)
#     async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
#         result_text = get_lottery_result(self.names, self.k, self.allow_duplicate)
#         await interaction.response.edit_message(content=f"🎯 다시 추첨 결과:\n{result_text}", view=self)

# def get_lottery_result(names: list[str], k: int, allow_duplicate: bool) -> str:
#     if allow_duplicate:
#         selected = [random.choice(names) for _ in range(k)]
#         counter = {}
#         for name in selected:
#             counter[name] = counter.get(name, 0) + 1

#         # 결과 정렬
#         sorted_counter = sorted(counter.items(), key=lambda x: x[1], reverse=True)
#         result_lines = [f"{name} : {count}회" for name, count in sorted_counter]

#         # 승자 판단
#         top_count = sorted_counter[0][1]
#         top_names = [name for name, count in sorted_counter if count == top_count]

#         if len(top_names) == 1:
#             result_lines.append(f"\n🎉 **당첨**: {top_names[0]} ({top_count}회)")
#         else:
#             tie_list = ", ".join(top_names)
#             result_lines.append(f"\n⚖️ **무승부**: {tie_list} ({top_count}회씩)")

#     else:
#         selected = random.sample(names, k)
#         result_lines = [f"{name}" for name in selected]

#     return "\n".join(result_lines)

# @bot.tree.command(name="복불복", description="N명 중 K명 추첨")
# @app_commands.describe(명단="띄어쓰기로 구분된 이름들", 추첨="추첨할 인원 수", 추첨방법="1: 중복허용, 2: 중복비허용")
# async def 복불복(interaction: discord.Interaction, 명단: str, 추첨: int, 추첨방법: str):
#     names = 명단.strip().split()
#     k = 추첨
#     how = 추첨방법.strip()
    
#     if not names or k < 1:
#         await interaction.response.send_message("❗ 명단과 추첨 수를 올바르게 입력해주세요.", ephemeral=True)
#         return
#     if how not in ['1', '2', '중복허용', '중복비허용']:
#         await interaction.response.send_message("❗ 추첨방법은 '1'(중복허용) 또는 '2'(중복비허용) 중 하나로 입력해주세요.", ephemeral=True)
#         return
#     if how in ['2', '중복비허용'] and k > len(names):
#         await interaction.response.send_message("❗ 추첨 인원이 명단보다 많습니다 (중복 비허용).", ephemeral=True)
#         return

#     allow_duplicate = how in ['1', '중복허용']
#     result_text = get_lottery_result(names, k, allow_duplicate)

#     view = RerollView(names, k, allow_duplicate)
#     await interaction.response.send_message(f"🎯 추첨 결과:\n{result_text}", view=view)

# # 익명
# @bot.tree.command(name="익명", description="익명으로 이 채널에 메시지를 보냅니다")
# @app_commands.describe(내용="하고 싶은 말을 적어주세요")
# async def 익명(interaction: discord.Interaction, 내용: str):
#     channel = interaction.channel

#     if len(내용.strip()) < 5:
#         await interaction.response.send_message("❗ 메시지는 5자 이상이어야 합니다.", ephemeral=True)
#         return

#     # 익명 메시지 Embed 구성
#     embed = discord.Embed(
#         title="📢 익명 메시지",
#         description=내용,
#         color=discord.Color.dark_gray()
#     )
#     embed.set_footer(text="보낸 사람 정보는 저장되지 않습니다")

#     # 메시지 전송
#     await channel.send(embed=embed)

#     # 사용자에게는 조용히 알림
#     await interaction.response.send_message("✅ 익명 메시지가 전송되었습니다.", ephemeral=True)


# 이벤트 & 지각 관리
EVENT_FILE = "events.json"

# Load and save functions for events data
# def load_events():
#     if os.path.exists(EVENT_FILE):
#         with open(EVENT_FILE, "r") as f:
#             return json.load(f)
#     return {}

# def save_events(data):
#     with open(EVENT_FILE, "w") as f:
#         json.dump(data, f, indent=4)

# events = load_events()

# # Schedule reminder check
# @tasks.loop(minutes=1)
# async def check_events():
#     now = datetime.now(KST)
#     for time_str, data in events.items():
#         event_time = KST.localize(datetime.strptime(time_str, "%Y-%m-%d %H:%M"))

#         if isinstance(data.get("notified"), bool) or "notified" not in data:
#             data["notified"] = {"30": False, "10": False, "0": False}

#         mentions = ' '.join([f'<@{uid}>' for uid in data.get("participants", [])])
#         channel = bot.get_channel(data["channel_id"])

#         if not data["notified"]["30"] and now + timedelta(minutes=30) >= event_time:
#             await channel.send(f"🔔 **[30분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
#             data["notified"]["30"] = True

#         if not data["notified"]["10"] and now + timedelta(minutes=10) >= event_time:
#             await channel.send(f"⏰ **[10분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
#             data["notified"]["10"] = True

#         if not data["notified"]["0"] and now >= event_time:
#             await channel.send(f"🚀 **[일정 시작]** `{data['title']}` 일정이 시작되었습니다!\n{mentions}")
#             data["notified"]["0"] = True
        
#             # 출석 현황 Embed 생성
#             참여자 = list(map(str, data.get("participants", [])))
#             출석자 = list(data.get("attendance", {}).keys())
#             미출석자 = [uid for uid in 참여자 if uid not in 출석자]
        
#             embed = discord.Embed(
#                 title=f"📋 `{data['title']}` 출석 현황",
#                 description=f"🕒 일정 시간: {time_str}",
#                 color=discord.Color.teal()
#             )
        
#             if 출석자:
#                 출석_멘션 = "\n".join([f"<@{uid}> ✅" for uid in 출석자])
#                 embed.add_field(name="출석자", value=출석_멘션, inline=False)
#             else:
#                 embed.add_field(name="출석자", value="없음", inline=False)
        
#             if 미출석자:
#                 미출석_멘션 = "\n".join([f"<@{uid}> ❌" for uid in 미출석자])
#                 embed.add_field(name="미출석자", value=미출석_멘션, inline=False)
#             else:
#                 embed.add_field(name="미출석자", value="없음", inline=False)
        
#             await channel.send(embed=embed)

# # 지난 일정 삭제
# @tasks.loop(minutes=60)
# async def clean_old_events():
#     now_kst = datetime.utcnow() + timedelta(hours=9)  # KST
#     if now_kst.hour != 6:
#         return

#     ATTENDANCE_FILE = "attendance_log.json"

#     to_delete = []
#     logs = load_attendance_log()
#     for time_str, data in list(events.items()):
#         start_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         if start_time.date() < now_kst.date():
#             if time_str not in logs:  # ✅ 중복 저장 방지
#                 save_attendance_log_entry(time_str, data)
#             to_delete.append(time_str)

#     for t in to_delete:
#         del events[t]

#     if to_delete:
#         save_events(events)
#         print(f"[자동 삭제] 다음 일정 삭제됨: {to_delete}")



# # ✅ 일정 생성 (제목 + 시간만 모달로 받기)
# class ScheduleCreateModal(discord.ui.Modal, title="일정 생성"):
#     title_input = discord.ui.TextInput(label="일정 제목")
#     time_input = discord.ui.TextInput(label="시작 시간 (YYYY-MM-DD HH:MM)")

#     async def on_submit(self, interaction: discord.Interaction):
#         title = self.title_input.value
#         time_str = self.time_input.value

#         try:
#             datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         except ValueError:
#             await interaction.response.send_message("❗ 시간 형식 오류. 예: 2025-07-01 15:00", ephemeral=True)
#             return

#         if time_str in events:
#             await interaction.response.send_message("❗ 해당 시간에 이미 일정이 존재합니다.", ephemeral=True)
#             return

#         events[time_str] = {
#             "title": title,
#             "participants": [],
#             "channel_id": interaction.channel_id,
#             "notified": {"30": False, "10": False, "0": False},
#             "attendance": {}
#         }
#         save_events(events)
#         await interaction.response.send_message(f"✅ `{title}` 일정이 생성되었습니다!", ephemeral=True)

# @bot.tree.command(name="일정추가", description="일정 제목과 시간만 입력합니다 (참여자는 나중에 등록)")
# async def 일정추가(interaction: discord.Interaction):
#     if not interaction.user.guild_permissions.administrator:
#         await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
#         return
#     await interaction.response.send_modal(ScheduleCreateModal())



# # ✅ 일정 참여 (유저 드롭다운으로 추가)
# class ParticipantSelect(discord.ui.Select):
#     def __init__(self, time_str: str, interaction: discord.Interaction):  # ✅ interaction 추가
#         self.time_str = time_str

#         members = [
#             member for member in interaction.guild.members
#             if not member.bot
#         ]

#         if not members:
#             options = []
#         else:
#             options = [
#                 discord.SelectOption(label=member.display_name, value=str(member.id))
#                 for member in members
#             ][:25]

#         super().__init__(
#             placeholder="참여할 유저를 선택하세요",
#             min_values=1,
#             max_values=min(25, len(options)) if options else 1,  # 🔧 fallback to 1
#             options=options
#         )

#     async def callback(self, interaction: discord.Interaction):
#         selected_ids = [int(uid) for uid in self.values]
#         events[self.time_str]["participants"] = selected_ids
#         save_events(events)
#         await interaction.response.send_message("✅ 참여자가 성공적으로 등록되었습니다.", ephemeral=True)

# class ParticipantSelectView(discord.ui.View):
#     def __init__(self, time_str: str, interaction: discord.Interaction):
#         super().__init__(timeout=60)
#         self.add_item(ParticipantSelect(time_str, interaction))

# @bot.tree.command(name="일정참여", description="기존 일정에 유저를 추가합니다.")
# @app_commands.describe(시간="참여할 일정의 시작 시간 (YYYY-MM-DD HH:MM)")
# async def 일정참여(interaction: discord.Interaction, 시간: str):
#     if not interaction.user.guild_permissions.administrator:
#         await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
#         return

#     if 시간 not in events:
#         await interaction.response.send_message("❗ 해당 시간의 일정이 없습니다.", ephemeral=True)
#         return

#     view = ParticipantSelectView(시간, interaction)
#     await interaction.response.send_message(f"💡 `{events[시간]['title']}` 일정에 참여할 유저를 선택하세요:", view=view, ephemeral=True)


# # 일정 목록 확인
# @bot.tree.command(name="일정목록", description="예정된 일정을 확인합니다")
# async def 일정목록(interaction: discord.Interaction):
#     try:
#         print("[디버그] 일정목록 명령어 실행됨")

#         # 1️⃣ 즉시 응답: 사용자에게 처리 중 메시지 표시
#         await interaction.response.send_message("⏳ 일정을 불러오는 중입니다...", ephemeral=True)
#         print("[디버그] 초기 응답 전송 완료")

#         if not events:
#             await interaction.followup.send("📭 예정된 일정이 없습니다.")
#             print("[디버그] 등록된 일정 없음 - 안내 메시지 전송 완료")
#             return

#         embed = discord.Embed(title="📅 예정된 일정 목록", color=discord.Color.blue())
#         for time_str, data in sorted(events.items()):
#             users = ', '.join([f'<@{uid}>' for uid in data["participants"]])
#             embed.add_field(name=f"{data['title']} ({time_str})", value=f"참여자: {users}", inline=False)

#         await interaction.followup.send(embed=embed)
#         print("[디버그] 일정 목록 전송 완료")

#     except Exception as e:
#         print("[에러] 일정목록 명령어 실패:", e)
#         await interaction.followup.send("❗ 일정 목록을 불러오던 중 오류가 발생했습니다.", ephemeral=True)

# # 일정삭제
# @bot.tree.command(name="일정삭제", description="일정을 삭제합니다")
# @app_commands.describe(time="삭제할 일정의 시작 시간 (YYYY-MM-DD HH:MM)")
# async def 일정삭제(interaction: discord.Interaction, time: str):
#     if not interaction.user.guild_permissions.administrator:
#         await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
#         return

#     try:
#         await interaction.response.defer(thinking=False)
#     except Exception as e:
#         print(f"[에러] 일정삭제 defer 실패: {e}")
#         return

#     if time not in events:
#         await interaction.followup.send("❗ 해당 시간에 등록된 일정이 없습니다.", ephemeral=True)
#         return

#     save_attendance_log_entry(time, events[time])  # ✅ 출석 정보 저장
#     del events[time]
#     save_events(events)
#     await interaction.followup.send(f"🗑 `{time}` 일정이 삭제되었습니다.")


# # 일정전체삭제
# @bot.tree.command(name="일정전체삭제", description="전체 일정을 삭제합니다 (되돌릴 수 없음)")
# async def 일정전체삭제(interaction: discord.Interaction):
#     if not interaction.user.guild_permissions.administrator:
#         await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
#         return

#     await interaction.response.send_message(
#         "⚠️ **정말로 모든 일정을 삭제하시겠습니까?**\n삭제를 원하면 `/일정삭제확인` 명령어를 실행해주세요.",
#         ephemeral=True
#     )


# #전체삭제확인
# @bot.tree.command(name="일정삭제확인", description="일정 전체 삭제를 확정합니다 (되돌릴 수 없음)")
# async def 일정삭제확인(interaction: discord.Interaction):
#     if not interaction.user.guild_permissions.administrator:
#         await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
#         return

#     logs = load_attendance_log()
#     for t, data in events.items():
#         if t not in logs:
#             save_attendance_log_entry(t, data)

#     events.clear()
#     save_events(events)
#     await interaction.response.send_message("🗑 모든 일정이 성공적으로 삭제되었습니다.", ephemeral=True)


# # 출석체크 파일
# def load_attendance_log():
#     if os.path.exists(ATTENDANCE_FILE):
#         with open(ATTENDANCE_FILE, "r") as f:
#             return json.load(f)
#     return {}

# def save_attendance_log_entry(event_time: str, data: dict):
#     logs = load_attendance_log()
#     if event_time not in logs:  # ✅ 중복 저장 방지
#         logs[event_time] = data
#         with open(ATTENDANCE_FILE, "w") as f:
#             json.dump(logs, f, indent=4)


# # 출석 체크
# @bot.tree.command(name="출석", description="출석을 체크합니다")
# async def 출석(interaction: discord.Interaction):
#     uid = str(interaction.user.id)
#     now = datetime.now(KST)  # ✅ 한국 시간 기준으로 now 설정

#     # 출석 가능한 일정 목록 (30분 전 ~ 시작 시각 전)
#     가능한_일정 = []

#     for time_str, data in events.items():
#         event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         event_time = KST.localize(event_time)  # ✅ 이벤트 시간도 한국 시간으로 간주

#         if uid in map(str, data.get("participants", [])):
#             if event_time - timedelta(minutes=30) <= now < event_time:
#                 가능한_일정.append((time_str, data))

#     if not 가능한_일정:
#         await interaction.response.send_message(
#             "❗ 출석 가능한 일정이 없습니다.\n(30분 전부터 일정 시작 전까지만 출석할 수 있습니다.)",
#             ephemeral=True
#         )
#         return

#     # 여러 개 중 하나 선택
#     options = [
#         discord.SelectOption(label=f"{data['title']} ({time_str})", value=time_str)
#         for time_str, data in 가능한_일정
#     ]

#     class AttendanceSelect(discord.ui.Select):
#         def __init__(self):
#             super().__init__(placeholder="출석할 일정을 선택하세요", options=options, min_values=1, max_values=1)

#         async def callback(self, interaction: discord.Interaction):
#             selected_time = self.values[0]
#             events[selected_time]["attendance"][uid] = now.strftime("%Y-%m-%d %H:%M")
#             save_events(events)
#             await interaction.response.send_message(
#                 f"✅ `{events[selected_time]['title']}` 출석 체크 완료!",
#                 ephemeral=True
#             )

#     view = discord.ui.View()
#     view.add_item(AttendanceSelect())
#     await interaction.response.send_message("📝 출석할 일정을 선택하세요:", view=view, ephemeral=True)




# # 지각 통계
# # 기존 지각통계 명령어 부분 전체를 아래 내용으로 교체하세요
# @bot.tree.command(name="지각통계", description="멤버별 지각 횟수 및 평균 지각 시간 (미출석도 지각 포함)")
# async def 지각통계(interaction: discord.Interaction):
#     delay_stats = {}

#     all_data = list(events.items()) + list(load_attendance_log().items())

#     for time_str, data in all_data:
#         start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         for uid in data.get("participants", []):
#             uid = str(uid)
#             attend_time = data.get("attendance", {}).get(uid)

#             if uid not in delay_stats:
#                 delay_stats[uid] = []

#             if attend_time:
#                 delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
#                 if delta > 0:
#                     delay_stats[uid].append(delta)
#                 else:
#                     delay_stats[uid].append(0.0)  # 정시 출석도 기록
#             else:
#                 delay_stats[uid].append(None)  # ❗ 출석하지 않음

#     if not delay_stats:
#         await interaction.response.send_message("📊 아직 지각 통계가 없습니다.")
#         return

#     embed = discord.Embed(title="⏱ 지각 통계 (미출석 포함)", color=discord.Color.orange())
#     for uid, delays in delay_stats.items():
#         user = await bot.fetch_user(int(uid))
#         total_count = len(delays)
#         late_count = sum(1 for d in delays if d is None or d > 0)
#         avg_delay = sum(d for d in delays if d is not None and d > 0) / max(1, sum(1 for d in delays if d and d > 0))

#         embed.add_field(
#             name=user.display_name,
#             value=f"지각 횟수: {late_count}회 / 총 {total_count}회\n평균 지각 시간: {avg_delay:.1f}분",
#             inline=False
#         )

#     await interaction.response.send_message(embed=embed)



# # 지각왕
# @bot.tree.command(name="지각왕", description="지각왕을 보여줍니다 (삭제된 일정 포함)")
# async def 지각왕(interaction: discord.Interaction):
#     delay_counts = {}
#     total_delays = {}

#     # 🔹 현재 남아있는 일정
#     for time_str, data in events.items():
#         start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         for uid in data.get("participants", []):
#             uid = str(uid)
#             attend_time = data.get("attendance", {}).get(uid)
#             if attend_time:
#                 delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
#                 if delta > 0:
#                     delay_counts[uid] = delay_counts.get(uid, 0) + 1
#                     total_delays[uid] = total_delays.get(uid, 0) + delta
#             else:
#                 # 출석하지 않은 경우도 지각으로 처리
#                 delay_counts[uid] = delay_counts.get(uid, 0) + 1

#     # 🔹 삭제된 일정 포함
#     attendance_log = load_attendance_log()
#     for time_str, data in attendance_log.items():
#         start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
#         for uid in data.get("participants", []):
#             uid = str(uid)
#             attend_time = data.get("attendance", {}).get(uid)
#             if attend_time:
#                 delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
#                 if delta > 0:
#                     delay_counts[uid] = delay_counts.get(uid, 0) + 1
#                     total_delays[uid] = total_delays.get(uid, 0) + delta
#             else:
#                 delay_counts[uid] = delay_counts.get(uid, 0) + 1

#     # 🔸 결과 출력
#     if not delay_counts:
#         await interaction.response.send_message("👑 현재 지각왕이 없습니다.")
#         return

#     top_uid = max(delay_counts, key=delay_counts.get)
#     top_user = await bot.fetch_user(int(top_uid))

#     embed = discord.Embed(title="👑 지각왕 (삭제된 일정 포함)", color=discord.Color.red())
#     embed.add_field(name="이름", value=top_user.display_name, inline=True)
#     embed.add_field(name="지각 횟수", value=f"{delay_counts[top_uid]}회", inline=True)
#     embed.add_field(name="누적 지각 시간", value=f"{total_delays.get(top_uid, 0):.1f}분", inline=True)

#     await interaction.response.send_message(embed=embed)



# # 출석률
# @bot.tree.command(name="출석률", description="사용자의 출석률을 확인합니다 (삭제된 일정 포함)")
# @app_commands.describe(대상="출석률을 확인할 대상 (멘션 또는 생략 시 본인)")
# async def 출석률(interaction: discord.Interaction, 대상: discord.User = None):
#     try:
#         await interaction.response.defer(thinking=False)
#     except Exception as e:
#         print(f"[에러] 출석률 defer 실패: {e}")
#         return

#     user = 대상 or interaction.user
#     uid = str(user.id)

#     참여수 = 0
#     출석수 = 0

#     # 🔹 현재 남아있는 일정
#     for data in events.values():
#         if int(uid) in data.get("participants", []):
#             참여수 += 1
#             if uid in data.get("attendance", {}):
#                 출석수 += 1

#     # 🔹 삭제된 일정 포함 (출석 로그)
#     attendance_log = load_attendance_log()
#     for data in attendance_log.values():
#         if int(uid) in data.get("participants", []):
#             참여수 += 1
#             if uid in data.get("attendance", {}):
#                 출석수 += 1

#     embed = discord.Embed(
#         title=f"📊 {user.display_name} 님의 출석률",
#         color=discord.Color.green() if 참여수 else discord.Color.greyple()
#     )

#     if 참여수 == 0:
#         embed.description = "참여한 일정이 없습니다."
#     else:
#         rate = (출석수 / 참여수) * 100
#         embed.add_field(name="✅ 총 참여 일정 수", value=f"{참여수}회", inline=True)
#         embed.add_field(name="📌 출석 완료", value=f"{출석수}회", inline=True)
#         embed.add_field(name="📈 출석률", value=f"{rate:.1f}%", inline=True)

#     await interaction.followup.send(embed=embed)

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

