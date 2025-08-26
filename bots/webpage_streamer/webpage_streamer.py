import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver import ActionChains
from selenium import webdriver

from bots.bot_adapter import BotAdapter

logger = logging.getLogger(__name__)

from pyvirtualdisplay import Display

import time

import os

import subprocess

class WebpageStreamer(BotAdapter):
    def __init__(
        self,
        *,
        webpage_url,
    ):
        self.driver = None
        self.webpage_url = webpage_url
        self.video_frame_size = (1580, 1024)
        self.display_var_for_debug_recording = None
        self.display = None

    def init_driver(self):

        self.display_var_for_debug_recording = os.environ.get("DISPLAY")
        if os.environ.get("DISPLAY") is None:
            # Create virtual display only if no real display is available
            self.display = Display(visible=0, size=(1930, 1090))
            self.display.start()
            self.display_var_for_debug_recording = self.display.new_display_var

        options = webdriver.ChromeOptions()

        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument("--use-fake-device-for-media-stream")
        #options.add_argument("--use-fake-ui-for-media-stream")
        options.add_argument(f"--window-size={self.video_frame_size[0]},{self.video_frame_size[1]}")
        options.add_argument("--no-sandbox")
        #options.add_argument("--start-fullscreen")
        # options.add_argument('--headless=new')
        options.add_argument("--disable-gpu")
        #options.add_argument("--mute-audio")
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--enable-blink-features=WebCodecs,WebRTC-InsertableStreams,-AutomationControlled")
        options.add_argument("--remote-debugging-port=9222")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.media_stream_mic": 1,  # 1 = allow, 2 = block
        })

        self.driver = webdriver.Chrome(options=options)
        logger.info(f"web driver server initialized at port {self.driver.service.port}")

        # navigate to the webpage
        self.driver.get(self.webpage_url)

        # wait for the page to load
        self.driver.implicitly_wait(600)

        load_webapp(self.display_var_for_debug_recording)


#!/usr/bin/env python3
import argparse
from pathlib import Path

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Local WebRTC: Webcam + Mic</title>
  <style>body{font-family:system-ui;margin:2rem} video{width:100%;max-width:960px;background:#000;border-radius:12px}</style>
</head>
<body>
  <h1>Local WebRTC (webcam + microphone)</h1>
  <p>Click start to receive the live stream from this machine.</p>
  <button id="start">Start</button>
  <video id="v" playsinline controls></video>

<script>
const startBtn = document.getElementById('start');
const videoEl  = document.getElementById('v');

startBtn.onclick = async () => {
  startBtn.disabled = true;

  const pc = new RTCPeerConnection();
  const ms = new MediaStream();
  pc.ontrack = (ev) => {
    ms.addTrack(ev.track);       // merge audio + video into one stream
    videoEl.srcObject = ms;
  };

  // Offer to receive both
  pc.addTransceiver('video', { direction: 'recvonly' });
  pc.addTransceiver('audio', { direction: 'recvonly' });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const res = await fetch('/offer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
  });
  const answer = await res.json();
  await pc.setRemoteDescription(answer);

  videoEl.muted = false;
  videoEl.volume = 1.0;
  try { await videoEl.play(); } catch (e) { console.error(e); }
};
</script>
</body>
</html>
"""

async def index(_req):
    return web.Response(text=INDEX_HTML, content_type="text/html")

pcs = set()

async def offer(req):
    params = await req.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Attach webcam + mic (MediaPlayer uses FFmpeg devices under the hood)
    v_player = req.app["video_player"]
    a_player = req.app["audio_player"]

    if v_player and v_player.video:
        pc.addTrack(v_player.video)
    if a_player and a_player.audio:
        pc.addTrack(a_player.audio)

    @pc.on("connectionstatechange")
    async def _on_state():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

def load_webapp(display_var_for_debug_recording):

    video_size = "1280x720"
    framerate = "30"
    video_device = display_var_for_debug_recording
    video_format = "x11grab"

    audio_device = "default"
    audio_format = "alsa"

    port = 8000


    # Build players
    # Video options: set size + fps (many webcams accept these via v4l2)
    v_opts = {
        "video_size": video_size,
        "framerate": framerate,
    }
    video_player = MediaPlayer(video_device, format=video_format, options=v_opts)

    # Audio player: let aiortc/ffmpeg handle resampling to 48k
    audio_player = MediaPlayer(audio_device, format=audio_format)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app["video_player"] = video_player
    app["audio_player"] = audio_player

    web.run_app(app, host="0.0.0.0", port=port)