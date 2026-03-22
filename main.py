import os
import platform
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
AUDIO_INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
AUDIO_BACKEND = os.getenv("AUDIO_BACKEND")
AUDIO_GAIN = float(os.getenv("AUDIO_GAIN", "2.0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reaperbot")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents)


def build_ffmpeg_source() -> discord.AudioSource:
    if not AUDIO_INPUT_DEVICE:
        raise RuntimeError(
            "AUDIO_INPUT_DEVICE is not set in .env. "
            "Examples: Windows dshow device name, Pulse source name, or ALSA hw/plughw value."
        )

    backend = (AUDIO_BACKEND or "").strip().lower()
    if not backend:
        # Default per OS so one .env can work on both dev machine and Raspberry Pi.
        backend = "dshow" if platform.system().lower().startswith("win") else "pulse"

    if backend == "dshow":
        source = f"audio={AUDIO_INPUT_DEVICE}"
    else:
        source = AUDIO_INPUT_DEVICE

    pcm_source = discord.FFmpegPCMAudio(
        source=source,
        executable=FFMPEG_PATH,
        before_options=f"-f {backend} -thread_queue_size 4096",
        options="-vn -ac 2 -ar 48000",
    )
    # Gain boost helps when monitor sources are too quiet.
    return discord.PCMVolumeTransformer(pcm_source, volume=AUDIO_GAIN)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}")


@bot.command(name="hello")
async def hello(ctx: commands.Context) -> None:
    await ctx.send("Hello!")


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.send("Pong!")


@bot.command(name="status")
async def status(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    backend = (AUDIO_BACKEND or "").strip().lower()
    if not backend:
        backend = "dshow" if platform.system().lower().startswith("win") else "pulse"

    if not voice_client:
        await ctx.send(
            f"Not connected. backend={backend}, device={AUDIO_INPUT_DEVICE}, gain={AUDIO_GAIN}"
        )
        return

    await ctx.send(
        " | ".join(
            [
                f"channel={voice_client.channel}",
                f"connected={voice_client.is_connected()}",
                f"playing={voice_client.is_playing()}",
                f"paused={voice_client.is_paused()}",
                f"backend={backend}",
                f"device={AUDIO_INPUT_DEVICE}",
                f"gain={AUDIO_GAIN}",
            ]
        )
    )


@bot.command(name="join")
async def join(ctx: commands.Context) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Join a voice channel first, then run $join.")
        return

    channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if voice_client and voice_client.channel != channel:
        await voice_client.move_to(channel)
        await ctx.send(f"Moved to {channel.name}.")
        return

    if not voice_client:
        await channel.connect()
        await ctx.send(f"Connected to {channel.name}.")
        return

    await ctx.send(f"Already connected to {channel.name}.")


@bot.command(name="leave")
async def leave(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if not voice_client:
        await ctx.send("I am not in a voice channel.")
        return

    if voice_client.is_playing():
        voice_client.stop()

    await voice_client.disconnect()
    await ctx.send("Disconnected.")


@bot.command(name="stream")
async def stream(ctx: commands.Context, action: str = "start") -> None:
    voice_client = ctx.voice_client
    if not voice_client:
        await ctx.send("Run $join first so I know which voice channel to use.")
        return

    action = action.lower().strip()

    if action == "stop":
        if voice_client.is_playing():
            voice_client.stop()
            await ctx.send("Stopped audio stream.")
            return
        await ctx.send("No active stream.")
        return

    if action != "start":
        await ctx.send("Use $stream start or $stream stop.")
        return

    if voice_client.is_playing():
        await ctx.send("Already streaming.")
        return

    try:
        source = build_ffmpeg_source()
    except RuntimeError as exc:
        await ctx.send(str(exc))
        return

    def on_stream_end(error: Exception | None) -> None:
        if error:
            logger.error("Audio stream ended with error: %s", error)
            return
        logger.info("Audio stream ended.")

    voice_client.play(source, after=on_stream_end)
    await ctx.send("Started streaming audio input to Discord voice.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env")

bot.run(TOKEN)
