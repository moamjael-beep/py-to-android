"""Kivy YouTube Downloader — Android-optimized build.

Changes vs desktop version:
- Android storage path via primary_external_storage_path()
- REQUEST_INSTALL_PACKAGES / WRITE_EXTERNAL_STORAGE permission request at startup
- Window size removed (full-screen on Android)
- Folder chooser replaced with Android Downloads folder (no file picker needed)
- ffmpeg / imageio-ffmpeg removed (not available on Android); only progressive
  video and audio-only streams are offered
- subprocess / tempfile merge path removed
- Clipboard.paste() wrapped for Android quirks

Requirements (buildozer):
    requirements = python3,kivy==2.3.0,pytubefix,requests,certifi,urllib3
"""

import os
import re
import threading

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.graphics import Color, Rectangle

# Android-specific imports (only available on device)
try:
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False

try:
    from pytubefix import YouTube
    PYTUBE_OK = True
except ImportError:
    PYTUBE_OK = False

# ---------------------------------------------------------------------------
# Style palette
# ---------------------------------------------------------------------------
BG        = (0.09, 0.09, 0.12, 1)
PANEL     = (0.13, 0.14, 0.18, 1)
HEADER    = (0.14, 0.35, 0.62, 1)
PRIMARY   = (0.16, 0.48, 0.78, 1)
DANGER    = (0.62, 0.22, 0.22, 1)
SUCCESS   = (0.16, 0.55, 0.32, 1)
SELECTED  = (0.20, 0.55, 0.85, 1)
UNSELECTED= (0.22, 0.25, 0.30, 1)
FIELD     = (0.16, 0.17, 0.21, 1)
TEXT      = (0.95, 0.96, 0.98, 1)
MUTED     = (0.62, 0.66, 0.72, 1)

HINT_STATUS = "1. Paste link   2. Load   3. Pick quality   4. Download"


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------
def tinted(widget, rgba):
    with widget.canvas.before:
        Color(*rgba)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, _: setattr(rect, 'pos', w.pos),
                size=lambda w, _: setattr(rect, 'size', w.size))
    return widget


def flat_button(text, rgba, height=48, font_size=15, **kwargs):
    return Button(
        text=text, size_hint_y=None, height=height,
        background_normal='', background_down='',
        background_color=rgba, color=TEXT, font_size=font_size, **kwargs)


def styled_input(hint_text, **kwargs):
    return TextInput(
        multiline=False, hint_text=hint_text,
        background_normal='', background_color=FIELD,
        foreground_color=TEXT, hint_text_color=MUTED,
        cursor_color=PRIMARY, font_size=15, **kwargs)


def left_aligned(widget):
    widget.halign = 'left'
    widget.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0], None)))
    return widget


# ---------------------------------------------------------------------------
# Download folder
# ---------------------------------------------------------------------------
def get_download_path():
    """Return a writable downloads folder on Android or desktop."""
    if IS_ANDROID:
        try:
            base = primary_external_storage_path()
            path = os.path.join(base, 'Download', 'YTDownloader')
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            pass
    fallback = os.path.join(os.path.expanduser('~'), 'Downloads', 'YTDownloader')
    os.makedirs(fallback, exist_ok=True)
    return fallback


# ---------------------------------------------------------------------------
# Quality helpers
# ---------------------------------------------------------------------------
def parse_number(text):
    if not text:
        return 0
    m = re.match(r'(\d+)', str(text))
    return int(m.group(1)) if m else 0


def format_size(num_bytes):
    if not num_bytes:
        return "? MB"
    mb = num_bytes / (1024 * 1024)
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def safe_filename(name):
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip()
    return cleaned or 'video'


def pick_video_qualities(streams):
    """Progressive (video+audio) streams only — no ffmpeg needed."""
    best = {}
    for s in streams:
        if not s.resolution or not s.is_progressive:
            continue
        res = parse_number(s.resolution)
        cur = best.get(res)
        if cur is None or (
            (getattr(s, 'subtype', '') == 'mp4') > (getattr(cur, 'subtype', '') == 'mp4')
        ):
            best[res] = s
    return sorted(best.items())


def pick_audio_qualities(streams):
    best = {}
    for s in streams:
        if not getattr(s, 'abr', None):
            continue
        kbps = parse_number(s.abr)
        cur = best.get(kbps)
        if cur is None or (
            (getattr(s, 'subtype', '') == 'mp4') > (getattr(cur, 'subtype', '') == 'mp4')
        ):
            best[kbps] = s
    return sorted(best.items())


# ---------------------------------------------------------------------------
# YouTube client fallback
# ---------------------------------------------------------------------------
YOUTUBE_CLIENTS = ['ANDROID_VR', 'IOS', 'ANDROID', 'TV', 'MWEB', 'WEB', None]


def create_youtube(url, is_video):
    last_err = None
    for client in YOUTUBE_CLIENTS:
        try:
            yt = YouTube(url) if client is None else YouTube(url, client=client)
            streams = yt.streams
            if is_video:
                ok = any(s.resolution and s.is_progressive for s in streams)
            else:
                ok = any(getattr(s, 'abr', None) for s in streams)
            if not ok:
                raise RuntimeError(f"{client or 'default'}: no usable streams")
            return yt, (client or 'default')
        except Exception as e:
            last_err = e
    raise last_err


def friendly_error(e):
    text = str(e)
    if 'bot' in text.lower() or 'BotDetection' in type(e).__name__:
        return "YouTube blocked the request (bot detection).\nTry again later or use a different network."
    if 'SABR' in text or '403' in text:
        return "Stream blocked by YouTube.\nTry again or pick a different quality."
    if 'no usable' in text:
        return "No downloadable qualities found for this video.\nTry the Audio tab."
    return f"{type(e).__name__}: {text[:200]}"


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------
class YTDownloaderApp(App):

    def build(self):
        Window.clearcolor = BG

        # Request Android permissions at startup
        if IS_ANDROID:
            request_permissions([
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
            ])

        self.yt = None
        self.client_name = None
        self.selected_stream = None
        self._popup = None
        self._busy = False
        self.download_path = get_download_path()

        main = BoxLayout(orientation='vertical', padding=10, spacing=8)

        # -- header --
        header = tinted(
            BoxLayout(orientation='vertical', size_hint_y=None,
                      height=72, padding=[14, 10]), HEADER)
        header.add_widget(left_aligned(Label(
            text="[b]YouTube Downloader[/b]", markup=True,
            font_size=22, color=TEXT)))
        header.add_widget(left_aligned(Label(
            text="Paste link → Load → Pick quality → Download",
            font_size=12, color=(0.85, 0.9, 1, 1))))
        main.add_widget(header)

        # -- link row --
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        self.link_input = styled_input("Paste a YouTube URL here", size_hint_x=1)
        self.link_input.bind(on_text_validate=self.fetch_qualities)
        paste_btn = flat_button("Paste", PRIMARY, size_hint_x=None, width=90)
        paste_btn.bind(on_press=self.paste_from_clipboard)
        clear_btn = flat_button("✕", DANGER, size_hint_x=None, width=52)
        clear_btn.bind(on_press=self.clear_link)
        row.add_widget(self.link_input)
        row.add_widget(paste_btn)
        row.add_widget(clear_btn)
        main.add_widget(row)

        # -- mode toggle + load --
        mode_row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        self.video_btn = ToggleButton(
            text="🎬 Video", group="mode", state='down',
            background_normal='', background_down='',
            background_color=SELECTED, color=TEXT, font_size=15)
        self.audio_btn = ToggleButton(
            text="🎵 Audio", group="mode",
            background_normal='', background_down='',
            background_color=UNSELECTED, color=TEXT, font_size=15)
        self.video_btn.bind(state=self._on_mode_toggle)
        self.audio_btn.bind(state=self._on_mode_toggle)
        load_btn = flat_button("⬇ Load", PRIMARY)
        load_btn.bind(on_press=self.fetch_qualities)
        mode_row.add_widget(self.video_btn)
        mode_row.add_widget(self.audio_btn)
        mode_row.add_widget(load_btn)
        main.add_widget(mode_row)

        # -- status --
        self.status_label = left_aligned(Label(
            text=HINT_STATUS, color=MUTED, font_size=13,
            size_hint_y=None, height=52, valign='middle'))
        main.add_widget(self.status_label)

        # -- quality grid --
        self.quality_grid = GridLayout(
            cols=3, size_hint_y=None, spacing=6)
        self.quality_grid.bind(minimum_height=self.quality_grid.setter('height'))
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.quality_grid)
        main.add_widget(scroll)

        # -- save path display --
        path_row = BoxLayout(size_hint_y=None, height=36, spacing=6)
        path_row.add_widget(left_aligned(Label(
            text="Save to:", color=MUTED, font_size=12,
            size_hint_x=None, width=70)))
        self.path_label = left_aligned(Label(
            text=self.download_path, color=TEXT, font_size=11))
        path_row.add_widget(self.path_label)
        main.add_widget(path_row)

        # -- download button --
        dl_btn = flat_button("⬇  Download", SUCCESS, height=56, font_size=17)
        dl_btn.bind(on_press=self.download_file)
        main.add_widget(dl_btn)

        return main

    # -- helpers --
    def ui(self, fn):
        Clock.schedule_once(lambda dt: fn(), 0)

    def set_status(self, text):
        self.status_label.text = text
        self.status_label.color = TEXT

    def _set_busy(self, busy):
        self._busy = busy

    def _on_mode_toggle(self, btn, state):
        if state == 'down':
            btn.background_color = SELECTED
        else:
            btn.background_color = UNSELECTED
        if not self._busy and self.yt:
            self.refresh_quality_list()

    # -- paste / clear --
    def paste_from_clipboard(self, *a):
        if self._busy:
            return
        try:
            text = (Clipboard.paste() or '').strip()
        except Exception:
            text = ''
        if not text:
            self.show_message("Clipboard is empty — copy a YouTube link first")
            return
        self.link_input.text = text
        if 'youtu' in text:
            self.fetch_qualities()
        else:
            self.set_status("Pasted — check the link, then press Load")

    def clear_link(self, *a):
        if self._busy:
            return
        self.link_input.text = ''
        self.yt = None
        self.selected_stream = None
        self.quality_grid.clear_widgets()
        self.set_status(HINT_STATUS)
        self.dismiss_popup()

    # -- load qualities --
    def fetch_qualities(self, *a):
        if self._busy:
            return
        url = self.link_input.text.strip()
        if not url:
            self.show_message("Please paste a YouTube URL first")
            return
        self._set_busy(True)
        is_video = self.video_btn.state == 'down'
        self.set_status("Loading video info…")
        threading.Thread(
            target=self._load_worker, args=(url, is_video), daemon=True
        ).start()

    def _load_worker(self, url, is_video):
        try:
            yt, client = create_youtube(url, is_video)
            self.ui(lambda: self._apply_loaded(yt, client))
        except Exception as e:
            err = friendly_error(e)
            self.ui(lambda: self._load_failed(err))

    def _apply_loaded(self, yt, client):
        self.yt = yt
        self.client_name = client
        self.selected_stream = None
        self._set_busy(False)
        self.refresh_quality_list()
        self.status_label.text += f"  [client: {client}]"

    def _load_failed(self, err):
        self.yt = None
        self._set_busy(False)
        self.set_status("Could not load the video.")
        self.show_message(err)

    def refresh_quality_list(self, *a):
        if self._busy:
            return
        self.quality_grid.clear_widgets()
        self.selected_stream = None
        if self.yt is None:
            self.set_status(HINT_STATUS)
            return
        try:
            is_video = self.video_btn.state == 'down'
            if is_video:
                options = pick_video_qualities(self.yt.streams.filter(type='video'))
                if not options:
                    raise RuntimeError("No progressive video qualities found")
                q = " → ".join(str(s.resolution) for _, s in options)
                self.set_status(f"{self.yt.title}\nQualities: {q}")
            else:
                options = pick_audio_qualities(
                    self.yt.streams.filter(only_audio=True))
                if not options:
                    raise RuntimeError("No audio streams found")
                q = " → ".join(str(s.abr) for _, s in options)
                self.set_status(f"{self.yt.title}\nAudio: {q}")

            for _, stream in options:
                label = stream.resolution or stream.abr
                size = format_size(stream.filesize)
                btn = ToggleButton(
                    text=f"{label}\n{size}", group="quality",
                    size_hint_y=None, height=64, font_size=14,
                    background_normal='', background_down='',
                    background_color=UNSELECTED, color=TEXT)
                btn.bind(state=lambda inst, s:
                         setattr(inst, 'background_color',
                                 SELECTED if s == 'down' else UNSELECTED))
                btn.bind(on_press=lambda b, s=stream: self.select_quality(s))
                self.quality_grid.add_widget(btn)
        except Exception as e:
            self.yt = None
            self.set_status("Could not build quality list.")
            self.show_message(friendly_error(e))

    def select_quality(self, stream):
        self.selected_stream = stream
        label = stream.resolution or stream.abr
        self.set_status(f"Selected: {label} — press Download")

    # -- download --
    def download_file(self, *a):
        if self._busy:
            return
        if self.yt is None:
            self.show_message("Load a video first")
            return
        if self.selected_stream is None:
            self.show_message("Pick a quality from the list first")
            return
        self._set_busy(True)
        label = self.selected_stream.resolution or self.selected_stream.abr or 'file'
        self.set_status(f"Downloading {label}…")
        threading.Thread(
            target=self._download_worker,
            args=(self.selected_stream, self.download_path), daemon=True
        ).start()

    def _download_worker(self, stream, path):
        def on_progress(stream, chunk, bytes_remaining):
            try:
                total = getattr(stream, 'filesize', 0) or 0
                done = max(total - bytes_remaining, 0)
                pct = int(done / total * 100) if total else 0
                lbl = stream.resolution or getattr(stream, 'abr', '') or 'file'
                txt = f"Downloading {lbl}: {pct}% ({format_size(done)} / {format_size(total)})"
                self.ui(lambda t=txt: setattr(self.status_label, 'text', t))
            except Exception:
                pass

        try:
            self.yt.register_on_progress_callback(on_progress)
            filepath = stream.download(output_path=path)
            msg = f"✅ Done!\nSaved to:\n{filepath}"
            self.ui(lambda: self._download_done(msg))
        except Exception as e:
            err = friendly_error(e)
            self.ui(lambda: self._download_done(err, error=True))

    def _download_done(self, message, error=False):
        self._set_busy(False)
        self.set_status("Ready — pick another quality or load a new video." if not error
                        else "Download failed.")
        self.show_message(message)

    # -- popup --
    def show_message(self, message):
        self.dismiss_popup()
        popup = tinted(
            BoxLayout(orientation='vertical', padding=14, spacing=10,
                      size_hint=(0.92, None), height=200,
                      pos_hint={'center_x': 0.5, 'center_y': 0.5}),
            PANEL)
        popup.add_widget(left_aligned(
            Label(text=message, color=TEXT, valign='middle', font_size=14)))
        close_btn = flat_button("Close", PRIMARY, height=44)
        popup.add_widget(close_btn)
        self.root.add_widget(popup)
        self._popup = popup
        close_btn.bind(on_press=self.dismiss_popup)

    def dismiss_popup(self, *a):
        if getattr(self, '_popup', None) is not None:
            try:
                self.root.remove_widget(self._popup)
            except Exception:
                pass
            self._popup = None


if __name__ == '__main__':
    YTDownloaderApp().run()
