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
import asyncio
import numpy as np

from av.audio.frame import AudioFrame

def audioframe_to_s16le_bytes(frame: AudioFrame, target_channels=2):
    """
    Convert aiortc AudioFrame to interleaved s16le bytes at 48k stereo.
    """
    # Ensure 48k
    if frame.sample_rate != 48000:
        # aiortc typically gives 48k; if not, let av resample:
        frame.pts = None
        frame.sample_rate = 48000

    # Convert to s16
    pcm = frame.to_ndarray(format="s16")  # shape: (channels, samples)
    if pcm.ndim == 1:
        pcm = np.expand_dims(pcm, axis=0)

    # Upmix/downmix to target_channels
    ch = pcm.shape[0]
    if ch < target_channels:
        pcm = np.vstack([pcm] + [pcm[0:1, :]] * (target_channels - ch))
    elif ch > target_channels:
        pcm = pcm[:target_channels, :]

    # Interleave channels (C, N) -> (N, C) -> bytes
    interleaved = pcm.T.astype(np.int16).tobytes()
    return interleaved

class AlsaLoopbackSink:
    """
    Writes 48k s16le stereo PCM to ALSA loopback using ffmpeg.
    Target device: hw:Loopback,0,0 (provided by snd-aloop).
    """
    def __init__(self, device="hw:Loopback,0,0", sample_rate=48000, channels=2):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self._proc = None
        self._stdin = None
        self._task = None
        self._stopped = asyncio.Event()

    def start(self):
        # Build ffmpeg proc: raw s16le → ALSA device
        pass
        

    def write(self, pcm_bytes: bytes):
        
        # Calculate volume (RMS) of the PCM data
        if len(pcm_bytes) > 0:
            # Convert bytes back to int16 array for volume calculation
            pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
            # Calculate RMS (Root Mean Square) for volume
            rms = np.sqrt(np.mean(pcm_array.astype(np.float32) ** 2))
            # Normalize to 0-100 scale (int16 max is 32767)
            volume_percent = (rms / 32767.0) * 100
            print(f"PCM volume: {volume_percent:.2f}% (RMS: {rms:.1f})")
        else:
            print("Empty PCM data")
        
        print(f"PCM bytes length: {len(pcm_bytes)}")

    async def stop(self):
        pass

class WebpageStreamer(BotAdapter):
    def __init__(
        self,
        *,
        webpage_url,
    ):
        self.driver = None
        self.webpage_url = webpage_url
        self.video_frame_size = (1280, 720)
        self.display_var_for_debug_recording = None
        self.display = None

    def init_driver(self):

        self.display_var_for_debug_recording = os.environ.get("DISPLAY")
        if os.environ.get("DISPLAY") is None:
            # Create virtual display only if no real display is available
            self.display = Display(visible=0, size=(1280, 720))
            self.display.start()
            self.display_var_for_debug_recording = self.display.new_display_var

        options = webdriver.ChromeOptions()

        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument("--use-fake-device-for-media-stream")
        #options.add_argument("--use-fake-ui-for-media-stream")
        options.add_argument(f"--window-size={self.video_frame_size[0]},{self.video_frame_size[1]}")
        options.add_argument("--no-sandbox")
        options.add_argument("--start-fullscreen")
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

        with open("bots/webpage_streamer/webpage_streamer_payload.js", "r") as file:
            payload_code = file.read()

        combined_code = f"""
            {payload_code}
        """

        # Add the combined script to execute on new document
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": combined_code})

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
from aiortc.contrib.media import MediaPlayer, MediaRelay

PUMP_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Pumped Audio Player</title>
  <style>body{font-family:system-ui;margin:2rem} audio{width:100%}</style>
</head>
<body>
  <h1>Pumped Audio (listen-only)</h1>
  <p>This page subscribes to the upstream audio captured by the other client.</p>
  <button id="start">Start</button>
  <audio id="a" autoplay controls></audio>

<script>
const startBtn = document.getElementById('start');
const audioEl  = document.getElementById('a');

startBtn.onclick = async () => {
  startBtn.disabled = true;

  const pc = new RTCPeerConnection();

  // When server sends audio, play it.
  const ms = new MediaStream();
  pc.ontrack = (ev) => {
    ms.addTrack(ev.track);
    audioEl.srcObject = ms;
    try { audioEl.play(); } catch(e) { console.error(e); }
  };

  // We only want to RECEIVE audio
  pc.addTransceiver('audio', { direction: 'recvonly' });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const res = await fetch('http://localhost:8000/offer_pump_audio', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
  });

  if (!res.ok) {
    const t = await res.text();
    alert('No upstream audio yet (or error): ' + t);
    startBtn.disabled = false;
    return;
  }

  const answer = await res.json();
  await pc.setRemoteDescription(answer);
};
</script>
</body>
</html>
"""

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

  // 1) Ask for the user's microphone
  const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  // 2) Create the RTCPeerConnection
  const pc = new RTCPeerConnection();

  // 3) Receive the server's *video* (to preview) and optionally server audio
  const ms = new MediaStream();
  pc.ontrack = (ev) => {
    ms.addTrack(ev.track);
    videoEl.srcObject = ms;
  };

  // We still want to receive the server's video
  pc.addTransceiver('video', { direction: 'recvonly' });

  // ❗ Instead of recvonly audio, we now **send** our mic upstream:
  for (const track of micStream.getAudioTracks()) {
    pc.addTrack(track, micStream);
  }

  // Create/POST offer → set remote answer
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

# ADD THESE TWO LINES
AUDIO_RELAY = MediaRelay()
# will hold the *original* upstream AudioStreamTrack
# from the first client that posts to /offer
UPSTREAM_AUDIO_TRACK_KEY = "upstream_audio_track"

async def pump_page(_req):
    # GET /offer_pump_audio -> returns the listener page
    return web.Response(text=PUMP_HTML, content_type="text/html")


async def offer_pump_audio(req):
    """
    POST /offer_pump_audio
    Return an SDP answer that *sends* the upstream audio (if present)
    to this new peer connection (listen-only client).
    """
    params = await req.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    # Do we have an upstream audio yet?
    upstream = req.app.get(UPSTREAM_AUDIO_TRACK_KEY)
    if upstream is None:
        return web.Response(status=409, text="No upstream audio has been published yet.")

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Re-broadcast using the relay so multiple listeners are OK
    rebroadcast_track = AUDIO_RELAY.subscribe(upstream)
    pc.addTrack(rebroadcast_track)

    @pc.on("connectionstatechange")
    async def _on_state():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

async def offer(req):
    params = await req.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # --- server-to-client (unchanged): send your local video/audio if desired ---
    v_player = req.app["video_player"]
    a_player = req.app["audio_player"]

    if v_player and v_player.video:
        pc.addTrack(v_player.video)
    # You can still send server audio if you want the page to hear server audio too:
    if a_player and a_player.audio:
        pc.addTrack(a_player.audio)

    # --- NEW: receive client's mic and feed to ALSA loopback ---
    #loopback_sink = AlsaLoopbackSink(device="hw:Loopback,0,0", sample_rate=48000, channels=2)
    #loopback_sink.start()

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            # store the ORIGINAL upstream track for rebroadcast
            req.app[UPSTREAM_AUDIO_TRACK_KEY] = track
            logger.info("Upstream audio track set for rebroadcast.")

    @pc.on("connectionstatechange")
    async def _on_state():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)
            pass
            #await loopback_sink.stop()

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
    # Add CORS handling for preflight requests
    async def handle_cors_preflight(request):
        """Handle CORS preflight requests"""
        return web.Response(
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400',
            }
        )

    # Add CORS headers to all responses
    @web.middleware
    async def add_cors_headers(request, handler):
        """Add CORS headers to all responses"""
        response = await handler(request)
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        })
        return response

    app.middlewares.append(add_cors_headers)
    
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_options("/offer", handle_cors_preflight)

    app.router.add_get("/offer_pump_audio", pump_page)   # serves the HTML player
    app.router.add_post("/offer_pump_audio", offer_pump_audio)  # SDP exchange
    app.router.add_options("/offer_pump_audio", handle_cors_preflight)

    app["video_player"] = video_player
    app["audio_player"] = audio_player

    web.run_app(app, host="0.0.0.0", port=port)