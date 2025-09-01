import logging, os, subprocess, threading, shlex

logger = logging.getLogger(__name__)

def _ensure_writable_dir(path: str):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    if not os.access(d, os.W_OK):
        raise PermissionError(f"Directory not writable: {d}")

def _stream_subproc_output(prefix: str, proc: subprocess.Popen):
    def _reader():
        for line in iter(proc.stdout.readline, ''):
            logger.info("%s %s", prefix, line.rstrip())
    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    return t

class ScreenAndAudioRecorder:
    def __init__(self, file_location, recording_dimensions, audio_only):
        self.file_location = file_location
        self.ffmpeg_proc = None
        self.ffmpeg_thread = None
        self.screen_dimensions = (recording_dimensions[0] + 10, recording_dimensions[1] + 10)
        self.recording_dimensions = recording_dimensions
        self.audio_only = audio_only
        self.paused = False
        self.xterm_proc = None

    def start_recording(self, display_var):
        _ensure_writable_dir(self.file_location)

        logger.info("Starting recorder: display=%s screen=%sx%s out=%s",
                    display_var, *self.screen_dimensions, self.file_location)

        if self.audio_only:
            ffmpeg_cmd = [
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "verbose", "-y",
                "-thread_queue_size", "4096",
                "-f", "pulse", "-i", "default",
                "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "1",
                self.file_location,
            ]
        else:
            w, h = self.screen_dimensions
            rw, rh = self.recording_dimensions
            ffmpeg_cmd = [
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "verbose", "-y",
                "-thread_queue_size", "4096",
                "-framerate", "30", "-video_size", f"{w}x{h}",
                "-f", "x11grab", "-draw_mouse", "0", "-probesize", "32",
                "-i", str(display_var),
                "-thread_queue_size", "4096",
                "-f", "pulse", "-i", "default",
                "-vf", f"crop={rw}:{rh}:10:10",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "30",
                "-c:a", "aac", "-b:a", "128k",
                self.file_location,
            ]

        logger.info("ffmpeg: %s", shlex.join(ffmpeg_cmd))
        # Capture combined stdout+stderr so we can see errors in logs
        self.ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "TMPDIR": os.environ.get("TMPDIR", "/tmp")},
        )
        self.ffmpeg_thread = _stream_subproc_output("[ffmpeg]", self.ffmpeg_proc)

        # Fail fast if it died immediately (permissions, display, device issues)
        try:
            rc = self.ffmpeg_proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            return  # still running — good
        else:
            raise RuntimeError(f"ffmpeg exited immediately (rc={rc}); check logs above")

    def stop_recording(self):
        if not self.ffmpeg_proc:
            return
        self.ffmpeg_proc.terminate()
        self.ffmpeg_proc.wait()
        self.ffmpeg_proc = None
        logger.info("Stopped recorder; out=%s", self.file_location)
