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
    "jaemmin0" : (628935601466376225, '재민'),
    "hi200000" : (353346301947281418, '현석'),
    "iweondong_" : (573085356291784724, '원동')
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


# ==================== 검 키우기 게임 ====================

SWORD_FILE = "sword_data.json"
SWORD_ATTRIBUTES = ["빛", "어둠", "피", "자연", "마"]

# 검 게임 데이터 로딩/저장 함수
def load_sword_data():
    if os.path.exists(SWORD_FILE):
        with open(SWORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_sword_data(data):
    with open(SWORD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

sword_data = load_sword_data()

# 강화 확률 함수
def get_enhancement_rate(current_level):
    rates = {
        0: 100,   # 0->1: 100%
        1: 90,    # 1->2: 90%
        2: 85,    # 2->3: 85%
        3: 80,    # 3->4: 80%
        4: 75,    # 4->5: 75%
        5: 70,    # 5->6: 70%
        6: 65,    # 6->7: 65%
        7: 60,    # 7->8: 60%
        8: 50,    # 8->9: 55%
        9: 40,    # 9->10: 50%
        10: 30,   # 10->11: 45%
        11: 20,   # 11->12: 40%
        12: 10,   # 12->13: 35%
        13: 5,   # 13->14: 30%
        14: 3     # 14->15: 4%
    }
    return rates.get(current_level, 0)

# 강화 유지 확률 (실패 시 레벨 유지할 확률)
def get_maintain_rate(current_level):
    if current_level <= 5:
        return 0  # 낮은 레벨은 유지 없음
    elif current_level <= 10:
        return 10  # 중간 레벨은 10%
    else:
        return 15  # 높은 레벨은 15%

# 강화 비용 계산
def get_enhancement_cost(current_level):
    if current_level == 0:
        return 10  # 0->1: 10골드
    elif current_level == 14:
        return 100000  # 14->15: 10만골드
    else:
        # 0->1은 10골, 14->15는 10만골 사이를 지수적으로 증가
        base = 10
        target = 100000
        return int(base * ((target / base) ** (current_level / 14)))

# 검 판매 가격 계산
def get_sword_price(level):
    if level == 0:
        return 0
    elif level == 1:
        return 50
    elif level == 15:
        return 700000
    else:
        # 1레벨 50골, 15레벨 70만골 사이를 지수적으로 증가
        base = 50
        target = 700000
        return int(base * ((target / base) ** ((level - 1) / 14)))

# 결투 승률 계산 (레벨 차이 기반)
def calculate_duel_win_rate(attacker_level, defender_level):
    level_diff = attacker_level - defender_level
    if level_diff >= 5:
        return 0.95  # 5레벨 이상 차이면 95%
    elif level_diff >= 3:
        return 0.85  # 3레벨 이상 차이면 85%
    elif level_diff >= 1:
        return 0.70  # 1레벨 이상 차이면 70%
    elif level_diff == 0:
        return 0.50  # 같은 레벨이면 50%
    elif level_diff >= -1:
        return 0.30  # 1레벨 낮으면 30%
    elif level_diff >= -3:
        return 0.15  # 3레벨 낮으면 15%
    else:
        return 0.05  # 5레벨 이상 낮으면 5%

# 결투 골드 획득량 계산
def calculate_duel_gold(winner_level, loser_level, loser_gold):
    level_diff = winner_level - loser_level
    if level_diff > 0:
        # 레벨이 높은 사람이 이긴 경우: 소량
        steal_rate = 0.05 + (level_diff * 0.01)  # 5% + 레벨차이당 1%
        steal_rate = min(steal_rate, 0.15)  # 최대 15%
    else:
        # 레벨이 낮은 사람이 이긴 경우: 많은 양
        steal_rate = 0.20 + (abs(level_diff) * 0.05)  # 20% + 레벨차이당 5%
        steal_rate = min(steal_rate, 0.40)  # 최대 50%
    
    return int(loser_gold * steal_rate)

# 서버의 왕(15레벨) 찾기
def find_king(server_id):
    for uid, data in sword_data.items():
        if data.get("server_id") == server_id and data.get("sword_level", 0) == 15:
            return uid
    return None

# 하루 결투 횟수 초기화 (자정 체크)
def reset_daily_duel_count(uid):
    today = datetime.now(KST).date()
    user_data = sword_data.get(uid, {})
    last_duel_date = user_data.get("last_duel_date")
    
    if last_duel_date != str(today):
        user_data["duel_count_today"] = 0
        user_data["last_duel_date"] = str(today)
        sword_data[uid] = user_data
        save_sword_data(sword_data)

# 검 시작 명령어
@bot.tree.command(name="검시작", description="검 키우기 게임을 시작합니다")
async def 검시작(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    server_id = interaction.guild.id
    
    if uid in sword_data:
        await interaction.response.send_message("❗ 이미 게임을 시작하셨습니다! `/검정보` 명령어로 현재 상태를 확인하세요.")
        return
    
    sword_data[uid] = {
        "gold": 100000,
        "sword_level": 0,
        "sword_attribute": None,
        "server_id": server_id,
        "duel_count_today": 0,
        "last_duel_date": str(datetime.now(KST).date())
    }
    save_sword_data(sword_data)
    
    embed = discord.Embed(
        title="⚔️ 검 키우기 게임 시작!",
        description=f"{interaction.user.display_name} 님이 게임을 시작했습니다!",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 시작 골드", value="100,000 골드", inline=False)
    embed.add_field(name="⚔️ 검 레벨", value="0 레벨 (속성 없음)", inline=False)
    embed.add_field(name="💡 다음 단계", value="`/강화` 명령어로 검을 강화하세요!", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 검 정보 명령어
@bot.tree.command(name="검정보", description="내 검 정보를 확인합니다")
async def 검정보(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    
    if uid not in sword_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = sword_data[uid]
    level = user_data.get("sword_level", 0)
    attribute = user_data.get("sword_attribute", "없음")
    gold = user_data.get("gold", 0)
    
    embed = discord.Embed(
        title=f"⚔️ {interaction.user.display_name} 님의 검 정보",
        color=discord.Color.blue()
    )
    embed.add_field(name="💰 골드", value=f"{gold:,} 골드", inline=True)
    embed.add_field(name="⚔️ 검 레벨", value=f"{level} 레벨", inline=True)
    embed.add_field(name="✨ 속성", value=attribute if attribute != "없음" else "속성 없음", inline=True)
    
    if level == 15:
        embed.add_field(name="👑 칭호", value="왕의 검", inline=False)
    
    if level < 15:
        next_rate = get_enhancement_rate(level)
        next_cost = get_enhancement_cost(level)
        embed.add_field(name="📈 다음 강화", value=f"성공률: {next_rate}% | 비용: {next_cost:,} 골드", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 강화 명령어
@bot.tree.command(name="강화", description="검을 강화합니다")
async def 강화(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    server_id = interaction.guild.id
    
    if uid not in sword_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = sword_data[uid]
    # 서버 ID 업데이트 (기존 데이터 호환성)
    user_data["server_id"] = server_id
    current_level = user_data.get("sword_level", 0)
    
    if current_level >= 15:
        await interaction.response.send_message("❗ 이미 최고 레벨(15레벨)입니다!")
        return
    
    # 강화 비용 확인
    enhancement_cost = get_enhancement_cost(current_level)
    current_gold = user_data.get("gold", 0)
    
    if current_gold < enhancement_cost:
        await interaction.response.send_message(f"❗ 강화 비용이 부족합니다! 필요 골드: {enhancement_cost:,} 골드 (보유: {current_gold:,} 골드)")
        return
    
    # 강화 비용 차감
    user_data["gold"] = current_gold - enhancement_cost
    
    success_rate = get_enhancement_rate(current_level)
    maintain_rate = get_maintain_rate(current_level)
    roll = random.randint(1, 100)
    
    embed = discord.Embed(title="⚔️ 강화 결과", color=discord.Color.orange())
    embed.add_field(name="💰 강화 비용", value=f"{enhancement_cost:,} 골드 소모", inline=False)
    
    # 성공
    if roll <= success_rate:
        new_level = current_level + 1
        user_data["sword_level"] = new_level
        
        # 0->1 강화 시 속성 부여
        if current_level == 0 and new_level == 1:
            attribute = random.choice(SWORD_ATTRIBUTES)
            user_data["sword_attribute"] = attribute
            embed.add_field(name="✨ 속성 부여!", value=f"**{attribute}** 속성이 부여되었습니다!", inline=False)
        
        # 15레벨 달성 시 왕의 검 체크
        if new_level == 15:
            king_uid = find_king(server_id)
            if king_uid and king_uid != uid:
                # 기존 왕과 자동 결투
                king_data = sword_data[king_uid]
                embed.add_field(
                    name="⚔️ 왕의 검 결투 발생!",
                    value=f"기존 왕 <@{king_uid}>과 자동으로 결투가 시작됩니다!",
                    inline=False
                )
                
                # 결투 진행
                attacker_win_rate = calculate_duel_win_rate(new_level, king_data.get("sword_level", 0))
                duel_roll = random.random()
                
                if duel_roll < attacker_win_rate:
                    # 새 왕 승리
                    stolen_gold = calculate_duel_gold(new_level, king_data.get("sword_level", 0), king_data.get("gold", 0))
                    user_data["gold"] = user_data.get("gold", 0) + stolen_gold
                    king_data["gold"] = max(0, king_data.get("gold", 0) - stolen_gold)
                    king_data["sword_level"] = 8  # 패자는 8레벨부터 재시작
                    king_data["sword_attribute"] = None  # 속성 초기화
                    
                    embed.add_field(
                        name="👑 새로운 왕 등극!",
                        value=f"승리! {stolen_gold:,} 골드를 획득했습니다!\n기존 왕은 8레벨부터 재시작합니다.",
                        inline=False
                    )
                else:
                    # 기존 왕 승리
                    user_data["sword_level"] = 8  # 패자는 8레벨부터 재시작
                    user_data["sword_attribute"] = None
                    stolen_gold = calculate_duel_gold(king_data.get("sword_level", 0), new_level, user_data.get("gold", 0))
                    king_data["gold"] = king_data.get("gold", 0) + stolen_gold
                    user_data["gold"] = max(0, user_data.get("gold", 0) - stolen_gold)
                    
                    embed.add_field(
                        name="👑 기존 왕의 승리",
                        value=f"패배... 기존 왕이 승리했습니다. 8레벨부터 재시작합니다.",
                        inline=False
                    )
                
                sword_data[king_uid] = king_data
            else:
                embed.add_field(
                    name="👑 왕의 검 획득!",
                    value="축하합니다! 당신이 이 서버의 왕이 되었습니다!",
                    inline=False
                )
        
        embed.add_field(
            name="✅ 강화 성공!",
            value=f"{current_level}레벨 → **{new_level}레벨**",
            inline=False
        )
        embed.color = discord.Color.green()
    
    # 실패 (유지 가능)
    elif roll <= success_rate + maintain_rate:
        embed.add_field(
            name="⚠️ 강화 실패 (레벨 유지)",
            value=f"{current_level}레벨 유지",
            inline=False
        )
        embed.color = discord.Color.orange()
    
    # 실패 (레벨 하락)
    else:
        user_data["sword_level"] = 0
        user_data["sword_attribute"] = None
        embed.add_field(
            name="❌ 강화 실패",
            value=f"{current_level}레벨 → **0레벨** (속성 초기화)",
            inline=False
        )
        embed.color = discord.Color.red()
    
    sword_data[uid] = user_data
    save_sword_data(sword_data)
    
    await interaction.response.send_message(embed=embed)

# 검 판매 명령어
@bot.tree.command(name="검판매", description="현재 검을 판매합니다")
async def 검판매(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    
    if uid not in sword_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = sword_data[uid]
    level = user_data.get("sword_level", 0)
    
    if level == 0:
        await interaction.response.send_message("❗ 0레벨 검은 판매할 수 없습니다!")
        return
    
    price = get_sword_price(level)
    user_data["gold"] = user_data.get("gold", 0) + price
    user_data["sword_level"] = 0
    user_data["sword_attribute"] = None
    
    sword_data[uid] = user_data
    save_sword_data(sword_data)
    
    embed = discord.Embed(
        title="💰 검 판매 완료",
        description=f"{level}레벨 검을 {price:,} 골드에 판매했습니다!",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 현재 골드", value=f"{user_data['gold']:,} 골드", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 결투 명령어
@bot.tree.command(name="결투", description="다른 유저와 결투합니다")
@app_commands.describe(상대="결투할 상대를 멘션하세요")
async def 결투(interaction: discord.Interaction, 상대: discord.Member):
    attacker_uid = str(interaction.user.id)
    defender_uid = str(상대.id)
    server_id = interaction.guild.id
    
    if attacker_uid == defender_uid:
        await interaction.response.send_message("❗ 자신과는 결투할 수 없습니다!")
        return
    
    if attacker_uid not in sword_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    if defender_uid not in sword_data:
        await interaction.response.send_message(f"❗ {상대.display_name} 님은 게임을 시작하지 않았습니다!")
        return
    
    # 같은 서버인지 확인
    attacker_data = sword_data[attacker_uid]
    defender_data = sword_data[defender_uid]
    
    if attacker_data.get("server_id") != server_id or defender_data.get("server_id") != server_id:
        await interaction.response.send_message("❗ 같은 서버의 유저와만 결투할 수 있습니다!")
        return
    
    # 하루 결투 횟수 체크
    reset_daily_duel_count(defender_uid)
    defender_data = sword_data[defender_uid]
    
    if defender_data.get("duel_count_today", 0) >= 10:
        await interaction.response.send_message(f"❗ {상대.display_name} 님은 오늘 이미 10번의 결투를 받았습니다!")
        return
    attacker_level = attacker_data.get("sword_level", 0)
    defender_level = defender_data.get("sword_level", 0)
    
    if attacker_level == 0:
        await interaction.response.send_message("❗ 0레벨 검으로는 결투할 수 없습니다!")
        return
    
    if defender_level == 0:
        await interaction.response.send_message(f"❗ {상대.display_name} 님의 검 레벨이 0입니다!")
        return
    
    # 결투 진행
    win_rate = calculate_duel_win_rate(attacker_level, defender_level)
    roll = random.random()
    
    embed = discord.Embed(
        title="⚔️ 결투 결과",
        color=discord.Color.purple()
    )
    
    if roll < win_rate:
        # 공격자 승리
        stolen_gold = calculate_duel_gold(attacker_level, defender_level, defender_data.get("gold", 0))
        attacker_data["gold"] = attacker_data.get("gold", 0) + stolen_gold
        defender_data["gold"] = max(0, defender_data.get("gold", 0) - stolen_gold)
        
        embed.add_field(
            name="✅ 승리!",
            value=f"{interaction.user.display_name} 님이 승리했습니다!",
            inline=False
        )
        embed.add_field(
            name="💰 획득 골드",
            value=f"{stolen_gold:,} 골드를 획득했습니다!",
            inline=False
        )
        embed.color = discord.Color.green()
    else:
        # 방어자 승리
        stolen_gold = calculate_duel_gold(defender_level, attacker_level, attacker_data.get("gold", 0))
        defender_data["gold"] = defender_data.get("gold", 0) + stolen_gold
        attacker_data["gold"] = max(0, attacker_data.get("gold", 0) - stolen_gold)
        
        embed.add_field(
            name="❌ 패배...",
            value=f"{상대.display_name} 님이 승리했습니다!",
            inline=False
        )
        embed.add_field(
            name="💰 손실 골드",
            value=f"{stolen_gold:,} 골드를 잃었습니다...",
            inline=False
        )
        embed.color = discord.Color.red()
    
    # 결투 횟수 증가
    defender_data["duel_count_today"] = defender_data.get("duel_count_today", 0) + 1
    defender_data["last_duel_date"] = str(datetime.now(KST).date())
    
    sword_data[attacker_uid] = attacker_data
    sword_data[defender_uid] = defender_data
    save_sword_data(sword_data)
    
    await interaction.response.send_message(embed=embed)

# 검 랭킹 명령어
@bot.tree.command(name="검랭킹", description="검 레벨 상위 10명을 확인합니다")
async def 검랭킹(interaction: discord.Interaction):
    server_id = interaction.guild.id
    
    # 같은 서버의 유저만 필터링
    server_users = {
        uid: data for uid, data in sword_data.items()
        if data.get("server_id") == server_id and data.get("sword_level", 0) > 0
    }
    
    if not server_users:
        await interaction.response.send_message("❗ 랭킹 정보가 없습니다.")
        return
    
    # 레벨 기준 정렬
    sorted_users = sorted(server_users.items(), key=lambda x: (x[1].get("sword_level", 0), x[1].get("gold", 0)), reverse=True)
    
    embed = discord.Embed(title="🏆 검 레벨 랭킹 TOP 10", color=discord.Color.gold())
    
    for idx, (uid, data) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(uid))
            level = data.get("sword_level", 0)
            attribute = data.get("sword_attribute", "없음")
            gold = data.get("gold", 0)
            
            title = f"{idx}. {user.display_name}"
            if level == 15:
                title += " 👑"
            
            value = f"레벨 {level} | {attribute} 속성 | {gold:,} 골드"
            embed.add_field(name=title, value=value, inline=False)
        except:
            continue
    
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

