# ReaperBot

ReaperBot is a Discord voice relay bot for routing DAW audio into Discord voice channels with low setup friction.

It is designed for creators and teams who want to stream audio from REAPER/ReaStream pipelines into Discord for collaboration, live feedback, or remote production sessions.

## Features

- Voice channel controls: join, leave, start, stop
- Configurable audio backend: `pulse` or `alsa`
- Runtime gain control for quick loudness tuning
- Production-safe environment config via `.env`
- Built for Raspberry Pi 5 and Linux VM hosts

## Commands

- `$help` - Show command list
- `$join` - Connect bot to your current voice channel
- `$leave` - Disconnect from voice channel
- `$stream start` - Start relaying configured audio source
- `$stream stop` - Stop relaying audio source
- `$gain <0.1-5.0>` - Set output gain while running
- `$status` - Show current relay status
- `$ping` - Health and latency check

## Quick Start

1. Create and activate a virtual environment
2. Install dependencies
3. Configure `.env`
4. Start the bot

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Raspberry Pi 5 Setup

Install system packages:

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg pulseaudio-utils libopus0 libffi-dev
```

Create a dedicated Pulse null sink and monitor source:

```bash
pactl load-module module-null-sink sink_name=discord_sink sink_properties=device.description=DiscordSink
pactl list short sources
```

Set in `.env`:

```env
AUDIO_BACKEND=pulse
AUDIO_INPUT_DEVICE=discord_sink.monitor
```

Route REAPER output to `DiscordSink` and run `$stream start`.

## License

MIT
