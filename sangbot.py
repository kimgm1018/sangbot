# MTM4NzMzNzk3NjAwMjExNzY0Mg.Gx5TvA.VcqEmgxBEmvI4dn6x5L50ClqPh9JXas-qWSi8c

import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import datetime
from datetime import datetime, timedelta
import json
import requests
import math
import json
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

print("🔍 토큰 값:", repr(token))


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

# 롤 ck
@bot.tree.command(name = "ck", description="ck 뽑기")
@app_commands.describe(명단 = "Blue팀과 Red팀 참가인원을 순서대로 입력 *10명")
async def ck(interaction : discord.Interaction, 명단 : str):
    names = 명단.strip().split()
    a = names[:5]
    b = names[5:]
    random.shuffle(a)
    random.shuffle(b)
    await interaction.response.send_message(f"Red팀 TOP : {a.pop()} - Blue팀 TOP : {b.pop()} \nRed팀 JUNGLE : {a.pop()} - Blue팀 JUNGLE : {b.pop()} \nRed팀 MID : {a.pop()} - Blue팀 MID : {b.pop()} \nRed팀 AD : {a.pop()} - Blue팀 AD : {b.pop()} \nRed팀 SUPPORT : {a.pop()} - Blue팀 SUPPORT : {b.pop()} ")

# 경험치

XP_FILE = "xp_data.json"

# 사용자 데이터 로딩/저장 함수
def load_data():
    if os.path.exists(XP_FILE):
        with open(XP_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(XP_FILE, "w") as f:
        json.dump(data, f)

xp_data = load_data()

# ✅ 채팅 감지 → XP 누적

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    uid = str(message.author.id)
    before_xp = xp_data.get(uid, 0)
    xp_data[uid] = before_xp + 10
    save_data(xp_data)

    before_level = calculate_level(before_xp)
    current_level = calculate_level(xp_data[uid])

    # ✅ 레벨업 시 축하 메시지
    if current_level > before_level:
        channel = message.channel
        await channel.send(
            f"🎉 {message.author.mention} 님이 **레벨 {current_level}**로 레벨업 했습니다! 🥳"
        )

    await bot.process_commands(message)


# 레벨 계산 함수
def calculate_level(xp):
    return int(math.sqrt(xp // 20))

@bot.tree.command(name="레벨", description="현재 경험치와 레벨을 확인합니다")
async def 레벨(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    xp = xp_data.get(uid, 0)
    level = calculate_level(xp)
    next_level_xp = ((level + 1) ** 2) * 20

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
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1], reverse=True)[:10]

    embed = discord.Embed(title="🏆 경험치 랭킹 TOP 10", color=discord.Color.gold())
    for idx, (uid, xp) in enumerate(sorted_users, start=1):
        user = await bot.fetch_user(int(uid))
        level = calculate_level(xp)
        embed.add_field(name=f"{idx}. {user.display_name}", value=f"레벨 {level} | XP: {xp}", inline=False)

    await interaction.response.send_message(embed=embed)


# 렌덤 추첨

class RerollView(discord.ui.View):
    def __init__(self, names: list[str], k: int, allow_duplicate: bool):
        super().__init__(timeout=60)  # 60초 뒤 자동 비활성화
        self.names = names
        self.k = k
        self.allow_duplicate = allow_duplicate

    @discord.ui.button(label="🔁 다시 뽑기", style=discord.ButtonStyle.primary)
    @discord.ui.button(label="🔁 다시 뽑기", style=discord.ButtonStyle.primary)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        result_text = get_lottery_result(self.names, self.k, self.allow_duplicate)
        await interaction.response.edit_message(content=f"🎯 다시 추첨 결과:\n{result_text}", view=self)

def get_lottery_result(names: list[str], k: int, allow_duplicate: bool) -> str:
    if allow_duplicate:
        selected = [random.choice(names) for _ in range(k)]
        counter = {}
        for name in selected:
            counter[name] = counter.get(name, 0) + 1

        # 결과 정렬
        sorted_counter = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        result_lines = [f"{name} : {count}회" for name, count in sorted_counter]

        # 승자 판단
        top_count = sorted_counter[0][1]
        top_names = [name for name, count in sorted_counter if count == top_count]

        if len(top_names) == 1:
            result_lines.append(f"\n🎉 **당첨**: {top_names[0]} ({top_count}회)")
        else:
            tie_list = ", ".join(top_names)
            result_lines.append(f"\n⚖️ **무승부**: {tie_list} ({top_count}회씩)")

    else:
        selected = random.sample(names, k)
        result_lines = [f"{name}" for name in selected]

    return "\n".join(result_lines)

@bot.tree.command(name="복불복", description="N명 중 K명 추첨")
@app_commands.describe(명단="띄어쓰기로 구분된 이름들", 추첨="추첨할 인원 수", 추첨방법="1: 중복허용, 2: 중복비허용")
async def 복불복(interaction: discord.Interaction, 명단: str, 추첨: int, 추첨방법: str):
    names = 명단.strip().split()
    k = 추첨
    how = 추첨방법.strip()
    
    if not names or k < 1:
        await interaction.response.send_message("❗ 명단과 추첨 수를 올바르게 입력해주세요.", ephemeral=True)
        return
    if how not in ['1', '2', '중복허용', '중복비허용']:
        await interaction.response.send_message("❗ 추첨방법은 '1'(중복허용) 또는 '2'(중복비허용) 중 하나로 입력해주세요.", ephemeral=True)
        return
    if how in ['2', '중복비허용'] and k > len(names):
        await interaction.response.send_message("❗ 추첨 인원이 명단보다 많습니다 (중복 비허용).", ephemeral=True)
        return

    allow_duplicate = how in ['1', '중복허용']
    result_text = get_lottery_result(names, k, allow_duplicate)

    view = RerollView(names, k, allow_duplicate)
    await interaction.response.send_message(f"🎯 추첨 결과:\n{result_text}", view=view)

# 익명
@bot.tree.command(name="익명", description="익명으로 이 채널에 메시지를 보냅니다")
@app_commands.describe(내용="하고 싶은 말을 적어주세요")
async def 익명(interaction: discord.Interaction, 내용: str):
    channel = interaction.channel

    if len(내용.strip()) < 5:
        await interaction.response.send_message("❗ 메시지는 5자 이상이어야 합니다.", ephemeral=True)
        return

    # 익명 메시지 Embed 구성
    embed = discord.Embed(
        title="📢 익명 메시지",
        description=내용,
        color=discord.Color.dark_embed()
    )
    embed.set_footer(text="보낸 사람 정보는 저장되지 않습니다")

    # 메시지 전송
    await channel.send(embed=embed)

    # 사용자에게는 조용히 알림
    await interaction.response.send_message("✅ 익명 메시지가 전송되었습니다.", ephemeral=True)


# 이벤트 & 지각 관리
EVENT_FILE = "events.json"

# Load and save functions for events data
def load_events():
    if os.path.exists(EVENT_FILE):
        with open(EVENT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_events(data):
    with open(EVENT_FILE, "w") as f:
        json.dump(data, f, indent=4)

events = load_events()

# Schedule reminder check
@tasks.loop(minutes=1)
async def check_events():
    now = datetime.now()
    for time_str, data in events.items():
        event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")

        # 초기화가 안 되어 있으면 새로 설정
        if isinstance(data.get("notified"), bool) or "notified" not in data:
            data["notified"] = {"30": False, "10": False, "0": False}

        # 알림 대상 사용자
        mentions = ' '.join([f'<@{uid}>' for uid in data.get("participants", [])])
        channel = bot.get_channel(data["channel_id"])

        # 30분 전
        if not data["notified"]["30"] and now + timedelta(minutes=30) >= event_time:
            await channel.send(f"🔔 **[30분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
            data["notified"]["30"] = True

        # 10분 전
        if not data["notified"]["10"] and now + timedelta(minutes=10) >= event_time:
            await channel.send(f"⏰ **[10분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
            data["notified"]["10"] = True

        # 시작 시
        if not data["notified"]["0"] and now >= event_time:
            await channel.send(f"🚀 **[일정 시작]** `{data['title']}` 일정이 시작되었습니다!\n{mentions}")
            data["notified"]["0"] = True


# 일정추가
@bot.tree.command(name="일정추가", description="일정을 추가합니다")
@app_commands.describe(title="일정 제목", time="시작 시간 (YYYY-MM-DD HH:MM)", participants="참여자 멘션 공백구분")
async def 일정추가(interaction: discord.Interaction, title: str, time: str, participants: str):
    # 🔍 interaction 응답 가능 여부 확인
    if interaction.is_expired():
        print(f"⚠️ 인터랙션이 만료되어 응답할 수 없습니다: {interaction.id}")
        return

    # 🔧 시간 파싱
    try:
        dt = datetime.strptime(time, "%Y-%m-%d %H:%M")
    except ValueError:
        await interaction.response.send_message("❗ 시간 형식이 올바르지 않습니다. (예: 2025-07-01 15:00)", ephemeral=True)
        return

    # 🔧 참여자 파싱
    try:
        uids = [int(user_id.strip("<@!>")) for user_id in participants.split()]
    except Exception:
        await interaction.response.send_message("❗ 참여자 형식이 잘못되었습니다.", ephemeral=True)
        return

    # 📝 이벤트 저장
    events[time] = {
        "title": title,
        "participants": uids,
        "channel_id": interaction.channel_id,
        "notified": {"30": False, "10": False, "0": False},
        "attendance": {}
    }
    save_events(events)

    # ✅ 완료 메시지
    try:
        await interaction.response.send_message(f"✅ `{title}` 일정이 등록되었습니다.")
    except Exception as e:
        print(f"❌ 응답 실패: {e}")



# 일정 목록 확인
@bot.tree.command(name="일정목록", description="예정된 일정을 확인합니다")
async def 일정목록(interaction: discord.Interaction):
    await interaction.response.defer(thinking=False)  # 🔹 첫 줄에서 바로 호출

    if not events:
        await interaction.followup.send("📭 예정된 일정이 없습니다.")
        return

    embed = discord.Embed(title="📅 예정된 일정 목록", color=discord.Color.blue())
    for time_str, data in sorted(events.items()):
        users = ', '.join([f'<@{uid}>' for uid in data["participants"]])
        embed.add_field(name=f"{data['title']} ({time_str})", value=f"참여자: {users}", inline=False)

    await interaction.followup.send(embed=embed)

# 일정삭제
@bot.tree.command(name="일정삭제", description="일정을 삭제합니다")
@app_commands.describe(time="삭제할 일정의 시작 시간 (YYYY-MM-DD HH:MM)")
async def 일정삭제(interaction: discord.Interaction, time: str):
    await interaction.response.defer(thinking=False)

    if time not in events:
        await interaction.followup.send("❗ 해당 시간에 등록된 일정이 없습니다.", ephemeral=True)
        return

    del events[time]
    save_events(events)
    await interaction.followup.send(f"🗑 `{time}` 일정이 삭제되었습니다.")

# 출석 체크
@bot.tree.command(name="출석", description="출석을 체크합니다")
async def 출석(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for time_str, data in events.items():
        if uid in map(str, data["participants"]):
            if uid not in data["attendance"]:
                data["attendance"][uid] = now
                save_events(events)
                await interaction.response.send_message(f"✅ `{data['title']}` 출석 체크 완료! ({now})")
                return

    await interaction.response.send_message("❗ 출석할 일정이 없습니다.")

# 지각 통계
@bot.tree.command(name="지각통계", description="멤버별 지각 횟수 및 평균 지각 시간")
async def 지각통계(interaction: discord.Interaction):
    delay_stats = {}

    for time_str, data in events.items():
        start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        for uid in data.get("participants", []):
            uid = str(uid)
            attend_time = data.get("attendance", {}).get(uid)
            if attend_time:
                delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
                if delta > 0:
                    if uid not in delay_stats:
                        delay_stats[uid] = []
                    delay_stats[uid].append(delta)

    if not delay_stats:
        await interaction.response.send_message("📊 아직 지각 통계가 없습니다.")
        return

    embed = discord.Embed(title="⏱ 지각 통계", color=discord.Color.orange())
    for uid, delays in delay_stats.items():
        user = await bot.fetch_user(int(uid))
        avg_delay = sum(delays) / len(delays)
        embed.add_field(name=user.display_name, value=f"지각 횟수: {len(delays)}회\n평균 지각 시간: {avg_delay:.1f}분", inline=False)

    await interaction.response.send_message(embed=embed)

# 지각왕
@bot.tree.command(name="지각왕", description="지각왕을 보여줍니다")
async def 지각왕(interaction: discord.Interaction):
    delay_counts = {}
    total_delays = {}

    for time_str, data in events.items():
        start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        for uid in data.get("participants", []):
            uid = str(uid)
            attend_time = data.get("attendance", {}).get(uid)
            if attend_time:
                delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
                if delta > 0:
                    delay_counts[uid] = delay_counts.get(uid, 0) + 1
                    total_delays[uid] = total_delays.get(uid, 0) + delta

    if not delay_counts:
        await interaction.response.send_message("👑 현재 지각왕이 없습니다.")
        return

    top_uid = max(delay_counts, key=delay_counts.get)
    top_user = await bot.fetch_user(int(top_uid))

    embed = discord.Embed(title="👑 지각왕", color=discord.Color.red())
    embed.add_field(name="이름", value=top_user.display_name, inline=True)
    embed.add_field(name="지각 횟수", value=f"{delay_counts[top_uid]}회", inline=True)
    embed.add_field(name="누적 지각 시간", value=f"{total_delays[top_uid]:.1f}분", inline=True)

    await interaction.response.send_message(embed=embed)

    top_uid = max(delay_counts, key=delay_counts.get)
    top_user = await bot.fetch_user(int(top_uid))

    embed = discord.Embed(title="👑 지각왕", color=discord.Color.red())
    embed.add_field(name="이름", value=top_user.display_name, inline=True)
    embed.add_field(name="지각 횟수", value=f"{delay_counts[top_uid]}회", inline=True)
    embed.add_field(name="누적 지각 시간", value=f"{total_delays[top_uid]:.1f}분", inline=True)

    await interaction.response.send_message(embed=embed)

# 출석률
@bot.tree.command(name="출석률", description="사용자의 출석률을 확인합니다")
@app_commands.describe(대상="출석률을 확인할 대상 (멘션 또는 생략 시 본인)")
async def 출석률(interaction: discord.Interaction, 대상: discord.User = None):
    user = 대상 or interaction.user
    uid = str(user.id)

    참여수 = 0
    출석수 = 0

    for data in events.values():
        if int(uid) in data.get("participants", []):
            참여수 += 1
            if uid in data.get("attendance", {}):
                출석수 += 1

    embed = discord.Embed(
        title=f"📊 {user.display_name} 님의 출석률",
        color=discord.Color.green() if 참여수 else discord.Color.greyple()
    )

    if 참여수 == 0:
        embed.description = "참여한 일정이 없습니다."
    else:
        rate = (출석수 / 참여수) * 100
        embed.add_field(name="✅ 총 참여 일정 수", value=f"{참여수}회", inline=True)
        embed.add_field(name="📌 출석 완료", value=f"{출석수}회", inline=True)
        embed.add_field(name="📈 출석률", value=f"{rate:.1f}%", inline=True)

    await interaction.response.send_message(embed=embed)


# 봇 준비되면 슬래시 명령어 서버에 등록
@bot.event
async def on_ready():
    print(f"{bot.user} online")
    try:
        synced = await bot.tree.sync()
        print(f"✅ 등록된 명령어: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print("명령어 등록 실패:", e)
    check_events.start()

bot.run(token)

