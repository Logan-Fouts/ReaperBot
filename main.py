import logging
import os
import platform
from dataclasses import dataclass

import discord
from discord.ext import commands
from dotenv import load_dotenv


def _safe_float(value: str, fallback: float) -> float:
    try:
        return float(value)
    except ValueError:
        return fallback


@dataclass(frozen=True)
class BotConfig:
    token: str
    prefix: str
    ffmpeg_path: str
    audio_backend: str
    audio_input_device: str
    startup_gain: float


def load_config() -> BotConfig:
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in .env")

    backend = os.getenv("AUDIO_BACKEND", "").strip().lower()
    if not backend:
        backend = "dshow" if platform.system().lower().startswith("win") else "pulse"

    device = os.getenv("AUDIO_INPUT_DEVICE", "").strip()
    if not device:
        raise RuntimeError(
            "AUDIO_INPUT_DEVICE is not set in .env. "
            "Use a dshow/pulse/alsa source name for your platform."
        )

    return BotConfig(
        token=token,
        prefix=os.getenv("BOT_PREFIX", "$").strip() or "$",
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg",
        audio_backend=backend,
        audio_input_device=device,
        startup_gain=_safe_float(os.getenv("AUDIO_GAIN", "2.0"), 2.0),
    )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("reaperbot")

config = load_config()
current_gain = config.startup_gain

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=config.prefix, intents=intents, help_command=None)


def build_ffmpeg_source() -> discord.AudioSource:
    if config.audio_backend == "dshow":
        source = f"audio={config.audio_input_device}"
    else:
        source = config.audio_input_device

    pcm_source = discord.FFmpegPCMAudio(
        source=source,
        executable=config.ffmpeg_path,
        before_options=f"-f {config.audio_backend} -thread_queue_size 4096",
        options="-vn -ac 2 -ar 48000",
    )
    return discord.PCMVolumeTransformer(pcm_source, volume=current_gain)


async def ensure_voice_connection(ctx: commands.Context) -> discord.VoiceClient | None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(f"Join a voice channel first, then run {config.prefix}join.")
        return None

    channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if voice_client and voice_client.channel != channel:
        await voice_client.move_to(channel)
        await ctx.send(f"Moved to {channel.name}.")
        return voice_client

    if not voice_client:
        return await channel.connect()

    return voice_client


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")
    await bot.change_presence(activity=discord.Game(name=f"{config.prefix}help"))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument. Try {config.prefix}help")
        return

    logger.exception("Unhandled command error", exc_info=error)
    await ctx.send("Command failed. Check bot logs for details.")


@bot.command(name="help")
async def help_command(ctx: commands.Context) -> None:
    await ctx.send(
        "\n".join(
            [
                "ReaperBot commands:",
                f"{config.prefix}join - Connect to your voice channel",
                f"{config.prefix}leave - Disconnect",
                f"{config.prefix}stream start|stop - Start or stop relay",
                f"{config.prefix}gain <0.1-5.0> - Set output gain",
                f"{config.prefix}status - Show relay status",
                f"{config.prefix}ping - Health check",
            ]
        )
    )


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.send(f"Pong! latency={round(bot.latency * 1000)}ms")


@bot.command(name="status")
async def status(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client

    if not voice_client:
        await ctx.send(
            " | ".join(
                [
                    "connected=False",
                    f"backend={config.audio_backend}",
                    f"device={config.audio_input_device}",
                    f"gain={current_gain}",
                ]
            )
        )
        return

    await ctx.send(
        " | ".join(
            [
                f"channel={voice_client.channel}",
                f"connected={voice_client.is_connected()}",
                f"playing={voice_client.is_playing()}",
                f"paused={voice_client.is_paused()}",
                f"backend={config.audio_backend}",
                f"device={config.audio_input_device}",
                f"gain={current_gain}",
            ]
        )
    )


@bot.command(name="join")
async def join(ctx: commands.Context) -> None:
    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        return
    await ctx.send(f"Connected to {voice_client.channel.name}.")


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


@bot.command(name="gain")
async def gain(ctx: commands.Context, value: float) -> None:
    global current_gain

    if value < 0.1 or value > 5.0:
        await ctx.send("Gain must be between 0.1 and 5.0")
        return

    current_gain = value
    if ctx.voice_client and ctx.voice_client.is_playing():
        source = ctx.voice_client.source
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = current_gain

    await ctx.send(f"Gain set to {current_gain}")


@bot.command(name="stream")
async def stream(ctx: commands.Context, action: str = "start") -> None:
    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        return

    requested_action = action.lower().strip()

    if requested_action == "stop":
        if voice_client.is_playing():
            voice_client.stop()
            await ctx.send("Stopped audio stream.")
            return
        await ctx.send("No active stream.")
        return

    if requested_action != "start":
        await ctx.send(f"Use {config.prefix}stream start or {config.prefix}stream stop")
        return

    if voice_client.is_playing():
        await ctx.send("Already streaming.")
        return

    source = build_ffmpeg_source()

    def on_stream_end(error: Exception | None) -> None:
        if error:
            logger.error("Audio stream ended with error: %s", error)
            return
        logger.info("Audio stream ended cleanly.")

    voice_client.play(source, after=on_stream_end)
    await ctx.send("Started streaming audio input to Discord voice.")


def main() -> None:
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
