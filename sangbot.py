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
from pytz import timezone


KST = timezone("Asia/Seoul")
ATTENDANCE_FILE = "attendance_log.json"

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

print("🔍 토큰 값:", repr(token))


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
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
    now = datetime.now(KST)
    for time_str, data in events.items():
        event_time = KST.localize(datetime.strptime(time_str, "%Y-%m-%d %H:%M"))

        if isinstance(data.get("notified"), bool) or "notified" not in data:
            data["notified"] = {"30": False, "10": False, "0": False}

        mentions = ' '.join([f'<@{uid}>' for uid in data.get("participants", [])])
        channel = bot.get_channel(data["channel_id"])

        if not data["notified"]["30"] and now + timedelta(minutes=30) >= event_time:
            await channel.send(f"🔔 **[30분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
            data["notified"]["30"] = True

        if not data["notified"]["10"] and now + timedelta(minutes=10) >= event_time:
            await channel.send(f"⏰ **[10분 전 알림]** `{data['title']}` 일정이 곧 시작합니다!\n{mentions}")
            data["notified"]["10"] = True

        if not data["notified"]["0"] and now >= event_time:
            await channel.send(f"🚀 **[일정 시작]** `{data['title']}` 일정이 시작되었습니다!\n{mentions}")
            data["notified"]["0"] = True
        
            # 출석 현황 Embed 생성
            참여자 = list(map(str, data.get("participants", [])))
            출석자 = list(data.get("attendance", {}).keys())
            미출석자 = [uid for uid in 참여자 if uid not in 출석자]
        
            embed = discord.Embed(
                title=f"📋 `{data['title']}` 출석 현황",
                description=f"🕒 일정 시간: {time_str}",
                color=discord.Color.teal()
            )
        
            if 출석자:
                출석_멘션 = "\n".join([f"<@{uid}> ✅" for uid in 출석자])
                embed.add_field(name="출석자", value=출석_멘션, inline=False)
            else:
                embed.add_field(name="출석자", value="없음", inline=False)
        
            if 미출석자:
                미출석_멘션 = "\n".join([f"<@{uid}> ❌" for uid in 미출석자])
                embed.add_field(name="미출석자", value=미출석_멘션, inline=False)
            else:
                embed.add_field(name="미출석자", value="없음", inline=False)
        
            await channel.send(embed=embed)

# 지난 일정 삭제
@tasks.loop(minutes=60)
async def clean_old_events():
    now_kst = datetime.utcnow() + timedelta(hours=9)  # KST
    if now_kst.hour != 6:
        return

    ATTENDANCE_FILE = "attendance_log.json"

    to_delete = []
    logs = load_attendance_log()
    for time_str, data in list(events.items()):
        start_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        if start_time.date() < now_kst.date():
            if time_str not in logs:  # ✅ 중복 저장 방지
                save_attendance_log_entry(time_str, data)
            to_delete.append(time_str)

    for t in to_delete:
        del events[t]

    if to_delete:
        save_events(events)
        print(f"[자동 삭제] 다음 일정 삭제됨: {to_delete}")



# ✅ 일정 생성 (제목 + 시간만 모달로 받기)
class ScheduleCreateModal(discord.ui.Modal, title="일정 생성"):
    title_input = discord.ui.TextInput(label="일정 제목")
    time_input = discord.ui.TextInput(label="시작 시간 (YYYY-MM-DD HH:MM)")

    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_input.value
        time_str = self.time_input.value

        try:
            datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message("❗ 시간 형식 오류. 예: 2025-07-01 15:00", ephemeral=True)
            return

        if time_str in events:
            await interaction.response.send_message("❗ 해당 시간에 이미 일정이 존재합니다.", ephemeral=True)
            return

        events[time_str] = {
            "title": title,
            "participants": [],
            "channel_id": interaction.channel_id,
            "notified": {"30": False, "10": False, "0": False},
            "attendance": {}
        }
        save_events(events)
        await interaction.response.send_message(f"✅ `{title}` 일정이 생성되었습니다!", ephemeral=True)

@bot.tree.command(name="일정추가", description="일정 제목과 시간만 입력합니다 (참여자는 나중에 등록)")
async def 일정추가(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    await interaction.response.send_modal(ScheduleCreateModal())



# ✅ 일정 참여 (유저 드롭다운으로 추가)
class ParticipantSelect(discord.ui.Select):
    def __init__(self, time_str: str, interaction: discord.Interaction):  # ✅ interaction 추가
        self.time_str = time_str

        members = [
            member for member in interaction.guild.members
            if not member.bot
        ]

        if not members:
            options = []
        else:
            options = [
                discord.SelectOption(label=member.display_name, value=str(member.id))
                for member in members
            ][:25]

        super().__init__(
            placeholder="참여할 유저를 선택하세요",
            min_values=1,
            max_values=min(25, len(options)) if options else 1,  # 🔧 fallback to 1
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_ids = [int(uid) for uid in self.values]
        events[self.time_str]["participants"] = selected_ids
        save_events(events)
        await interaction.response.send_message("✅ 참여자가 성공적으로 등록되었습니다.", ephemeral=True)

class ParticipantSelectView(discord.ui.View):
    def __init__(self, time_str: str, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.add_item(ParticipantSelect(time_str, interaction))

@bot.tree.command(name="일정참여", description="기존 일정에 유저를 추가합니다.")
@app_commands.describe(시간="참여할 일정의 시작 시간 (YYYY-MM-DD HH:MM)")
async def 일정참여(interaction: discord.Interaction, 시간: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    if 시간 not in events:
        await interaction.response.send_message("❗ 해당 시간의 일정이 없습니다.", ephemeral=True)
        return

    view = ParticipantSelectView(시간, interaction)
    await interaction.response.send_message(f"💡 `{events[시간]['title']}` 일정에 참여할 유저를 선택하세요:", view=view, ephemeral=True)


# 일정 목록 확인
@bot.tree.command(name="일정목록", description="예정된 일정을 확인합니다")
async def 일정목록(interaction: discord.Interaction):
    try:
        print("[디버그] 일정목록 명령어 실행됨")

        # 1️⃣ 즉시 응답: 사용자에게 처리 중 메시지 표시
        await interaction.response.send_message("⏳ 일정을 불러오는 중입니다...", ephemeral=True)
        print("[디버그] 초기 응답 전송 완료")

        if not events:
            await interaction.followup.send("📭 예정된 일정이 없습니다.", ephemeral=True)
            print("[디버그] 등록된 일정 없음 - 안내 메시지 전송 완료")
            return

        embed = discord.Embed(title="📅 예정된 일정 목록", color=discord.Color.blue())
        for time_str, data in sorted(events.items()):
            users = ', '.join([f'<@{uid}>' for uid in data["participants"]])
            embed.add_field(name=f"{data['title']} ({time_str})", value=f"참여자: {users}", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
        print("[디버그] 일정 목록 전송 완료")

    except Exception as e:
        print("[에러] 일정목록 명령어 실패:", e)
        await interaction.followup.send("❗ 일정 목록을 불러오던 중 오류가 발생했습니다.", ephemeral=True)

# 일정삭제
@bot.tree.command(name="일정삭제", description="일정을 삭제합니다")
@app_commands.describe(time="삭제할 일정의 시작 시간 (YYYY-MM-DD HH:MM)")
async def 일정삭제(interaction: discord.Interaction, time: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=False)
    except Exception as e:
        print(f"[에러] 일정삭제 defer 실패: {e}")
        return

    if time not in events:
        await interaction.followup.send("❗ 해당 시간에 등록된 일정이 없습니다.", ephemeral=True)
        return

    save_attendance_log_entry(time, events[time])  # ✅ 출석 정보 저장
    del events[time]
    save_events(events)
    await interaction.followup.send(f"🗑 `{time}` 일정이 삭제되었습니다.")


# 일정전체삭제
@bot.tree.command(name="일정전체삭제", description="전체 일정을 삭제합니다 (되돌릴 수 없음)")
async def 일정전체삭제(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    await interaction.response.send_message(
        "⚠️ **정말로 모든 일정을 삭제하시겠습니까?**\n삭제를 원하면 `/일정삭제확인` 명령어를 실행해주세요.",
        ephemeral=True
    )


#전체삭제확인
@bot.tree.command(name="일정삭제확인", description="일정 전체 삭제를 확정합니다 (되돌릴 수 없음)")
async def 일정삭제확인(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    logs = load_attendance_log()
    for t, data in events.items():
        if t not in logs:
            save_attendance_log_entry(t, data)

    events.clear()
    save_events(events)
    await interaction.response.send_message("🗑 모든 일정이 성공적으로 삭제되었습니다.", ephemeral=True)


# 출석체크 파일
def load_attendance_log():
    if os.path.exists(ATTENDANCE_FILE):
        with open(ATTENDANCE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_attendance_log_entry(event_time: str, data: dict):
    logs = load_attendance_log()
    if event_time not in logs:  # ✅ 중복 저장 방지
        logs[event_time] = data
        with open(ATTENDANCE_FILE, "w") as f:
            json.dump(logs, f, indent=4)


# 출석 체크
@bot.tree.command(name="출석", description="출석을 체크합니다")
async def 출석(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    now = datetime.now(KST)  # ✅ 한국 시간 기준으로 now 설정

    # 출석 가능한 일정 목록 (30분 전 ~ 시작 시각 전)
    가능한_일정 = []

    for time_str, data in events.items():
        event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        event_time = KST.localize(event_time)  # ✅ 이벤트 시간도 한국 시간으로 간주

        if uid in map(str, data.get("participants", [])):
            if event_time - timedelta(minutes=30) <= now < event_time:
                가능한_일정.append((time_str, data))

    if not 가능한_일정:
        await interaction.response.send_message(
            "❗ 출석 가능한 일정이 없습니다.\n(30분 전부터 일정 시작 전까지만 출석할 수 있습니다.)",
            ephemeral=True
        )
        return

    # 여러 개 중 하나 선택
    options = [
        discord.SelectOption(label=f"{data['title']} ({time_str})", value=time_str)
        for time_str, data in 가능한_일정
    ]

    class AttendanceSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="출석할 일정을 선택하세요", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            selected_time = self.values[0]
            events[selected_time]["attendance"][uid] = now.strftime("%Y-%m-%d %H:%M")
            save_events(events)
            await interaction.response.send_message(
                f"✅ `{events[selected_time]['title']}` 출석 체크 완료!",
                ephemeral=True
            )

    view = discord.ui.View()
    view.add_item(AttendanceSelect())
    await interaction.response.send_message("📝 출석할 일정을 선택하세요:", view=view, ephemeral=True)




# 지각 통계
@bot.tree.command(name="지각통계", description="멤버별 지각 횟수 및 평균 지각 시간 (미출석도 지각으로 포함)")
async def 지각통계(interaction: discord.Interaction):
    delay_stats = {}

    # 🔹 현재 일정 + 삭제된 일정 포함
    all_data = list(events.items()) + list(load_attendance_log().items())

    for time_str, data in all_data:
        start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        for uid in data.get("participants", []):
            uid = str(uid)
            attend_time = data.get("attendance", {}).get(uid)

            if uid not in delay_stats:
                delay_stats[uid] = []

            if attend_time:
                delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
                if delta > 0:
                    delay_stats[uid].append(delta)
            else:
                delay_stats[uid].append(None)  # 출석 안 한 경우는 지각 처리 (시간 없음)

    if not delay_stats:
        await interaction.response.send_message("📊 아직 지각 통계가 없습니다.")
        return

    embed = discord.Embed(title="⏱ 지각 통계 (미출석 포함)", color=discord.Color.orange())
    for uid, delays in delay_stats.items():
        user = await bot.fetch_user(int(uid))
        total_count = len(delays)
        actual_delays = [d for d in delays if d is not None]

        if actual_delays:
            avg_delay = sum(actual_delays) / len(actual_delays)
            value = f"지각 횟수: {total_count}회\n평균 지각 시간: {avg_delay:.1f}분"
        else:
            value = f"지각 횟수: {total_count}회\n(모두 무단 결석)"

        embed.add_field(name=user.display_name, value=value, inline=False)

    await interaction.response.send_message(embed=embed)


# 지각왕
@bot.tree.command(name="지각통계", description="멤버별 지각 횟수 및 평균 지각 시간 (미출석도 지각으로 포함)")
async def 지각통계(interaction: discord.Interaction):
    delay_stats = {}

    # 🔹 현재 일정 + 삭제된 일정 포함
    all_data = list(events.items()) + list(load_attendance_log().items())

    for time_str, data in all_data:
        start = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        for uid in data.get("participants", []):
            uid = str(uid)
            attend_time = data.get("attendance", {}).get(uid)

            if uid not in delay_stats:
                delay_stats[uid] = []

            if attend_time:
                delta = (datetime.strptime(attend_time, "%Y-%m-%d %H:%M") - start).total_seconds() / 60
                if delta > 0:
                    delay_stats[uid].append(delta)
            else:
                delay_stats[uid].append(None)  # 출석 안 한 경우는 지각 처리 (시간 없음)

    if not delay_stats:
        await interaction.response.send_message("📊 아직 지각 통계가 없습니다.")
        return

    embed = discord.Embed(title="⏱ 지각 통계 (미출석 포함)", color=discord.Color.orange())
    for uid, delays in delay_stats.items():
        user = await bot.fetch_user(int(uid))
        total_count = len(delays)
        actual_delays = [d for d in delays if d is not None]

        if actual_delays:
            avg_delay = sum(actual_delays) / len(actual_delays)
            value = f"지각 횟수: {total_count}회\n평균 지각 시간: {avg_delay:.1f}분"
        else:
            value = f"지각 횟수: {total_count}회\n(모두 무단 결석)"

        embed.add_field(name=user.display_name, value=value, inline=False)

    await interaction.response.send_message(embed=embed)



# 출석률
@bot.tree.command(name="출석률", description="사용자의 출석률을 확인합니다 (삭제된 일정 포함)")
@app_commands.describe(대상="출석률을 확인할 대상 (멘션 또는 생략 시 본인)")
async def 출석률(interaction: discord.Interaction, 대상: discord.User = None):
    try:
        await interaction.response.defer(thinking=False)
    except Exception as e:
        print(f"[에러] 출석률 defer 실패: {e}")
        return

    user = 대상 or interaction.user
    uid = str(user.id)

    참여수 = 0
    출석수 = 0

    # 🔹 현재 남아있는 일정
    for data in events.values():
        if int(uid) in data.get("participants", []):
            참여수 += 1
            if uid in data.get("attendance", {}):
                출석수 += 1

    # 🔹 삭제된 일정 포함 (출석 로그)
    attendance_log = load_attendance_log()
    for data in attendance_log.values():
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

    await interaction.followup.send(embed=embed)

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
    clean_old_events.start()

bot.run(token)

