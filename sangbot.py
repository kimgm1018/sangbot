# MTM4NzMzNzk3NjAwMjExNzY0Mg.Gx5TvA.VcqEmgxBEmvI4dn6x5L50ClqPh9JXas-qWSi8c

import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime
import requests
import math
import json
import os
from dotenv import load_dotenv

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
    xp_data[uid] = xp_data.get(uid, 0) + 10  # 메시지마다 10 XP
    
    save_data(xp_data)
    await bot.process_commands(message)

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



# 봇 준비되면 슬래시 명령어 서버에 등록
@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"✅ 등록된 명령어: {[cmd.name for cmd in synced]}")
    print(f"✅ 로그인: {bot.user}")

bot.run(token)

