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

# ------------------ 결투 스토리 생성 --------------------------------

duel_story_prompt = PromptTemplate(
    input_variables=["attacker_name", "defender_name", "attacker_level", "defender_level", 
                     "attacker_attribute", "defender_attribute", "attacker_sword_name", "defender_sword_name",
                     "winner_name", "stolen_gold"],
    template="""
당신은 판타지 세계의 서사시 작가입니다. 두 검사가 결투를 벌인 이야기를 작성해주세요.

결투 정보:
- 공격자: {attacker_name} (검 레벨: {attacker_level}, 속성: {attacker_attribute}, 검 이름: {attacker_sword_name})
- 방어자: {defender_name} (검 레벨: {defender_level}, 속성: {defender_attribute}, 검 이름: {defender_sword_name})
- 승리자: {winner_name}
- 획득 골드: {stolen_gold} 골드

요구사항:
1. 판타지 세계관에 맞는 웅장하고 드라마틱한 스토리를 작성하세요.
2. 두 검사의 검 이름과 속성을 활용하여 전투 장면을 생생하게 묘사하세요.
3. 레벨 차이에 따라 전투의 난이도와 긴장감을 표현하세요.
4. 승리자가 어떻게 승리했는지 구체적으로 묘사하세요.
5. 마지막에 "{winner_name}이(가) 승리했다!"라는 결론을 포함하세요.
6. 스토리는 3줄에서 4줄 정도로 작성하세요.
7. 이모지나 특수문자는 사용하지 마세요.

스토리를 작성해주세요:
""",
)

duel_story_chain = duel_story_prompt | sang_llm


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

        # 맨션 사용 (자동으로 서버 닉네임으로 표시되면서 맨션 기능도 작동)
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

SWORD_FILE_PREFIX = "sword_data_"  # 서버별 파일: sword_data_{server_id}.json
SWORD_ATTRIBUTES = ["빛", "어둠", "피", "자연", "마"]

# 서버별 검 게임 데이터 로딩/저장 함수
def get_sword_file_path(server_id):
    """서버 ID에 따른 데이터 파일 경로 반환"""
    return f"{SWORD_FILE_PREFIX}{server_id}.json"

def load_sword_data(server_id):
    """특정 서버의 검 게임 데이터 로드"""
    file_path = get_sword_file_path(server_id)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_sword_data(server_id, data):
    """특정 서버의 검 게임 데이터 저장"""
    file_path = get_sword_file_path(server_id)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
        9: 45,    # 9->10: 50%
        10: 40,   # 10->11: 45%
        11: 35,   # 11->12: 40%
        12: 30,   # 12->13: 35%
        13: 20,   # 13->14: 30%
        14: 10     # 14->15: 4%
    }
    return rates.get(current_level, 0)

# 강화 유지 확률 (실패 시 레벨 유지할 확률)
def get_maintain_rate(current_level):
    if current_level <= 5:
        return 0  # 낮은 레벨은 유지 없음
    elif current_level <= 10:
        return 40  # 중간 레벨은 10%
    else:
        return 10  # 높은 레벨은 15%

# 강화 멘트 반환 함수
def get_enhancement_message(current_level, new_level, attribute):
    """
    레벨과 속성에 따라 적절한 강화 멘트를 반환
    """
    # 속성별 멘트 딕셔너리
    enhancement_messages = {
        "빛": {
            "attribute_grant": [
                "✨ 신성한 빛이 검에 깃들었다! 빛의 속성이 부여되었다!",
                "✨ 하늘에서 내려온 빛이 검을 감싸며 빛의 속성을 부여했다!",
                "✨ 찬란한 빛이 검에 스며들어 빛의 속성이 깨어났다!"
            ],
            "basic": [
                "✨ 빛의 힘이 조금씩 강해지며 검을 강화시켰다!",
                "✨ 신성한 빛이 검을 감싸며 강화의 기운을 불어넣었다!",
                "✨ 찬란한 빛이 검에 스며들어 더욱 날카로워졌다!"
            ],
            "epic": [
                "✨✨ 강렬한 빛의 폭풍이 검을 감싸며 강화되었다!",
                "✨✨ 신성한 빛이 하늘을 찌를 듯 강해지며 검을 강화시켰다!",
                "✨✨ 찬란한 빛의 기운이 검에 깃들어 압도적인 힘을 발휘한다!"
            ],
            "legendary": [
                "✨✨✨ 신중하게... 빛의 본질이 검에 깃들어 전설에 한 걸음 다가갔다.",
                "✨✨✨ 조심스럽게 강화되는 빛의 힘, 검은 이제 전설의 영역에 접근하고 있다.",
                "✨✨✨ 진지한 강화의 순간, 신성한 빛이 검의 운명을 바꾸고 있다."
            ],
            "king": [
                "👑✨✨✨ 빛의 속성을 가진 왕의 검이 탄생했다!! 신성한 빛이 하늘을 찌르며 새로운 왕이 등극한다!",
                "👑✨✨✨ 빛의 왕이 탄생했다!! 찬란한 빛의 검을 가진 자가 이제 이 땅의 왕이 되었다!",
                "👑✨✨✨ 빛의 속성 검을 가진 왕이 탄생했다!! 신성한 빛이 모든 것을 지배한다!"
            ]
        },
        "어둠": {
            "attribute_grant": [
                "🌑 깊은 어둠이 검에 깃들었다! 어둠의 속성이 부여되었다!",
                "🌑 그림자의 힘이 검을 감싸며 어둠의 속성을 부여했다!",
                "🌑 암흑의 기운이 검에 스며들어 어둠의 속성이 깨어났다!"
            ],
            "basic": [
                "🌑 어둠의 힘이 조금씩 강해지며 검을 강화시켰다!",
                "🌑 그림자의 기운이 검을 감싸며 강화의 힘을 불어넣었다!",
                "🌑 암흑의 마력이 검에 스며들어 더욱 날카로워졌다!"
            ],
            "epic": [
                "🌑🌑 깊은 어둠의 폭풍이 검을 감싸며 강화되었다!",
                "🌑🌑 그림자의 힘이 공간을 가르며 검을 강화시켰다!",
                "🌑🌑 암흑의 기운이 검에 깃들어 압도적인 힘을 발휘한다!"
            ],
            "legendary": [
                "🌑🌑🌑 신중하게... 어둠의 본질이 검에 깃들어 전설에 한 걸음 다가갔다.",
                "🌑🌑🌑 조심스럽게 강화되는 그림자의 힘, 검은 이제 전설의 영역에 접근하고 있다.",
                "🌑🌑🌑 진지한 강화의 순간, 암흑의 기운이 검의 운명을 바꾸고 있다."
            ],
            "king": [
                "👑🌑🌑🌑 어둠의 속성을 가진 왕의 검이 탄생했다!! 깊은 그림자가 세상을 뒤덮으며 새로운 왕이 등극한다!",
                "👑🌑🌑🌑 어둠의 왕이 탄생했다!! 암흑의 검을 가진 자가 이제 이 땅의 왕이 되었다!",
                "👑🌑🌑🌑 어둠의 속성 검을 가진 왕이 탄생했다!! 그림자의 힘이 모든 것을 지배한다!"
            ]
        },
        "피": {
            "attribute_grant": [
                "🩸 생명의 피가 검에 깃들었다! 피의 속성이 부여되었다!",
                "🩸 붉은 피가 검을 감싸며 피의 속성을 부여했다!",
                "🩸 생명의 힘이 검에 스며들어 피의 속성이 깨어났다!"
            ],
            "basic": [
                "🩸 피의 힘이 조금씩 강해지며 검을 강화시켰다!",
                "🩸 생명의 기운이 검을 감싸며 강화의 힘을 불어넣었다!",
                "🩸 붉은 피가 검에 스며들어 더욱 날카로워졌다!"
            ],
            "epic": [
                "🩸🩸 생명의 피가 폭풍처럼 검을 감싸며 강화되었다!",
                "🩸🩸 붉은 피의 힘이 검을 감싸며 강화시켰다!",
                "🩸🩸 생명의 기운이 검에 깃들어 압도적인 힘을 발휘한다!"
            ],
            "legendary": [
                "🩸🩸🩸 신중하게... 생명의 본질이 검에 깃들어 전설에 한 걸음 다가갔다.",
                "🩸🩸🩸 조심스럽게 강화되는 피의 힘, 검은 이제 전설의 영역에 접근하고 있다.",
                "🩸🩸🩸 진지한 강화의 순간, 생명의 기운이 검의 운명을 바꾸고 있다."
            ],
            "king": [
                "👑🩸🩸🩸 피의 속성을 가진 왕의 검이 탄생했다!! 생명의 피가 강물처럼 흐르며 새로운 왕이 등극한다!",
                "👑🩸🩸🩸 피의 왕이 탄생했다!! 붉은 피의 검을 가진 자가 이제 이 땅의 왕이 되었다!",
                "👑🩸🩸🩸 피의 속성 검을 가진 왕이 탄생했다!! 생명의 힘이 모든 것을 지배한다!"
            ]
        },
        "자연": {
            "attribute_grant": [
                "🌿 자연의 힘이 검에 깃들었다! 자연의 속성이 부여되었다!",
                "🌿 대지의 기운이 검을 감싸며 자연의 속성을 부여했다!",
                "🌿 생명의 숨결이 검에 스며들어 자연의 속성이 깨어났다!"
            ],
            "basic": [
                "🌿 자연의 힘이 조금씩 강해지며 검을 강화시켰다!",
                "🌿 대지의 기운이 검을 감싸며 강화의 힘을 불어넣었다!",
                "🌿 생명의 숨결이 검에 스며들어 더욱 날카로워졌다!"
            ],
            "epic": [
                "🌿🌿 대지의 폭풍이 검을 감싸며 강화되었다!",
                "🌿🌿 자연의 힘이 대지를 뒤흔들며 검을 강화시켰다!",
                "🌿🌿 생명의 숨결이 검에 깃들어 압도적인 힘을 발휘한다!"
            ],
            "legendary": [
                "🌿🌿🌿 신중하게... 자연의 본질이 검에 깃들어 전설에 한 걸음 다가갔다.",
                "🌿🌿🌿 조심스럽게 강화되는 대지의 힘, 검은 이제 전설의 영역에 접근하고 있다.",
                "🌿🌿🌿 진지한 강화의 순간, 생명의 숨결이 검의 운명을 바꾸고 있다."
            ],
            "king": [
                "👑🌿🌿🌿 자연의 속성을 가진 왕의 검이 탄생했다!! 대지의 힘이 세상을 뒤흔들며 새로운 왕이 등극한다!",
                "👑🌿🌿🌿 자연의 왕이 탄생했다!! 생명의 숨결이 담긴 검을 가진 자가 이제 이 땅의 왕이 되었다!",
                "👑🌿🌿🌿 자연의 속성 검을 가진 왕이 탄생했다!! 대지의 기운이 모든 것을 지배한다!"
            ]
        },
        "마": {
            "attribute_grant": [
                "🔮 신비로운 마법이 검에 깃들었다! 마의 속성이 부여되었다!",
                "🔮 마법의 빛이 검을 감싸며 마의 속성을 부여했다!",
                "🔮 마력의 기운이 검에 스며들어 마의 속성이 깨어났다!"
            ],
            "basic": [
                "🔮 마법의 힘이 조금씩 강해지며 검을 강화시켰다!",
                "🔮 신비로운 기운이 검을 감싸며 강화의 힘을 불어넣었다!",
                "🔮 마력의 빛이 검에 스며들어 더욱 날카로워졌다!"
            ],
            "epic": [
                "🔮🔮 마법의 폭풍이 검을 감싸며 강화되었다!",
                "🔮🔮 신비로운 마력이 공간을 뒤틀며 검을 강화시켰다!",
                "🔮🔮 마력의 빛이 검에 깃들어 압도적인 힘을 발휘한다!"
            ],
            "legendary": [
                "🔮🔮🔮 신중하게... 마법의 본질이 검에 깃들어 전설에 한 걸음 다가갔다.",
                "🔮🔮🔮 조심스럽게 강화되는 마력의 힘, 검은 이제 전설의 영역에 접근하고 있다.",
                "🔮🔮🔮 진지한 강화의 순간, 신비로운 기운이 검의 운명을 바꾸고 있다."
            ],
            "king": [
                "👑🔮🔮🔮 마법의 왕의 검이 탄생했다!! 신비로운 마력이 공간을 뒤틀며 새로운 왕이 등극한다!",
                "👑🔮🔮🔮 마법의 왕이 탄생했다!! 마력의 빛이 담긴 검을 가진 자가 이제 이 땅의 왕이 되었다!",
                "👑🔮🔮🔮 마법의 검을 가진 왕이 탄생했다!! 신비로운 힘이 모든 것을 지배한다!"
            ]
        }
    }
    
    # 속성이 없으면 기본 멘트 반환
    if not attribute or attribute not in enhancement_messages:
        return f"검의 힘이 강해졌다! ({current_level}레벨 → {new_level}레벨)"
    
    # 레벨 구간에 따라 적절한 멘트 선택
    if current_level == 0 and new_level == 1:
        # 속성 부여
        messages = enhancement_messages[attribute]["attribute_grant"]
    elif new_level == 15:
        # 왕의 검 탄생
        messages = enhancement_messages[attribute]["king"]
    elif new_level >= 11:
        # 전설 구간 (11-14레벨)
        messages = enhancement_messages[attribute]["legendary"]
    elif new_level >= 5:
        # 멋진 구간 (5-10레벨)
        messages = enhancement_messages[attribute]["epic"]
    else:
        # 기본 구간 (1-4레벨)
        messages = enhancement_messages[attribute]["basic"]
    
    # 랜덤으로 하나 선택
    return random.choice(messages)

# 검 이름 생성 함수 (레벨별, 속성별)
def get_sword_name(level, attribute=None):
    """
    레벨과 속성에 따라 적절한 검 이름을 랜덤으로 반환
    """
    if level == 0:
        return "낡은 검"
    
    if not attribute or attribute not in SWORD_ATTRIBUTES:
        return f"{level}레벨 검"
    
    # 속성별 검 이름 풀
    sword_names = {
        "빛": {
            1: ["빛나는 낡은 검", "반짝이는 낡은 검"],
            2: ["반짝이는 검", "빛의 작은 검"],
            3: ["빛의 단검", "신성한 빛의 단검"],
            4: ["신성한 빛의 검", "찬란한 빛의 검"],
            5: ["빛의 장검", "신성한 빛의 장검"],
            6: ["신성한 빛의 장검", "찬란한 빛의 장검"],
            7: ["찬란한 빛의 검", "하늘의 빛 검"],
            8: ["하늘의 빛 검", "성스러운 빛의 검"],
            9: ["성스러운 빛의 검", "신의 빛 검"],
            10: ["신의 빛 검", "영원한 빛의 검"],
            11: ["전설의 빛의 검", "신성한 빛의 전설 검"],
            12: ["신성한 빛의 전설 검", "하늘을 찌르는 빛의 검"],
            13: ["하늘을 찌르는 빛의 검", "신의 빛 전설 검"],
            14: ["신의 빛 전설 검", "영원한 빛의 전설 검"],
            15: ["빛의 절대왕의 검", "신성한 빛의 절대왕의 검", "하늘을 지배하는 빛의 왕의 검", "영원한 빛의 절대왕의 검", "신의 권능을 가진 빛의 왕의 검"]
        },
        "어둠": {
            1: ["어둠에 물든 검", "그림자에 물든 검"],
            2: ["그림자 검", "어둠의 작은 검"],
            3: ["암흑의 단검", "그림자의 단검"],
            4: ["깊은 어둠의 검", "암흑의 검"],
            5: ["어둠의 장검", "그림자의 장검"],
            6: ["그림자의 장검", "암흑의 장검"],
            7: ["암흑의 장검", "심연의 검"],
            8: ["심연의 검", "절대 어둠의 검"],
            9: ["절대 어둠의 검", "그림자 군주의 검"],
            10: ["그림자 군주의 검", "영원한 어둠의 검"],
            11: ["전설의 어둠의 검", "심연의 그림자 전설 검"],
            12: ["심연의 그림자 전설 검", "절대 암흑의 검"],
            13: ["절대 암흑의 검", "그림자 군주의 전설 검"],
            14: ["그림자 군주의 전설 검", "영원한 어둠의 전설 검"],
            15: ["어둠의 절대왕의 검", "심연을 지배하는 그림자 왕의 검", "절대 암흑의 절대왕의 검", "영원한 어둠의 왕의 검", "그림자 군주의 절대왕의 검"]
        },
        "피": {
            1: ["피로 물든 검", "붉은 피의 검"],
            2: ["붉은 검", "피의 작은 검"],
            3: ["생명의 단검", "피의 단검"],
            4: ["피의 갈증 검", "생명의 피 검"],
            5: ["피의 장검", "생명의 장검"],
            6: ["생명의 장검", "붉은 피의 검"],
            7: ["붉은 피의 검", "피의 갈증 장검"],
            8: ["피의 갈증 장검", "생명 흡수 검"],
            9: ["생명 흡수 검", "피의 군주 검"],
            10: ["피의 군주 검", "불멸의 피 검"],
            11: ["전설의 피의 검", "생명 흡수 전설 검"],
            12: ["생명 흡수 전설 검", "불멸의 피의 검"],
            13: ["불멸의 피의 검", "피의 군주 전설 검"],
            14: ["피의 군주 전설 검", "영원한 생명의 전설 검"],
            15: ["피의 절대왕의 검", "생명을 지배하는 피의 왕의 검", "불멸의 피 절대왕의 검", "영원한 생명의 왕의 검", "피의 군주 절대왕의 검"]
        },
        "자연": {
            1: ["자연의 낡은 검", "대지의 낡은 검"],
            2: ["대지의 검", "자연의 작은 검"],
            3: ["생명의 단검", "숲의 단검"],
            4: ["숲의 검", "대지의 힘 검"],
            5: ["자연의 장검", "대지의 장검"],
            6: ["대지의 장검", "숲의 장검"],
            7: ["숲의 장검", "생명의 숨결 검"],
            8: ["생명의 숨결 검", "대지의 힘 검"],
            9: ["대지의 힘 검", "자연의 군주 검"],
            10: ["자연의 군주 검", "영원한 대지의 검"],
            11: ["전설의 자연의 검", "대지의 힘 전설 검"],
            12: ["대지의 힘 전설 검", "생명의 숨결 전설 검"],
            13: ["생명의 숨결 전설 검", "자연의 군주 전설 검"],
            14: ["자연의 군주 전설 검", "영원한 대지의 전설 검"],
            15: ["자연의 절대왕의 검", "대지를 지배하는 자연의 왕의 검", "생명의 숨결 절대왕의 검", "영원한 대지의 왕의 검", "자연의 군주 절대왕의 검"]
        },
        "마": {
            1: ["마법에 물든 검", "마력에 물든 검"],
            2: ["마력의 검", "마법의 작은 검"],
            3: ["신비의 단검", "마법의 단검"],
            4: ["마법의 빛 검", "신비로운 마력 검"],
            5: ["마법의 장검", "마력의 장검"],
            6: ["마력의 장검", "신비의 장검"],
            7: ["신비의 장검", "마법의 빛 장검"],
            8: ["마법의 빛 장검", "고대 마법 검"],
            9: ["고대 마법 검", "마법 군주의 검"],
            10: ["마법 군주의 검", "영원한 마력의 검"],
            11: ["전설의 마법의 검", "고대 마법 전설 검"],
            12: ["고대 마법 전설 검", "신비로운 마력의 검"],
            13: ["신비로운 마력의 검", "마법 군주의 전설 검"],
            14: ["마법 군주의 전설 검", "영원한 마력의 전설 검"],
            15: ["마법의 절대왕의 검", "마력을 지배하는 마법의 왕의 검", "고대 마법 절대왕의 검", "영원한 마력의 왕의 검", "마법 군주의 절대왕의 검"]
        }
    }
    
    if level in sword_names[attribute]:
        return random.choice(sword_names[attribute][level])
    else:
        return f"{attribute} 속성 {level}레벨 검"

# 검 이미지 URL 반환 (레벨별)
def get_sword_image_url(level, attribute=None):
    """
    레벨과 속성에 따른 검 이미지 URL 반환
    이미지 URL을 설정하려면 아래 SWORD_IMAGES 딕셔너리를 수정하세요.
    
    이미지 호스팅 방법:
    - Discord CDN (이미지 업로드 후 링크 복사)
    - Imgur, imgbb 등 이미지 호스팅 서비스
    - GitHub, GitLab 등 코드 저장소의 이미지
    """
    # ========== 여기에 이미지 URL을 설정하세요 ==========
    # 레벨별 이미지 URL (None이면 이미지 표시 안 함)
    SWORD_IMAGES = {
        0: None,   # 예: "https://example.com/sword_level_0.png"
        1: None,   # 예: "https://example.com/sword_level_1.png"
        2: None,
        3: None,
        4: None,
        5: None,
        6: None,
        7: None,
        8: None,
        9: None,
        10: None,
        11: None,
        12: None,
        13: None,
        14: None,
        15: None,  # 예: "https://example.com/sword_level_15_king.png"
    }
    
    # 또는 자동 생성 방식 (base_url 설정 시)
    base_url = None  # 예: "https://your-image-host.com/swords/"
    
    # ====================================================
    
    # base_url이 설정되어 있으면 자동 생성
    if base_url:
        if level == 15:
            return f"{base_url}sword_level_15_king.png"
        elif attribute and attribute in SWORD_ATTRIBUTES:
            return f"{base_url}sword_level_{level}_{attribute.lower()}.png"
        else:
            return f"{base_url}sword_level_{level}.png"
    
    # 딕셔너리에서 직접 가져오기
    return SWORD_IMAGES.get(level, None)

# 강화 성공 이미지 URL 반환
def get_enhancement_success_image_url():
    """
    강화 성공 시 표시할 이미지 URL 반환
    """
    # ========== 여기에 성공 이미지 URL을 설정하세요 ==========
    # 방법 1: base_url 사용 (GitHub 레포의 img 폴더 사용 시) - 추천
    # GitHub 저장소의 img 폴더에 이미지를 업로드한 후 아래 형식으로 설정
    # 형식: https://raw.githubusercontent.com/사용자명/저장소명/브랜치명/img/
    base_url = "https://raw.githubusercontent.com/kimgm1018/sangbot/main/img/"
    
    # 방법 2: 직접 URL 입력
    # 강화 성공 이미지 URL (None이면 이미지 표시 안 함)
    success_image = "enhancement_success.png"  # enhancement_success.png (오타 주의)
    
    # ====================================================
    
    # base_url이 설정되어 있으면 자동 생성
    if base_url:
        return f"{base_url}enhancement_success.png"
    
    # 직접 URL 반환
    return success_image if success_image else None

# 강화 실패 이미지 URL 반환
def get_enhancement_fail_image_url(fail_type="maintain"):
    """
    강화 실패 시 표시할 이미지 URL 반환
    fail_type: "maintain" (레벨 유지) 또는 "downgrade" (레벨 하락)
    """
    # ========== 여기에 실패 이미지 URL을 설정하세요 ==========
    # 방법 1: base_url 사용 (GitHub 레포의 img 폴더 사용 시) - 추천
    # GitHub 저장소의 img 폴더에 이미지를 업로드한 후 아래 형식으로 설정
    # 형식: https://raw.githubusercontent.com/사용자명/저장소명/브랜치명/img/
    base_url = "https://raw.githubusercontent.com/kimgm1018/sangbot/main/img/"
    
    # 방법 2: 직접 URL 입력
    # 강화 실패 이미지 URL (None이면 이미지 표시 안 함)
    FAIL_IMAGES = {
        "maintain" : "enhancement_fail_maintain.png",      # 레벨 유지 실패 이미지 URL
        "downgrade": "enhancement_fail_downgrade.png",     # 레벨 하락 실패 이미지 URL
    }
    
    # ====================================================
    
    # base_url이 설정되어 있으면 자동 생성
    if base_url:
        if fail_type == "maintain":
            return f"{base_url}enhancement_fail_maintain.png"
        else:  # downgrade
            return f"{base_url}enhancement_fail_downgrade.png"
    
    # 딕셔너리에서 직접 가져오기
    return FAIL_IMAGES.get(fail_type, None)

# 강화 비용 계산
def get_enhancement_cost(current_level):
    costs = {
        0: 10,        # 0->1: 10골드
        1: 40,        # 1->2: 40골드
        2: 80,        # 2->3: 80골드
        3: 200,       # 3->4: 200골드
        4: 500,       # 4->5: 500골드
        5: 1200,      # 5->6: 1,200골드
        6: 3000,      # 6->7: 3,000골드
        7: 5000,      # 7->8: 5,000골드
        8: 8000,      # 8->9: 8,000골드
        9: 12000,     # 9->10: 12,000골드
        10: 18000,    # 10->11: 18,000골드
        11: 25000,    # 11->12: 25,000골드
        12: 32000,    # 12->13: 32,000골드
        13: 40000,    # 13->14: 40,000골드
        14: 50000     # 14->15: 50,000골드
    }
    return costs.get(current_level, 0)

# 검 판매 가격 계산
def get_sword_price(level):
    prices = {
        0: 0,         # 0레벨: 0골드
        1: 40,        # 1레벨: 40골드
        2: 120,       # 2레벨: 120골드
        3: 300,       # 3레벨: 300골드
        4: 800,       # 4레벨: 800골드
        5: 2000,      # 5레벨: 2,000골드
        6: 5000,      # 6레벨: 5,000골드
        7: 7000,     # 7레벨: 12,000골드
        8: 12000,     # 8레벨: 28,000골드
        9: 20000,     # 9레벨: 60,000골드
        10: 35000,   # 10레벨: 120,000골드
        11: 50000,   # 11레벨: 160,000골드
        12: 75000,   # 12레벨: 200,000골드
        13: 150000,   # 13레벨: 230,000골드
        14: 400000,   # 14레벨: 260,000골드
        15: 600000    # 15레벨: 280,000골드
    }
    return prices.get(level, 0)

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
    """특정 서버의 왕(15레벨) 찾기"""
    server_data = load_sword_data(server_id)
    for uid, data in server_data.items():
        if data.get("sword_level", 0) == 15:
            return uid
    return None

# 하루 결투 횟수 초기화 (자정 체크)
def reset_daily_duel_count(server_id, uid):
    """특정 서버의 유저 결투 횟수 초기화"""
    today = datetime.now(KST).date()
    server_data = load_sword_data(server_id)
    user_data = server_data.get(uid, {})
    last_duel_date = user_data.get("last_duel_date")
    
    if last_duel_date != str(today):
        user_data["duel_count_today"] = 0
        user_data["last_duel_date"] = str(today)
        server_data[uid] = user_data
        save_sword_data(server_id, server_data)

# 검 시작 명령어
@bot.tree.command(name="검시작", description="검 키우기 게임을 시작합니다")
async def 검시작(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    server_id = interaction.guild.id
    
    server_data = load_sword_data(server_id)
    
    if uid in server_data:
        await interaction.response.send_message("❗ 이미 게임을 시작하셨습니다! `/검정보` 명령어로 현재 상태를 확인하세요.")
        return
    
    server_data[uid] = {
        "gold": 100000,
        "sword_level": 0,
        "sword_attribute": None,
        "duel_count_today": 0,
        "last_duel_date": str(datetime.now(KST).date())
    }
    save_sword_data(server_id, server_data)
    
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
    server_id = interaction.guild.id
    
    server_data = load_sword_data(server_id)
    
    if uid not in server_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = server_data[uid]
    level = user_data.get("sword_level", 0)
    attribute = user_data.get("sword_attribute", "없음")
    gold = user_data.get("gold", 0)
    
    # 검 이름 생성
    sword_name = get_sword_name(level, attribute if attribute != "없음" else None)
    
    embed = discord.Embed(
        title=f"⚔️ {interaction.user.display_name} 님의 검 정보",
        color=discord.Color.blue()
    )
    embed.add_field(name="⚔️ 검 이름", value=sword_name, inline=False)
    embed.add_field(name="💰 골드", value=f"{gold:,} 골드", inline=True)
    embed.add_field(name="⚔️ 검 레벨", value=f"{level} 레벨", inline=True)
    embed.add_field(name="✨ 속성", value=attribute if attribute != "없음" else "속성 없음", inline=True)
    
    # 현재 검 이미지 표시 (이미지 URL이 설정되어 있을 때만)
    sword_image = get_sword_image_url(level, attribute if attribute != "없음" else None)
    if sword_image:
        embed.set_image(url=sword_image)
    
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
    
    server_data = load_sword_data(server_id)
    
    if uid not in server_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = server_data[uid]
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
        
        # 현재 속성 가져오기 (0->1 강화 전)
        new_attribute = user_data.get("sword_attribute")
        
        # 강화 성공 시 성공 이미지 표시
        success_image = get_enhancement_success_image_url()
        if success_image:
            embed.set_image(url=success_image)
        else:
            # 성공 이미지가 없으면 새로운 레벨의 검 이미지 표시
            sword_image = get_sword_image_url(new_level, new_attribute)
            if sword_image:
                embed.set_image(url=sword_image)
        
        # 0->1 강화 시 속성 부여
        if current_level == 0 and new_level == 1:
            attribute = random.choice(SWORD_ATTRIBUTES)
            user_data["sword_attribute"] = attribute
            new_attribute = attribute  # 멘트를 위해 업데이트
        
        # 강화 멘트 추가
        enhancement_message = get_enhancement_message(current_level, new_level, new_attribute)
        embed.add_field(
            name="⚔️ 강화 성공!",
            value=enhancement_message,
            inline=False
        )
        
        # 15레벨 달성 시 왕의 검 체크
        if new_level == 15:
            king_uid = find_king(server_id)
            if king_uid and king_uid != uid:
                # 기존 왕과 자동 결투
                king_data = server_data[king_uid]
                # 맨션 사용 (자동으로 서버 닉네임으로 표시되면서 맨션 기능도 작동)
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
                
                server_data[king_uid] = king_data
            else:
                embed.add_field(
                    name="👑 왕의 검 획득!",
                    value="축하합니다! 당신이 이 서버의 왕이 되었습니다!",
                    inline=False
                )
        
        # 결투 후 최종 레벨과 속성 확인 (결투에서 패배하면 레벨이 변경될 수 있음)
        final_level = user_data.get("sword_level", new_level)
        final_attribute = user_data.get("sword_attribute", new_attribute)
        
        # 검 이름 생성 (최종 레벨)
        new_sword_name = get_sword_name(final_level, final_attribute)
        
        # 레벨 정보 추가 (멘트와 함께)
        if final_level != new_level:
            # 결투에서 패배해서 레벨이 변경된 경우
            embed.add_field(
                name="📊 레벨 변화",
                value=f"{current_level}레벨 → **{new_level}레벨** → **{final_level}레벨** (결투 패배)",
                inline=False
            )
        else:
            embed.add_field(
                name="📊 레벨 변화",
                value=f"{current_level}레벨 → **{final_level}레벨**",
                inline=False
            )
        embed.add_field(
            name="⚔️ 검 이름",
            value=new_sword_name,
            inline=False
        )
        embed.color = discord.Color.green()
    
    # 실패 (유지 가능)
    elif roll <= success_rate + maintain_rate:
        current_attribute = user_data.get("sword_attribute")
        current_sword_name = get_sword_name(current_level, current_attribute)
        
        embed.add_field(
            name="⚠️ 강화 실패 (레벨 유지)",
            value=f"{current_level}레벨 유지",
            inline=False
        )
        embed.add_field(
            name="⚔️ 검 이름",
            value=current_sword_name,
            inline=False
        )
        embed.color = discord.Color.orange()
        # 강화 실패 (레벨 유지) 이미지 표시
        fail_image = get_enhancement_fail_image_url("maintain")
        if fail_image:
            embed.set_image(url=fail_image)
        else:
            # 실패 이미지가 없으면 현재 레벨 이미지 유지
            sword_image = get_sword_image_url(current_level, current_attribute)
            if sword_image:
                embed.set_image(url=sword_image)
    
    # 실패 (레벨 하락)
    else:
        user_data["sword_level"] = 0
        user_data["sword_attribute"] = None
        failed_sword_name = get_sword_name(0, None)
        
        embed.add_field(
            name="❌ 강화 실패",
            value=f"{current_level}레벨 → **0레벨** (속성 초기화)",
            inline=False
        )
        embed.add_field(
            name="⚔️ 검 이름",
            value=failed_sword_name,
            inline=False
        )
        embed.color = discord.Color.red()
        # 강화 실패 (레벨 하락) 이미지 표시
        fail_image = get_enhancement_fail_image_url("downgrade")
        if fail_image:
            embed.set_image(url=fail_image)
        else:
            # 실패 이미지가 없으면 0레벨 이미지
            sword_image = get_sword_image_url(0)
            if sword_image:
                embed.set_image(url=sword_image)
    
    server_data[uid] = user_data
    save_sword_data(server_id, server_data)
    
    await interaction.response.send_message(embed=embed)

# 검 판매 명령어
@bot.tree.command(name="검판매", description="현재 검을 판매합니다")
async def 검판매(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    server_id = interaction.guild.id
    
    server_data = load_sword_data(server_id)
    
    if uid not in server_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    user_data = server_data[uid]
    level = user_data.get("sword_level", 0)
    
    if level == 0:
        await interaction.response.send_message("❗ 0레벨 검은 판매할 수 없습니다!")
        return
    
    price = get_sword_price(level)
    user_data["gold"] = user_data.get("gold", 0) + price
    user_data["sword_level"] = 0
    user_data["sword_attribute"] = None
    
    server_data[uid] = user_data
    save_sword_data(server_id, server_data)
    
    embed = discord.Embed(
        title="💰 검 판매 완료",
        description=f"{level}레벨 검을 {price:,} 골드에 판매했습니다!",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 현재 골드", value=f"{user_data['gold']:,} 골드", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 허수아비(가상의 상대) 생성 함수
def create_dummy_opponent(attacker_level):
    """
    공격자 레벨에 맞춰 랜덤한 허수아비 생성
    """
    # 허수아비 레벨: 공격자 레벨 ±3 범위 내에서 랜덤 (최소 1, 최대 15)
    min_level = max(1, attacker_level - 3)
    max_level = min(15, attacker_level + 3)
    dummy_level = random.randint(min_level, max_level)
    
    # 랜덤 속성
    dummy_attribute = random.choice(SWORD_ATTRIBUTES)
    
    # 허수아비 골드: 레벨에 비례하여 생성 (승리 시 획득 가능)
    dummy_gold = dummy_level * 5000  # 레벨당 5000골드
    
    return {
        "sword_level": dummy_level,
        "sword_attribute": dummy_attribute,
        "gold": dummy_gold,
        "name": "허수아비"
    }

# 결투 명령어
@bot.tree.command(name="결투", description="다른 유저와 결투합니다")
@app_commands.describe(상대="결투할 상대를 멘션하세요 (또는 '허수아비' 입력)")
async def 결투(interaction: discord.Interaction, 상대: str):
    attacker_uid = str(interaction.user.id)
    server_id = interaction.guild.id
    
    server_data = load_sword_data(server_id)
    
    if attacker_uid not in server_data:
        await interaction.response.send_message("❗ 게임을 시작하지 않았습니다! `/검시작` 명령어로 게임을 시작하세요.")
        return
    
    attacker_data = server_data[attacker_uid]
    attacker_level = attacker_data.get("sword_level", 0)
    
    if attacker_level == 0:
        await interaction.response.send_message("❗ 0레벨 검으로는 결투할 수 없습니다!")
        return
    
    # 허수아비 모드 체크
    is_dummy = False
    defender_data = None
    defender_name = ""
    defender_uid = None
    
    # "허수아비" 문자열 체크
    if 상대.lower() in ["허수아비", "허수아비 ", " 허수아비", "허수아비와", "허수아비와 결투"]:
        is_dummy = True
        defender_data = create_dummy_opponent(attacker_level)
        defender_name = "허수아비"
    else:
        # 멘션 파싱 시도
        try:
            # <@123456789> 형식에서 ID 추출
            import re
            mention_match = re.search(r'<@!?(\d+)>', 상대)
            if mention_match:
                defender_uid = mention_match.group(1)
                defender_member = await interaction.guild.fetch_member(int(defender_uid))
            else:
                # 숫자만 있는 경우
                if 상대.isdigit():
                    defender_uid = 상대
                    defender_member = await interaction.guild.fetch_member(int(defender_uid))
                else:
                    await interaction.response.send_message("❗ 올바른 상대를 멘션하거나 '허수아비'를 입력하세요.")
                    return
        except:
            await interaction.response.send_message("❗ 올바른 상대를 멘션하거나 '허수아비'를 입력하세요.")
            return
        
        if attacker_uid == defender_uid:
            await interaction.response.send_message("❗ 자신과는 결투할 수 없습니다!")
            return
        
        if defender_uid not in server_data:
            await interaction.response.send_message(f"❗ {defender_member.display_name} 님은 게임을 시작하지 않았습니다!")
            return
        
        defender_data = server_data[defender_uid]
        defender_name = defender_member.display_name
        
        # 하루 결투 횟수 체크 (허수아비는 제한 없음)
        reset_daily_duel_count(server_id, defender_uid)
        defender_data = server_data[defender_uid]
        
        if defender_data.get("duel_count_today", 0) >= 10:
            await interaction.response.send_message(f"❗ {defender_name} 님은 오늘 이미 10번의 결투를 받았습니다!")
            return
    
    defender_level = defender_data.get("sword_level", 0)
    
    if not is_dummy and defender_level == 0:
        await interaction.response.send_message(f"❗ {defender_name} 님의 검 레벨이 0입니다!")
        return
    
    # 결투 진행
    win_rate = calculate_duel_win_rate(attacker_level, defender_level)
    roll = random.random()
    
    # 검 이름 가져오기
    attacker_attribute = attacker_data.get("sword_attribute", "없음")
    defender_attribute = defender_data.get("sword_attribute", "없음")
    attacker_sword_name = get_sword_name(attacker_level, attacker_attribute if attacker_attribute != "없음" else None)
    defender_sword_name = get_sword_name(defender_level, defender_attribute if defender_attribute != "없음" else None)
    
    attacker_name = interaction.user.display_name
    
    embed = discord.Embed(
        title="⚔️ 결투 결과",
        color=discord.Color.purple()
    )
    
    # 허수아비 정보 표시
    if is_dummy:
        embed.add_field(
            name="🎯 허수아비와의 결투",
            value=f"레벨 {defender_level} | {defender_attribute} 속성 | {defender_data.get('gold', 0):,} 골드",
            inline=False
        )
    
    # 스토리 생성을 위한 정보 준비
    winner_name = ""
    stolen_gold = 0
    
    if roll < win_rate:
        # 공격자 승리
        winner_name = attacker_name
        
        if is_dummy:
            # 허수아비와의 결투: 골드 변동 없음
            embed.add_field(
                name="✅ 승리!",
                value=f"{attacker_name} 님이 허수아비를 물리쳤습니다!",
                inline=False
            )
            embed.add_field(
                name="💡 연습 결투",
                value="허수아비와의 결투에서는 골드를 획득하거나 잃지 않습니다.",
                inline=False
            )
            stolen_gold = 0  # 스토리용 (표시 안 함)
        else:
            # 실제 유저와의 결투: 골드 변동 있음
            stolen_gold = calculate_duel_gold(attacker_level, defender_level, defender_data.get("gold", 0))
            attacker_data["gold"] = attacker_data.get("gold", 0) + stolen_gold
            defender_data["gold"] = max(0, defender_data.get("gold", 0) - stolen_gold)
            
            embed.add_field(
                name="✅ 승리!",
                value=f"{attacker_name} 님이 승리했습니다!",
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
        winner_name = defender_name
        
        if is_dummy:
            # 허수아비와의 결투: 골드 변동 없음
            embed.add_field(
                name="❌ 패배...",
                value=f"{attacker_name} 님이 허수아비에게 패배했습니다!",
                inline=False
            )
            embed.add_field(
                name="💡 연습 결투",
                value="허수아비와의 결투에서는 골드를 획득하거나 잃지 않습니다.",
                inline=False
            )
            stolen_gold = 0  # 스토리용 (표시 안 함)
        else:
            # 실제 유저와의 결투: 골드 변동 있음
            stolen_gold = calculate_duel_gold(defender_level, attacker_level, attacker_data.get("gold", 0))
            attacker_data["gold"] = max(0, attacker_data.get("gold", 0) - stolen_gold)
            defender_data["gold"] = defender_data.get("gold", 0) + stolen_gold
            
            embed.add_field(
                name="❌ 패배...",
                value=f"{defender_name} 님이 승리했습니다!",
                inline=False
            )
            embed.add_field(
                name="💰 손실 골드",
                value=f"{stolen_gold:,} 골드를 잃었습니다...",
                inline=False
            )
        embed.color = discord.Color.red()
    
    # 허수아비가 아닌 경우에만 결투 횟수 증가 및 저장
    if not is_dummy:
        defender_data["duel_count_today"] = defender_data.get("duel_count_today", 0) + 1
        defender_data["last_duel_date"] = str(datetime.now(KST).date())
        server_data[defender_uid] = defender_data
    
    server_data[attacker_uid] = attacker_data
    save_sword_data(server_id, server_data)
    
    # 스토리 생성 (비동기)
    await interaction.response.defer()  # 응답 지연
    
    try:
        story_result = duel_story_chain.invoke({
            "attacker_name": attacker_name,
            "defender_name": defender_name,
            "attacker_level": attacker_level,
            "defender_level": defender_level,
            "attacker_attribute": attacker_attribute if attacker_attribute != "없음" else "속성 없음",
            "defender_attribute": defender_attribute if defender_attribute != "없음" else "속성 없음",
            "attacker_sword_name": attacker_sword_name,
            "defender_sword_name": defender_sword_name,
            "winner_name": winner_name,
            "stolen_gold": f"{stolen_gold:,}"
        })
        
        story_text = story_result.content if hasattr(story_result, 'content') else str(story_result)
        
        # 스토리가 너무 길면 자르기 (Discord embed 필드 제한: 1024자)
        if len(story_text) > 1024:
            story_text = story_text[:1021] + "..."
        
        embed.add_field(
            name="📖 결투 스토리",
            value=story_text,
            inline=False
        )
    except Exception as e:
        print(f"스토리 생성 오류: {e}")
        embed.add_field(
            name="📖 결투 스토리",
            value="스토리 생성 중 오류가 발생했습니다.",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

# 검 랭킹 명령어
@bot.tree.command(name="검랭킹", description="검 레벨 상위 10명을 확인합니다")
async def 검랭킹(interaction: discord.Interaction):
    server_id = interaction.guild.id
    
    # 서버별 데이터 로드
    server_data = load_sword_data(server_id)
    
    # 같은 서버의 유저만 필터링 (레벨 0 이상)
    server_users = {
        uid: data for uid, data in server_data.items()
        if data.get("sword_level", 0) > 0
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

