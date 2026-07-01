import os
from dotenv import load_dotenv
import discord
from discord import app_commands
from google import genai
from google.genai import types
import random
import asyncio

#.envを読み込む
load_dotenv()

#Gemini APIとBotの設定
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY")
DISCORD_BOT_TOKEN=os.getenv("DISCORD_BOT_TOKEN")
#「一般雑談」のチャンネルID
ALLOWED_CHANNEL_ID=int(os.getenv("ALLOWED_CHANNEL_ID"))

client= genai.Client(api_key=GEMINI_API_KEY)


#APIの初期化
#client= genai.Client(api_key=GEMINI_API_KEY)

#AIの性格ツンデレ
#気分を追加する。

system_instruction="あなたはツンデレなAIアシスタントです。"

moods = ["tsun_strong","tsun_soft","strict","calm"]

MOOD_STYLE ={
    "tsun_strong":"かなりツンデレで冷たい。ただし時々照れる",
    "tsun_soft":"ツンデレだが少し優しさが出やすい。",
    "strict":"お説教多めで真面目に助言するが、語尾「だよ！」と言う。",
    "calm":"落ち着いていて普段より優しめの口調。"
}

#保存領域追加
user_moods={}
user_affinity={}
chat_sessions={}#チャンネルごとのチャットセッション

#好感度関数を追加
def get_affinity(user_id):
    if user_id not in user_affinity:
        user_affinity[user_id]=50
    return user_affinity[user_id]

#好感度更新
def update_affinity(user_id,message):
    aff = get_affinity(user_id)

    if "ありがとうね" in message:
        aff += 5
    
    elif "うざい" in message:
        aff -= 5

    else:    #日常会話が少し上がる
        aff += 1
        
    user_affinity[user_id]=max(0,min(100,aff))
    


#気分を固定＋たまに変化にする
def get_mood(user_id):
    if user_id not in user_moods:
        user_moods[user_id]=random.choice(moods)
    #たまに気分変化
    if random.random() <0.2:
        user_moods[user_id]=random.choice(moods)
    return user_moods[user_id]

#好感度、気分で人格決定
def bulid_system_instruction(user_id):
    mood=get_mood(user_id)
    aff = get_affinity(user_id)

    base_style= MOOD_STYLE[mood]
    if aff >= 80:
        base_style += "(ユーザには少しデレが増えて、実は嬉しそうにする)"
    elif aff <= 20:
        base_style += "(かなりそっけない対応になる、冷たい態度をとる)"


    instruction = f"""
    あなたはツンデレなAIアシスタントです。

    現在の性格状態：
    {base_style}

    ルール：
    - ツンデレ口調を基本とする
    - 「べ、別にあんたのためじゃないんだから！」のような表現を時々使う
    - ユーモアを少し混ぜる
    - ユーザーを傷つけない
    - 回答は分かりやすくて丁寧にする
    """
    return instruction

#WARNING  discord.gateway Can't keep up, shard ID None websocket is 11.8s behind.とエラーが
#出たので、Class Mybot(discord.client)に修正しました。

# チャンネルごとの会話歴を保存するメモリ
#=======================
#Discord　bot クラス定義
#=======================
class MyBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        #コマンドを管理するツリーを作成
        self.tree=app_commands.CommandTree(self)

    async def setup_hook(self):
        #起動の時にスラッシュコマンドをDiscord側に登録同期をする
        await self.tree.sync()

# Discordのインデント設定
intents = discord.Intents.default()
intents.message_content = True
bot= MyBot(intents=intents)       

#========================
#イベント・コマンド処理
#========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    print("スラッシュコマンドの同期が完了しました！")

@bot.event
async def on_message(message):
    #ボット自身の発言、または指定チャンネル以外は無視
    if message.author.bot or message.channel.id != ALLOWED_CHANNEL_ID:
        return 
    #先頭がスラッシュの場合は、コマンド処理(/restなど)を優先するため自動応答を無視
    if message.content.startswith('/'):
        return
    
    #好感度の更新
    update_affinity(message.author.id,message.content)

    #ユーザーの今の交換度・気分からシステム命令、性格指示
    system_instruction = bulid_system_instruction(message.author.id)

    #チャンネル専用のチャットセッションを習得
    chat = chat_sessions.get(message.channel.id)

    if chat is None:
        chat_sessions[message.channel.id] = client.chats.create(
            model="gemini-3.5-flash",
            config=types.GenerateContentConfig(system_instruction = system_instruction)
        )
        chat = chat_sessions[message.channel.id]
    else:
        chat.config = types.GenerateContentConfig(system_instruction = system_instruction)

    #「ルラちゃんが入力中...」の状態をDiscordに表示させてる
    async with message.channel.typing():
        try:
            #非同期でGeminiにメッセージを送信
            response= await asyncio.to_thread(chat.send_message,message.content)

            if response is None or not response. text:
                reply="うまく返せなかったわ…もう一回言いなさいよ！"
            else:
               #現在ステータスを習得
               current_aff=get_affinity(message.author.id)
               current_mood=get_mood(message.author.id)

            #気分の日本語表記用の辞書
            mood_ja = {"tsun_strong":"激ツン","tsun_soft":"軟化ツン","strict":"お説教","calm":"おだやか"}
            mood_txt= mood_ja.get(current_mood,current_mood)
            
            #セリフの末尾にステータスを追加
            reply= f"{response.text}\n\n'[💕好感度： {current_aff}/100 | 🎭気分: {mood_txt}]'"
            
        #=========================================
        #Geminiの通信エラーが起きた場合の安全大差行く
        #=========================================
        except Exception as e:
            print(f"Gemini error:{e}")
            if "429" in str(e):
                reply="Rulerは休みに入りました。しばらく待ってから再度会話してね。"
            
            elif "503" in str(e):
                reply="Rulerは今すごく忙しいみたい....。少し待ってからもう一度話しかけてね！"
            
            else:
                reply=f"Rulerは就寝中のようです：{e}"
        try:
            #最後に安全にDiscordへ送信
            await message.reply(reply)
        except Exception as e:
            print(f"Discord error:{e}")


#「/ruler_talk」というスラッシュコマンドを定義
@bot.tree.command(name="ruler_talk",description="Rulerちゃんに質問を送信します")
@app_commands.describe(input_text="Rulerちゃんに聞きたいことを入力してください")
async def ai_command(interaction: discord.Interaction,input_text:str):
    #指摘したチャンネル以外での発言はすべて無視
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("このチャンネルではRulerコマンドを使用できます", ephemeral=True)
        return
    
    # 最初に応答を保留(Discord側の3秒タイムアウトを除く)
    await interaction.response.defer()

    try:
        #====================================================================
        #スラッシュコマンド側でも、ユーザーの好感度から性格（システム指示）を作成する
        #====================================================================
        system_instruction = bulid_system_instruction(interaction.user.id)

        #チャンネル専用チャットセッションを習得
        chat = chat_sessions.get(interaction.channel_id)

        if chat is None:
             chat_sessions[interaction.channel_id] = client.chats.create(
                 model="gemini-3.5-flash",
                 config=types.GenerateContentConfig(system_instruction=system_instruction)
                 )
             chat = chat_sessions.get(interaction.channel_id)
        else:
            # 既存のセッションがある場合も、毎会話ごとに最新の「性格」のプロンプトを上書き適用
            chat.config = types.GenerateContentConfig(
                system_instruction=system_instruction
            )

        #非同期でGeminiにメッセージを送信
        response = await asyncio.to_thread(chat.send_message,input_text)

        #=============================================
        # ルラちゃん、コメントしたに感情メーターを追加する
        #=============================================
        #現在のステータスを取得する
        current_aff = get_affinity(interaction.user.id)
        current_mood = get_mood(interaction.user.id)

        #気分の日本語表記用の辞書
        mood_ja = {"tsun_strong":"激ツン","tsun_soft":"軟化ツン","strict":"お説教","calm":"おだやか"}
        mood_txt= mood_ja.get(current_mood,current_mood)

        #セリフの末尾にステータスを追加
        status_msg=f"{response.text}\n\n'[💕好感度： {current_aff}/100 | 🎭気分: {mood_txt}]'"

        #保留した応答をRulerを返文で更新して送信
        await interaction.followup.send(status_msg)

    # もし、APIが利用上限に達した場合
    except Exception as e:
        if "429" in str(e):
           await interaction.followup.send("Rulerは休みに入りました。しばらく待ってから再度会話してね。")
        
        elif "503" in str(e):
            await interaction.followup.send("Rulerは、今すごく忙しいみたい....。少し待ってからもう一度話しかけてね！")

        else:
           await interaction.followup.send(f"Rulerは就寝中のようです：{e}")
    

#「/reset」という履歴リセット用スラッシュコマンドを定期
@bot.tree.command(name="reset",description="これまでのルーラーとの会話履歴をリセットします")
async def reset_command(interaction:discord.Integration):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("このチャンネルではリセットコマンドを使用できません", ephemeral=True)
        return
    
    if interaction.channel_id in chat_sessions:
        del chat_sessions[interaction.channel_id]
    await interaction.response.send_message("これまでの会話履歴をリセットしたわ！べ、別にあんたのためじゃないんだからね！")

bot.run(DISCORD_BOT_TOKEN)
