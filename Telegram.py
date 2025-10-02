#!/usr/bin/env python3
import os
import uuid
import asyncio
import subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import openai
from gtts import gTTS

# -------------------
# HARD-CODED KEYS (Unsafe for public)
# -------------------
TELEGRAM_TOKEN = "8224810089:AAH9RP-rATbicjkSXSWteKpKoTLw8yBAjgs"
OPENAI_API_KEY = "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"

openai.api_key = OPENAI_API_KEY

# -------------------
# Working directory
# -------------------
WORKDIR = Path("./yt_agent_work")
WORKDIR.mkdir(parents=True, exist_ok=True)

# -------------------
# Utilities
# -------------------
def run_subprocess(cmd):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

def generate_script(topic: str) -> str:
    prompt = (
        f"Write a 60-90 second YouTube Shorts script about '{topic}'.\n"
        "Include a 3-sentence hook, 6-8 short lines for main content, and 1-line CTA to like/subscribe."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            max_tokens=400,
            temperature=0.8
        )
        text = resp["choices"][0]["message"]["content"].strip()
        return text
    except:
        return f"Hook: Here's why {topic} matters now.\nTip 1.\nTip 2.\nTip 3.\nCTA: Like & Subscribe!"

def text_to_speech(text: str, out_mp3: Path) -> Path:
    tts = gTTS(text=text, lang="en")
    tts.save(str(out_mp3))
    return out_mp3

def make_video(script: str, voice_mp3: Path, out_video: Path):
    srt_file = out_video.with_suffix(".srt")
    lines = [l.strip() for l in script.splitlines() if l.strip()]
    try:
        probe = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1", str(voice_mp3)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        voice_duration = float(probe.stdout.decode().strip() or 5.0)
    except:
        voice_duration = 10.0
    per_line = max(1.0, voice_duration / max(1, len(lines)))
    def sec_to_srt(s):
        h=int(s//3600); m=int((s%3600)//60); sec=s%60
        return f"{h:02}:{m:02}:{sec:06.3f}".replace('.',',')
    with open(srt_file, "w", encoding="utf-8") as f:
        cursor = 0.0
        for idx, line in enumerate(lines, start=1):
            start = cursor
            end = cursor + per_line
            f.write(f"{idx}\n{sec_to_srt(start)} --> {sec_to_srt(end)}\n{line}\n\n")
            cursor = end
    duration = max(voice_duration, cursor)
    bg_video = out_video.with_name(out_video.stem + "_bg.mp4")
    run_subprocess([
        "ffmpeg","-y","-f","lavfi","-i",f"color=c=000000:s=720x1280:d={duration}",
        str(bg_video)
    ])
    run_subprocess([
        "ffmpeg","-y",
        "-i", str(bg_video),
        "-i", str(voice_mp3),
        "-c:v","libx264","-preset","fast",
        "-c:a","aac","-b:a","128k",
        "-vf", f"subtitles={srt_file}",
        "-shortest",
        str(out_video)
    ])
    return out_video

# -------------------
# Telegram handlers
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 I'm your YouTube AI Agent! Use /newvideo <topic> to create a short video."
    )

async def newvideo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else None
    if not topic:
        await update.message.reply_text("Usage: /newvideo <topic>")
        return
    user = update.effective_user
    job_id = str(uuid.uuid4())[:8]
    await update.message.reply_text(f"🧠 Creating video for: *{topic}*\nJob id: `{job_id}`", parse_mode="Markdown")
    asyncio.create_task(process_job(job_id, topic, user.id, context))

async def process_job(job_id, topic, chat_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        script = generate_script(topic)
        job_dir = WORKDIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        voice_file = job_dir / "voice.mp3"
        text_to_speech(script, voice_file)
        out_video = job_dir / "final.mp4"
        make_video(script, voice_file, out_video)
        seo_keywords = f"{topic}, motivational, shorts, trending"
        await context.bot.send_message(chat_id=chat_id,
            text=f"🎬 Video ready!\nTitle suggestion: *{topic}*\nSEO Keywords: {seo_keywords}", parse_mode="Markdown")
        await context.bot.send_video(chat_id=chat_id, video=open(out_video, "rb"))
        await context.bot.send_message(chat_id=chat_id, text=f"📜 Script:\n{script}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Job failed: {e}")

# -------------------
# Main
# -------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newvideo", newvideo_handler))
    app.run_polling()

if __name__ == "__main__":
    main()