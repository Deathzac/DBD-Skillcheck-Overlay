import io
import ctypes
from ctypes import wintypes
import json
import math
import os
import random
import shutil
import struct
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import wave
import winsound
import keyboard

try:
    from PIL import Image, ImageFilter, ImageTk
    import PIL._tkinter_finder
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# --- DEFAULT CONFIGURATION ---
# PyInstaller/auto-py-to-exe: build as One File + Window Based (no console).
# Optional runtime asset folders can be bundled as icons;icons and sounds;sounds.
DEFAULT_SETTINGS = {
    "min_wait_seconds": 0,
    "max_wait_seconds": 800,
    "trigger_key": "=",
    "hit_key": "space",
    "master_volume": 100,
    "wheel_theme": "Classic Survivor",
    "chaos_mode_enabled": False,
    "entity_favor_enabled": True,
    "entity_favor_chance": 0.05,
    "coulrophobia_chance": 0.08,
    "merciless_storm_chance": 0.12,
    "madness_chance": 0.06,
    "huntress_lullaby_chance": 0.06,
    "unnerving_presence_chance": 0.08,
    "oppression_chance": 0.08,
    "miss_punish_enabled": True,
    "miss_punish_duration": 2.0,
    "miss_punish_escalating": True,
    "best_hit_streak": 0,
    "best_great_streak": 0,
    "lifetime_total": 0,
    "lifetime_great": 0,
    "lifetime_good": 0,
    "lifetime_misses": 0,
    "monitor_index": 0,
}

# --- WHEEL THEMES ---
WHEEL_THEMES = {
    "Classic Survivor": {
        "ring": "#eeeeee",
        "good": "#777777",
        "great": "#ffffff",
        "needle": "#ff2a2a",
        "accent": None,
        "accent_color": "#ffffff",
    },
    "Bloody Prestige": {
        "ring": "#c81d25",
        "good": "#6b141a",
        "great": "#ff6b6b",
        "needle": "#ffffff",
        "accent": "blood",
        "accent_color": "#9e1118",
    },
    "Auric Gold": {
        "ring": "#e6b84c",
        "good": "#8c6d23",
        "great": "#fff2b2",
        "needle": "#ff4d4d",
        "accent": "sparkles",
        "accent_color": "#ffd966",
    },
    "Entity Touched": {
        "ring": "#9d4edd",
        "good": "#4a2574",
        "great": "#e0aaff",
        "needle": "#ff7b00",
        "accent": "tendrils",
        "accent_color": "#7b2cbf",
    },
    "Blighted Serum": {
        "ring": "#ff8500",
        "good": "#7f3f00",
        "great": "#ffe169",
        "needle": "#ff2a2a",
        "accent": "serum",
        "accent_color": "#ff9e00",
    },
    "Frosty Eyes": {
        "ring": "#72efdd",
        "good": "#2b6e70",
        "great": "#e0fbfc",
        "needle": "#4ea8de",
        "accent": "frost",
        "accent_color": "#ade8f4",
    },
}

NEEDLE_SPEED = 320
GOOD_ZONE_SIZE = 38
GREAT_ZONE_SIZE = 10
TRANSPARENT_COLOR = "#010101"

NORMAL_WARNING_DELAY_MS = 450

COULROPHOBIA_SPEED_MULT = 1.50
MERCILESS_HITS_REQUIRED = 5
LULLABY_MAX_TOKENS = 5
LULLABY_DELAYS_MS = {
    1: 310,
    2: 190,
    3: 95,
    4: 35,
    5: 0,
}
UNNERVING_ZONE_SCALE = 0.55
OPPRESSION_SPEED_MULT = 1.15
OPPRESSION_ZONE_SIZE = 14

PERK_WARNING_DURATION = 0.75
ICON_STROKE_WIDTH = 3
ICON_STROKE_COLOR = (17, 17, 17)
PUNISH_KEYS = ["w", "a", "s", "d", "up", "down", "left", "right"]


def get_base_dir():
    """Return the folder containing the .py file or the built .exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """Find bundled PyInstaller data, while allowing optional beside-exe overrides."""
    # An external folder beside the executable takes priority so users can replace
    # icons/sounds without rebuilding. In a one-file build, bundled data lives in
    # PyInstaller's temporary _MEIPASS directory.
    external_path = os.path.join(get_base_dir(), relative_path)
    if os.path.exists(external_path):
        return external_path
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        bundled_path = os.path.join(bundle_dir, relative_path)
        if os.path.exists(bundled_path):
            return bundled_path
    return external_path


def get_settings_path():
    """Use a writable per-user location instead of PyInstaller's temp folder."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        settings_dir = os.path.join(appdata, "DBD Skill Check Overlay")
    else:
        settings_dir = os.path.join(os.path.expanduser("~"), ".dbd_skill_check_overlay")
    os.makedirs(settings_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, "dbd_overlay_settings.json")

    # Migrate settings from earlier script versions that stored the JSON beside
    # the .py/.exe. Do this only when the new per-user file does not exist.
    legacy_path = os.path.join(get_base_dir(), "dbd_overlay_settings.json")
    if not os.path.exists(settings_path) and os.path.isfile(legacy_path):
        try:
            shutil.copy2(legacy_path, settings_path)
        except OSError:
            # Reading the legacy file remains a fallback in load_settings().
            pass
    return settings_path


SOUNDS_DIR = resource_path("sounds")
ICONS_DIR = resource_path("icons")
SETTINGS_PATH = get_settings_path()


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings_source = SETTINGS_PATH
    if not os.path.isfile(settings_source):
        legacy_path = os.path.join(get_base_dir(), "dbd_overlay_settings.json")
        if os.path.isfile(legacy_path):
            settings_source = legacy_path
    if os.path.isfile(settings_source):
        try:
            with open(settings_source, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
        except Exception:
            pass
    if settings.get("wheel_theme") not in WHEEL_THEMES:
        settings["wheel_theme"] = "Classic Survivor"
    return settings


def save_settings(settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        # Settings are non-fatal: the overlay can still run with defaults.
        pass


def generate_beep_wav(freq, duration_ms, volume=0.4):
    sample_rate = 44100
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(num_samples):
            t = float(i) / sample_rate
            envelope = max(0.0, 1.0 - (i / num_samples))
            val = int(32767.0 * volume * envelope * math.sin(2.0 * math.pi * freq * t))
            wav_file.writeframes(struct.pack("<h", val))
    return buf.getvalue()


FALLBACK_SOUNDS = {
    "warning": generate_beep_wav(880, 180, 0.35),
    "great": generate_beep_wav(1320, 150, 0.4),
    "good": generate_beep_wav(660, 150, 0.35),
    "miss": generate_beep_wav(140, 350, 0.5),
}


def scale_wav_to_file(src_path, dst_path, scale):
    with wave.open(src_path, "rb") as w_in:
        params = w_in.getparams()
        frames = w_in.readframes(params.nframes)
    if params.sampwidth == 2:
        count = len(frames) // 2
        samples = struct.unpack(f"<{count}h", frames)
        scaled = [max(-32768, min(32767, int(s * scale))) for s in samples]
        out_frames = struct.pack(f"<{count}h", *scaled)
    elif params.sampwidth == 1:
        scaled = [max(0, min(255, int((b - 128) * scale + 128))) for b in frames]
        out_frames = bytes(scaled)
    else:
        raise ValueError("Unsupported sample width")
    with wave.open(dst_path, "wb") as w_out:
        w_out.setparams(params)
        w_out.writeframes(out_frames)


class SoundManager:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="dbd_overlay_sfx_")
        self.file_cache = {}
        self.mem_cache = {}
        self.volume_percent = 100

    def rebuild(self, volume_percent):
        self.volume_percent = max(0, min(100, int(volume_percent)))
        scale = self.volume_percent / 100.0
        self.file_cache.clear()
        self.mem_cache.clear()

        for name in ("warning", "great", "good", "miss"):
            custom_path = os.path.join(SOUNDS_DIR, f"{name}.wav")
            if os.path.isfile(custom_path):
                if self.volume_percent >= 100:
                    self.file_cache[name] = custom_path
                elif self.volume_percent > 0:
                    scaled_path = os.path.join(self.temp_dir, f"{name}_{self.volume_percent}.wav")
                    try:
                        scale_wav_to_file(custom_path, scaled_path, scale)
                        self.file_cache[name] = scaled_path
                    except Exception:
                        self.file_cache[name] = custom_path
            else:
                if self.volume_percent > 0:
                    freq, dur, base_vol = {
                        "warning": (880, 180, 0.35),
                        "great": (1320, 150, 0.40),
                        "good": (660, 150, 0.35),
                        "miss": (140, 350, 0.50),
                    }[name]
                    self.mem_cache[name] = generate_beep_wav(freq, dur, base_vol * scale)

    def play(self, sound_name):
        if self.volume_percent <= 0:
            return
        fpath = self.file_cache.get(sound_name)
        if fpath and os.path.isfile(fpath):
            winsound.PlaySound(fpath, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        wav_bytes = self.mem_cache.get(sound_name)
        if wav_bytes:
            threading.Thread(
                target=winsound.PlaySound,
                args=(wav_bytes, winsound.SND_MEMORY),
                daemon=True,
            ).start()

    def cleanup(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


def build_outlined_transparent_icon(path, target_size, stroke_width=ICON_STROKE_WIDTH):
    if not os.path.isfile(path):
        return None
    try:
        if HAS_PIL:
            pad = stroke_width + 2
            inner_size = max(16, target_size - pad * 2)
            src = Image.open(path).convert("RGBA")
            src = src.resize((inner_size, inner_size), Image.Resampling.LANCZOS)

            canvas_size = inner_size + pad * 2
            padded = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            padded.paste(src, (pad, pad))

            alpha = padded.split()[3]
            kernel_size = stroke_width * 2 + 1
            dilated_alpha = alpha.filter(ImageFilter.MaxFilter(kernel_size))
            dilated_alpha = dilated_alpha.point(lambda p: 255 if p > 80 else 0)

            outline_layer = Image.new(
                "RGBA",
                (canvas_size, canvas_size),
                (*ICON_STROKE_COLOR, 255),
            )
            outline_layer.putalpha(dilated_alpha)

            combined = Image.alpha_composite(outline_layer, padded)

            key_bg = Image.new("RGBA", (canvas_size, canvas_size), (1, 1, 1, 255))
            final_alpha = combined.split()[3].point(lambda p: 255 if p > 128 else 0)
            key_bg.paste(combined, (0, 0), final_alpha)

            return ImageTk.PhotoImage(key_bg.convert("RGB"))
        else:
            return tk.PhotoImage(file=path)
    except Exception:
        return None


def enumerate_monitors():
    """Return monitor rectangles in virtual-desktop coordinates (Windows)."""
    monitors = []
    if os.name != "nt":
        return [(0, 0, 0, 0, 0)]
    try:
        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_ssize_t)
        def collect(hmonitor, _hdc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                r = info.rcMonitor
                monitors.append((r.left, r.top, r.right, r.bottom, info.dwFlags))
            return True
        callback = callback_type(collect)
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback, 0)
    except Exception:
        monitors = []
    return monitors or [(0, 0, 0, 0, 0)]


class SkillCheckOverlay:

    def __init__(self):
        self.settings = load_settings()
        self.sfx = SoundManager()
        self.sfx.rebuild(self.settings["master_volume"])

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.root.config(bg=TRANSPARENT_COLOR)

        self.width = 360
        self.height = 290
        self.monitors = enumerate_monitors()
        self.monitor_index = max(0, min(int(self.settings.get("monitor_index", 0)), len(self.monitors) - 1))
        self.set_active_monitor(self.monitor_index, reposition=False)
        self.center_window()

        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack()

        perk_files = {
            "coulrophobia": "coulrophobia.png",
            "merciless_storm": "merciless_storm.png",
            "madness": "madness.png",
            "huntress_lullaby": "huntress_lullaby.png",
            "unnerving_presence": "unnerving_presence.png",
            "oppression": "oppression.png",
            "chaos": "chaos.png",
            "entity_favor": "entity_favor.png",
        }
        self.perk_icons_large = {
            k: build_outlined_transparent_icon(os.path.join(ICONS_DIR, fname), 82)
            for k, fname in perk_files.items()
        }
        self.perk_icons_side = {
            k: build_outlined_transparent_icon(os.path.join(ICONS_DIR, fname), 60)
            for k, fname in perk_files.items()
        }

        self.active = False
        self.pending = False
        self.angle = 0.0
        self.direction = 1
        self.target_start = 0.0
        self.last_time = 0.0
        self.warning_start_time = 0.0

        self.active_event = None
        self.entity_favor_active = False
        self.merciless_hits = 0
        self.passed_target = False
        self.lullaby_tokens = 0

        # Streak tracking
        self.hit_streak = 0
        self.great_streak = 0
        self.best_hit_streak = int(self.settings.get("best_hit_streak", 0))
        self.best_great_streak = int(self.settings.get("best_great_streak", 0))
        self.lifetime_total = int(self.settings.get("lifetime_total", 0))
        self.lifetime_great = int(self.settings.get("lifetime_great", 0))
        self.lifetime_good = int(self.settings.get("lifetime_good", 0))
        self.lifetime_misses = int(self.settings.get("lifetime_misses", 0))
        self.feedback_after_id = None

        self.blocked_keys = set()
        self.consecutive_misses = 0
        self.punish_win = None
        self.punish_after_id = None
        self.settings_win = None
        self.wake_event = threading.Event()

        self.root.withdraw()
        self.create_corner_controls()

        self.hit_hook = None
        self.trigger_hook = None
        self.rebind_hotkeys()

        threading.Thread(target=self.scheduler_loop, daemon=True).start()

    def rebind_hotkeys(self):
        if self.hit_hook is not None:
            try:
                keyboard.unhook(self.hit_hook)
            except Exception:
                pass
            self.hit_hook = None
        if self.trigger_hook is not None:
            try:
                keyboard.unhook(self.trigger_hook)
            except Exception:
                pass
            self.trigger_hook = None

        hit_key = str(self.settings.get("hit_key", "space")).strip() or "space"
        trig_key = str(self.settings.get("trigger_key", "=")).strip() or "="
        try:
            self.hit_hook = keyboard.on_press_key(hit_key, self.on_hit_key_pressed)
        except Exception:
            self.hit_hook = keyboard.on_press_key("space", self.on_hit_key_pressed)
        try:
            self.trigger_hook = keyboard.on_press_key(trig_key, self.on_manual_trigger)
        except Exception:
            self.trigger_hook = keyboard.on_press_key("=", self.on_manual_trigger)

    def set_active_monitor(self, index, reposition=True):
        self.monitor_index = max(0, min(int(index), len(self.monitors) - 1))
        left, top, right, bottom, _flags = self.monitors[self.monitor_index]
        self.monitor_left = left
        self.monitor_top = top
        self.screen_w = max(1, right - left) if right > left else self.root.winfo_screenwidth()
        self.screen_h = max(1, bottom - top) if bottom > top else self.root.winfo_screenheight()
        self.settings["monitor_index"] = self.monitor_index
        if reposition:
            self.center_window()
            if hasattr(self, "ctrl_win") and self.ctrl_win.winfo_exists():
                self.position_corner_controls()

    def position_corner_controls(self):
        pill_w, pill_h = 54, 22
        pos_x = self.monitor_left + self.screen_w - pill_w - 10
        pos_y = self.monitor_top + 10
        self.ctrl_win.geometry(f"{pill_w}x{pill_h}+{pos_x}+{pos_y}")

    def center_window(self):
        x = self.monitor_left + (self.screen_w - self.width) // 2
        y = self.monitor_top + (self.screen_h - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def randomize_window_position(self):
        margin_x = 120
        margin_y = 100
        max_x = max(margin_x + 1, self.screen_w - self.width - margin_x)
        max_y = max(margin_y + 1, self.screen_h - self.height - margin_y)
        x = self.monitor_left + random.randint(margin_x, max_x)
        y = self.monitor_top + random.randint(margin_y, max_y)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def create_corner_controls(self):
        self.ctrl_win = tk.Toplevel(self.root)
        self.ctrl_win.overrideredirect(True)
        self.ctrl_win.attributes("-topmost", True)
        self.ctrl_win.attributes("-alpha", 0.35)
        self.ctrl_win.config(bg="#111111")

        pill_w, pill_h = 54, 22
        self.position_corner_controls()

        frame = tk.Frame(self.ctrl_win, bg="#111111", bd=1, relief="solid")
        frame.pack(fill=tk.BOTH, expand=True)

        gear_btn = tk.Button(
            frame,
            text="⚙",
            command=self.open_settings_menu,
            bg="#1a1a1a",
            fg="#cccccc",
            activebackground="#333333",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            bd=0,
            cursor="hand2",
            width=2,
        )
        gear_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        close_btn = tk.Button(
            frame,
            text="✕",
            command=self.quit_app,
            bg="#1a1a1a",
            fg="#cccccc",
            activebackground="#cc2222",
            activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"),
            bd=0,
            cursor="hand2",
            width=2,
        )
        close_btn.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        def on_enter(_):
            self.ctrl_win.attributes("-alpha", 0.90)

        def on_leave(_):
            self.ctrl_win.attributes("-alpha", 0.35)

        self.ctrl_win.bind("<Enter>", on_enter)
        self.ctrl_win.bind("<Leave>", on_leave)

    def open_settings_menu(self):
        if self.settings_win is not None and tk.Toplevel.winfo_exists(self.settings_win):
            self.settings_win.lift()
            return

        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("DBD Skill Check Overlay — Settings")
        win.attributes("-topmost", True)
        win.configure(bg="#141414")
        win.resizable(False, False)

        w, h = 500, 680
        px = self.monitor_left + (self.screen_w - w) // 2
        py = self.monitor_top + (self.screen_h - h) // 2
        win.geometry(f"{w}x{h}+{px}+{py}")

        # Pinned bottom action bar
        bottom_bar = tk.Frame(win, bg="#1c1c1c", pady=10, padx=16)
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        status_lbl = tk.Label(
            win,
            text="",
            bg="#141414",
            fg="#70e000",
            font=("Segoe UI", 9, "bold"),
        )
        status_lbl.pack(side=tk.BOTTOM, pady=(2, 4))

        # Scrollable settings area; the action buttons and status remain pinned.
        scroll_frame = tk.Frame(win, bg="#141414")
        scroll_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        settings_canvas = tk.Canvas(
            scroll_frame, bg="#141414", highlightthickness=0, bd=0
        )
        settings_scrollbar = ttk.Scrollbar(
            scroll_frame, orient=tk.VERTICAL, command=settings_canvas.yview
        )
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)
        settings_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        settings_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        body = tk.Frame(settings_canvas, bg="#141414", padx=18, pady=10)
        body_window = settings_canvas.create_window(
            (0, 0), window=body, anchor="nw"
        )

        def update_settings_scroll_region(_event=None):
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))

        def fit_settings_body(event):
            settings_canvas.itemconfigure(body_window, width=event.width)

        body.bind("<Configure>", update_settings_scroll_region)
        settings_canvas.bind("<Configure>", fit_settings_body)

        def scroll_settings(event):
            # Windows wheel delta is normally +/-120; keep trackpad scrolling smooth.
            settings_canvas.yview_scroll(int(-event.delta / 120) if abs(event.delta) >= 120
                                         else (-1 if event.delta > 0 else 1), "units")

        def bind_settings_wheel(_event=None):
            win.bind_all("<MouseWheel>", scroll_settings)

        def unbind_settings_wheel(_event=None):
            win.unbind_all("<MouseWheel>")

        settings_canvas.bind("<Enter>", bind_settings_wheel)
        settings_canvas.bind("<Leave>", unbind_settings_wheel)
        body.bind("<Enter>", bind_settings_wheel)
        body.bind("<Leave>", unbind_settings_wheel)

        # Stats bar
        stats_frame = tk.Frame(body, bg="#1f1f1f", bd=1, relief="solid", padx=10, pady=6)
        stats_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            stats_frame,
            text=(f"Lifetime: {self.lifetime_total:,} checks  |  Great: {self.lifetime_great:,}  "
                  f"|  Good: {self.lifetime_good:,}  |  Misses: {self.lifetime_misses:,}\n"
                  f"Accuracy: {((self.lifetime_great + self.lifetime_good) / self.lifetime_total * 100):.1f}%" if self.lifetime_total else
                  "Lifetime: 0 checks  |  Great: 0  |  Good: 0  |  Misses: 0\nAccuracy: —"),
            bg="#1f1f1f",
            fg="#ffd166",
            font=("Segoe UI", 9, "bold"),
            justify="center",
        ).pack()
        tk.Label(stats_frame,
            text=f"Best Streak: {self.best_hit_streak}   |   Best Great Streak: {self.best_great_streak}",
            bg="#1f1f1f", fg="#bbbbbb", font=("Segoe UI", 8)).pack(pady=(3, 0))

        # --- Monitor selection ---
        monitor_row = tk.Frame(body, bg="#141414")
        monitor_row.pack(fill=tk.X, pady=(0, 7))
        tk.Label(monitor_row, text="Overlay Monitor:", bg="#141414", fg="#eeeeee",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        monitor_labels = [f"Monitor {i + 1}" + (" (Primary)" if m[4] & 1 else "")
                          for i, m in enumerate(self.monitors)]
        monitor_var = tk.StringVar(value=monitor_labels[self.monitor_index])
        monitor_combo = ttk.Combobox(monitor_row, textvariable=monitor_var,
                                     values=monitor_labels, state="readonly", width=22)
        monitor_combo.pack(side=tk.RIGHT)

        # --- Challenge modifiers ---
        tk.Label(
            body, text="CHALLENGE MODIFIERS", bg="#141414", fg="#ff6b6b",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 4))

        chaos_var = tk.BooleanVar(value=bool(self.settings.get("chaos_mode_enabled", False)))
        tk.Checkbutton(
            body,
            text="Enable Chaos Mode (Coulrophobia + Unnerving Presence + Madness)",
            variable=chaos_var, bg="#141414", fg="#eeeeee", selectcolor="#222222",
            activebackground="#141414", activeforeground="#ffffff",
            font=("Segoe UI", 8), wraplength=370, justify="left",
        ).pack(anchor="w", pady=(0, 3))

        favor_var = tk.BooleanVar(value=bool(self.settings.get("entity_favor_enabled", True)))
        tk.Checkbutton(
            body,
            text="Enable Entity's Favor (rare larger skill-check zone)",
            variable=favor_var, bg="#141414", fg="#eeeeee", selectcolor="#222222",
            activebackground="#141414", activeforeground="#ffffff",
            font=("Segoe UI", 8), wraplength=370, justify="left",
        ).pack(anchor="w", pady=(0, 1))

        favor_chance_row = tk.Frame(body, bg="#141414")
        favor_chance_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            favor_chance_row, text="Entity's Favor Chance (%):",
            bg="#141414", fg="#dddddd", font=("Segoe UI", 8),
        ).pack(side=tk.LEFT)
        favor_chance_var = tk.IntVar(
            value=int(round(float(self.settings.get("entity_favor_chance", 0.05)) * 100))
        )
        tk.Scale(
            favor_chance_row,
            from_=0, to=50, orient=tk.HORIZONTAL,
            variable=favor_chance_var,
            bg="#141414", fg="#ffffff", highlightthickness=0,
            troughcolor="#2a2a2a", length=155, showvalue=True,
            sliderlength=14, width=10,
        ).pack(side=tk.RIGHT)

        # --- Visuals & Theme ---
        tk.Label(
            body,
            text="VISUALS & WHEEL THEME",
            bg="#141414",
            fg="#e0aaff",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(2, 4))

        theme_row = tk.Frame(body, bg="#141414")
        theme_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            theme_row,
            text="Wheel Theme:",
            bg="#141414",
            fg="#eeeeee",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)

        theme_var = tk.StringVar(value=self.settings.get("wheel_theme", "Classic Survivor"))
        theme_combo = ttk.Combobox(
            theme_row,
            textvariable=theme_var,
            values=list(WHEEL_THEMES.keys()),
            state="readonly",
            width=22,
        )
        theme_combo.pack(side=tk.RIGHT)

        # --- Audio & Controls ---
        tk.Label(
            body,
            text="AUDIO & CONTROLS",
            bg="#141414",
            fg="#ff6b6b",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(2, 4))

        vol_row = tk.Frame(body, bg="#141414")
        vol_row.pack(fill=tk.X, pady=2)
        tk.Label(vol_row, text="Master Volume (%):", bg="#141414", fg="#eeeeee", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        vol_var = tk.IntVar(value=int(self.settings["master_volume"]))
        tk.Scale(
            vol_row,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=vol_var,
            bg="#141414",
            fg="#ffffff",
            highlightthickness=0,
            troughcolor="#2a2a2a",
            length=165,
        ).pack(side=tk.RIGHT)

        def preview_audio():
            self.sfx.rebuild(vol_var.get())
            self.sfx.play("great")

        tk.Button(
            body,
            text="Preview Sound",
            command=preview_audio,
            bg="#262626",
            fg="#ffffff",
            font=("Segoe UI", 8),
            bd=1,
            relief="solid",
            padx=8,
            pady=2,
            cursor="hand2",
        ).pack(anchor="e", pady=(0, 6))

        key_row = tk.Frame(body, bg="#141414")
        key_row.pack(fill=tk.X, pady=2)
        tk.Label(key_row, text="Hit Skill Check Key:", bg="#141414", fg="#eeeeee", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        hit_key_var = tk.StringVar(value=str(self.settings["hit_key"]))
        capturing = {"active": False}

        key_btn = tk.Button(
            key_row,
            text=hit_key_var.get().upper(),
            bg="#262626",
            fg="#ffd166",
            font=("Segoe UI", 9, "bold"),
            width=14,
            bd=1,
            relief="solid",
            cursor="hand2",
        )
        key_btn.pack(side=tk.RIGHT)

        def start_key_capture():
            if capturing["active"]:
                return
            capturing["active"] = True
            key_btn.config(text="Press any key...", fg="#ff6b6b")

            def on_cap(ev):
                if not capturing["active"]:
                    return
                capturing["active"] = False
                try:
                    keyboard.unhook(cap_hook)
                except Exception:
                    pass
                name = ev.name or "space"
                hit_key_var.set(name)
                win.after(0, lambda: key_btn.config(text=name.upper(), fg="#ffd166"))

            cap_hook = keyboard.on_press(on_cap)

        key_btn.config(command=start_key_capture)

        # --- Spawn Timing ---
        tk.Label(
            body,
            text="RANDOM SPAWN DELAY (SECONDS)",
            bg="#141414",
            fg="#70c5ff",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 4))

        wait_row = tk.Frame(body, bg="#141414")
        wait_row.pack(fill=tk.X, pady=2)
        tk.Label(wait_row, text="Min Wait (s):", bg="#141414", fg="#eeeeee", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        min_var = tk.StringVar(value=str(int(self.settings["min_wait_seconds"])))
        tk.Entry(wait_row, textvariable=min_var, width=8, bg="#222222", fg="#ffffff", insertbackground="#ffffff").pack(side=tk.LEFT, padx=(6, 18))

        tk.Label(wait_row, text="Max Wait (s):", bg="#141414", fg="#eeeeee", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        max_var = tk.StringVar(value=str(int(self.settings["max_wait_seconds"])))
        tk.Entry(wait_row, textvariable=max_var, width=8, bg="#222222", fg="#ffffff", insertbackground="#ffffff").pack(side=tk.LEFT, padx=6)

        # --- Perk Odds ---
        tk.Label(
            body,
            text="KILLER PERK ODDS (%)",
            bg="#141414",
            fg="#ffd166",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 2))

        perk_vars = {}
        perk_defs = [
            ("coulrophobia_chance", "Coulrophobia (Fast)"),
            ("merciless_storm_chance", "Merciless Storm (5x)"),
            ("madness_chance", "Doctor Madness (Spot)"),
            ("huntress_lullaby_chance", "Huntress Lullaby"),
            ("unnerving_presence_chance", "Unnerving Presence"),
            ("oppression_chance", "Oppression (Great Only)"),
        ]
        for key, label in perk_defs:
            row = tk.Frame(body, bg="#141414")
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, bg="#141414", fg="#dddddd", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            var = tk.IntVar(value=int(round(float(self.settings[key]) * 100)))
            perk_vars[key] = var
            tk.Scale(
                row,
                from_=0,
                to=50,
                orient=tk.HORIZONTAL,
                variable=var,
                bg="#141414",
                fg="#ffffff",
                highlightthickness=0,
                troughcolor="#2a2a2a",
                length=155,
                showvalue=True,
                sliderlength=14,
                width=10,
            ).pack(side=tk.RIGHT)

        punish_var = tk.BooleanVar(value=bool(self.settings["miss_punish_enabled"]))
        tk.Checkbutton(
            body,
            text="Enable Miss Punishment (red flash + movement-key freeze)",
            variable=punish_var,
            bg="#141414",
            fg="#eeeeee",
            selectcolor="#222222",
            activebackground="#141414",
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(6, 0))

        escalating_var = tk.BooleanVar(
            value=bool(self.settings.get("miss_punish_escalating", True))
        )
        tk.Checkbutton(
            body,
            text="Escalating miss punishment (2s → 3s → 5s; resets on success)",
            variable=escalating_var,
            bg="#141414",
            fg="#eeeeee",
            selectcolor="#222222",
            activebackground="#141414",
            activeforeground="#ffffff",
            font=("Segoe UI", 8),
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        def apply_changes():
            try:
                mn = max(0, int(float(min_var.get())))
                mx = max(mn + 1, int(float(max_var.get())))
            except ValueError:
                mn, mx = 0, 800

            self.settings["wheel_theme"] = theme_var.get()
            self.settings["chaos_mode_enabled"] = bool(chaos_var.get())
            self.settings["entity_favor_enabled"] = bool(favor_var.get())
            self.settings["entity_favor_chance"] = favor_chance_var.get() / 100.0
            selected_monitor = monitor_labels.index(monitor_var.get()) if monitor_var.get() in monitor_labels else self.monitor_index
            self.set_active_monitor(selected_monitor, reposition=True)
            if win.winfo_exists():
                win.geometry(f"{w}x{h}+{self.monitor_left + (self.screen_w - w) // 2}+{self.monitor_top + (self.screen_h - h) // 2}")
            self.settings["master_volume"] = int(vol_var.get())
            self.settings["hit_key"] = hit_key_var.get().strip() or "space"
            self.settings["min_wait_seconds"] = mn
            self.settings["max_wait_seconds"] = mx
            for k, v in perk_vars.items():
                self.settings[k] = round(v.get() / 100.0, 4)
            self.settings["miss_punish_enabled"] = bool(punish_var.get())
            self.settings["miss_punish_escalating"] = bool(escalating_var.get())

            save_settings(self.settings)
            self.sfx.rebuild(self.settings["master_volume"])
            self.rebind_hotkeys()
            self.wake_event.set()
            status_lbl.config(text="Settings applied & saved!", fg="#70e000")

        def reset_defaults():
            theme_var.set(DEFAULT_SETTINGS["wheel_theme"])
            chaos_var.set(DEFAULT_SETTINGS["chaos_mode_enabled"])
            favor_var.set(DEFAULT_SETTINGS["entity_favor_enabled"])
            favor_chance_var.set(int(round(DEFAULT_SETTINGS["entity_favor_chance"] * 100)))
            vol_var.set(DEFAULT_SETTINGS["master_volume"])
            hit_key_var.set(DEFAULT_SETTINGS["hit_key"])
            key_btn.config(text=DEFAULT_SETTINGS["hit_key"].upper())
            min_var.set(str(DEFAULT_SETTINGS["min_wait_seconds"]))
            max_var.set(str(DEFAULT_SETTINGS["max_wait_seconds"]))
            for k, v in perk_vars.items():
                v.set(int(round(DEFAULT_SETTINGS[k] * 100)))
            punish_var.set(DEFAULT_SETTINGS["miss_punish_enabled"])
            escalating_var.set(DEFAULT_SETTINGS["miss_punish_escalating"])
            apply_changes()
            status_lbl.config(text="Reset to defaults!", fg="#70c5ff")

        tk.Button(
            bottom_bar,
            text="Apply Settings",
            command=apply_changes,
            bg="#2b9348",
            fg="#ffffff",
            activebackground="#55a630",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Button(
            bottom_bar,
            text="Reset Defaults",
            command=reset_defaults,
            bg="#333333",
            fg="#eeeeee",
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=8)

        win.bind("<Destroy>", lambda event: unbind_settings_wheel() if event.widget is win else None)

        tk.Button(
            bottom_bar,
            text="Close",
            command=win.destroy,
            bg="#222222",
            fg="#cccccc",
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

    def clear_punishment(self):
        if self.punish_after_id is not None:
            try:
                self.root.after_cancel(self.punish_after_id)
            except Exception:
                pass
            self.punish_after_id = None

        for key in list(self.blocked_keys):
            try:
                keyboard.unblock_key(key)
            except Exception:
                pass
        self.blocked_keys.clear()

        if self.punish_win is not None:
            try:
                self.punish_win.destroy()
            except Exception:
                pass
            self.punish_win = None

    def trigger_miss_punishment(self):
        if not self.settings.get("miss_punish_enabled", True):
            return

        self.clear_punishment()
        if self.settings.get("miss_punish_escalating", True):
            # Escalate only for consecutive failed checks; successful checks reset this counter.
            duration = (2.0 if self.consecutive_misses <= 1 else
                        3.0 if self.consecutive_misses == 2 else 5.0)
        else:
            duration = float(self.settings.get("miss_punish_duration", 2.0))

        for key in PUNISH_KEYS:
            try:
                keyboard.block_key(key)
                self.blocked_keys.add(key)
            except Exception:
                pass

        self.punish_win = tk.Toplevel(self.root)
        self.punish_win.overrideredirect(True)
        self.punish_win.attributes("-topmost", True)
        self.punish_win.attributes("-alpha", 0.34)
        self.punish_win.config(bg="#cc0000")
        self.punish_win.geometry(f"{self.screen_w}x{self.screen_h}+{self.monitor_left}+{self.monitor_top}")

        start_time = time.perf_counter()

        def fade_punishment():
            if self.punish_win is None:
                return
            elapsed = time.perf_counter() - start_time
            if elapsed >= duration:
                self.clear_punishment()
                return
            remaining_ratio = max(0.0, 1.0 - (elapsed / duration))
            try:
                self.punish_win.attributes("-alpha", 0.34 * remaining_ratio)
            except Exception:
                pass
            self.punish_after_id = self.root.after(20, fade_punishment)

        self.punish_after_id = self.root.after(20, fade_punishment)

    def quit_app(self):
        self.clear_punishment()
        self.sfx.cleanup()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)

    def scheduler_loop(self):
        while True:
            self.wake_event.clear()
            mn = float(self.settings.get("min_wait_seconds", 0))
            mx = float(self.settings.get("max_wait_seconds", 800))
            wait_time = random.uniform(mn, max(mn + 0.5, mx))
            interrupted = self.wake_event.wait(timeout=wait_time)
            if interrupted:
                continue
            if not self.active and not self.pending:
                self.root.after(0, self.trigger_skill_check)

    def on_manual_trigger(self, event):
        if not self.active and not self.pending:
            self.root.after(0, self.trigger_skill_check)

    def trigger_skill_check(self):
        if self.active or self.pending:
            return
        if self.feedback_after_id is not None:
            try:
                self.root.after_cancel(self.feedback_after_id)
            except Exception:
                pass
            self.feedback_after_id = None

        self.pending = True

        self.entity_favor_active = (
            bool(self.settings.get("entity_favor_enabled", True))
            and random.random() < max(0.0, min(1.0, float(
                self.settings.get("entity_favor_chance", 0.05)
            )))
        )

        if bool(self.settings.get("chaos_mode_enabled", False)):
            # Chaos combines the three selected effects on every skill check.
            self.active_event = "chaos"
        elif self.lullaby_tokens > 0:
            self.active_event = "huntress_lullaby"
        else:
            c_coul = float(self.settings.get("coulrophobia_chance", 0.08))
            c_merc = float(self.settings.get("merciless_storm_chance", 0.12))
            c_mad = float(self.settings.get("madness_chance", 0.06))
            c_lull = float(self.settings.get("huntress_lullaby_chance", 0.06))
            c_unne = float(self.settings.get("unnerving_presence_chance", 0.08))
            c_oppr = float(self.settings.get("oppression_chance", 0.08))

            roll = random.random()
            acc = c_coul
            if roll < acc:
                self.active_event = "coulrophobia"
            elif roll < (acc := acc + c_merc):
                self.active_event = "merciless_storm"
            elif roll < (acc := acc + c_mad):
                self.active_event = "madness"
            elif roll < (acc := acc + c_lull):
                self.active_event = "huntress_lullaby"
                self.lullaby_tokens = 1
            elif roll < (acc := acc + c_unne):
                self.active_event = "unnerving_presence"
            elif roll < (acc := acc + c_oppr):
                self.active_event = "oppression"
            else:
                self.active_event = None

        if self.active_event in ("madness", "chaos"):
            self.randomize_window_position()
        else:
            self.center_window()

        if self.active_event == "huntress_lullaby":
            if self.lullaby_tokens < LULLABY_MAX_TOKENS:
                self.sfx.play("warning")

            if self.lullaby_tokens == 1:
                self.warning_start_time = time.perf_counter()
                self.root.attributes("-alpha", 0.0)
                self.draw_center_warning_icon()
                self.root.deiconify()
                self.animate_warning_fade()
            else:
                delay_ms = LULLABY_DELAYS_MS.get(self.lullaby_tokens, 0)
                if delay_ms <= 0:
                    self.start_wheel()
                else:
                    self.root.attributes("-alpha", 1.0)
                    self.root.after(delay_ms, self.start_wheel)
        elif self.active_event:
            self.sfx.play("warning")
            self.warning_start_time = time.perf_counter()
            self.root.attributes("-alpha", 0.0)
            self.draw_center_warning_icon()
            self.root.deiconify()
            self.animate_warning_fade()
        else:
            self.sfx.play("warning")
            self.root.attributes("-alpha", 1.0)
            self.root.after(NORMAL_WARNING_DELAY_MS, self.start_wheel)

    def draw_center_warning_icon(self):
        self.canvas.delete("all")
        cx, cy = self.width // 2, self.height // 2

        icon = self.perk_icons_large.get(self.active_event)
        if icon:
            self.canvas.create_image(cx, cy, image=icon)
        else:
            d_outer = 40
            pts_outer = [
                cx, cy - d_outer,
                cx + d_outer, cy,
                cx, cy + d_outer,
                cx - d_outer, cy,
            ]
            self.canvas.create_polygon(pts_outer, fill="#111111", outline="#000000", width=3)

            d = 35
            points = [cx, cy - d, cx + d, cy, cx, cy + d, cx - d, cy]
            self.canvas.create_polygon(points, fill="#4b1d6e", outline="#d4af37", width=2)
            short_labels = {
                "coulrophobia": "COUL",
                "merciless_storm": "STORM",
                "madness": "MAD",
                "huntress_lullaby": "LULL",
                "unnerving_presence": "UNNERV",
                "oppression": "OPPR",
                "chaos": "CHAOS",
            }
            self.draw_stroked_text(
                cx, cy, short_labels.get(self.active_event, "PERK"), ("Segoe UI", 9, "bold")
            )

    def animate_warning_fade(self):
        if not self.pending:
            return
        elapsed = time.perf_counter() - self.warning_start_time
        progress = min(1.0, elapsed / PERK_WARNING_DURATION)
        self.root.attributes("-alpha", progress)

        if progress >= 1.0:
            self.start_wheel()
        else:
            self.root.after(15, self.animate_warning_fade)

    def start_wheel(self):
        self.pending = False
        self.active = True
        self.root.attributes("-alpha", 1.0)
        self.angle = 0.0
        self.direction = 1
        self.merciless_hits = 0
        self.passed_target = False
        self.target_start = random.uniform(110, 290)
        self.last_time = time.perf_counter()
        self.root.deiconify()
        self.animate()

    def get_zone_sizes(self):
        # Entity's Favor is deliberately generous and overrides the smaller
        # Unnerving Presence zone for this one check, including during Chaos.
        if self.entity_favor_active:
            return (GOOD_ZONE_SIZE * 1.6, GREAT_ZONE_SIZE * 1.6)
        if self.active_event in ("unnerving_presence", "chaos"):
            return (
                GOOD_ZONE_SIZE * UNNERVING_ZONE_SCALE,
                GREAT_ZONE_SIZE * UNNERVING_ZONE_SCALE,
            )
        if self.active_event == "oppression":
            return (OPPRESSION_ZONE_SIZE, OPPRESSION_ZONE_SIZE)
        return (GOOD_ZONE_SIZE, GREAT_ZONE_SIZE)

    def spawn_next_merciless_target(self):
        offset = random.uniform(95, 210)
        self.target_start = (self.angle + self.direction * offset) % 360.0
        self.passed_target = False

    def is_angle_in_zone(self, angle, start, size):
        diff = (angle - start) % 360.0
        return 0.0 <= diff <= size

    def draw_stroked_text(self, x, y, text, font, fill="#ffffff", stroke="#111111"):
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
            self.canvas.create_text(x + dx, y + dy, text=text, fill=stroke, font=font)
        self.canvas.create_text(x, y, text=text, fill=fill, font=font)

    def animate(self):
        if not self.active:
            return

        now = time.perf_counter()
        dt = now - self.last_time
        self.last_time = now

        speed = NEEDLE_SPEED
        if self.active_event in ("coulrophobia", "chaos"):
            speed *= COULROPHOBIA_SPEED_MULT
        elif self.active_event == "oppression":
            speed *= OPPRESSION_SPEED_MULT

        self.angle = (self.angle + self.direction * speed * dt) % 360.0
        good_size, _ = self.get_zone_sizes()

        if self.active_event == "merciless_storm":
            in_zone = self.is_angle_in_zone(self.angle, self.target_start, good_size)
            if in_zone:
                self.passed_target = True
            elif self.passed_target:
                self.resolve_check("MISS")
                return
        else:
            if self.angle < (speed * dt):
                self.resolve_check("MISS")
                return

        self.draw_wheel()
        self.root.after(10, self.animate)

    def draw_theme_accents(self, cx, cy, r, theme):
        """Draw theme-specific ornament around the wheel without affecting hit logic."""
        accent = theme.get("accent")
        color = theme.get("accent_color", "#ffffff")

        # Fine radial graduations give the wheel a machined, game-HUD finish.
        for deg in range(0, 360, 10):
            a = math.radians(deg - 90)
            major = (deg % 30 == 0)
            r1 = r + (8 if major else 10)
            r2 = r + (15 if major else 13)
            x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
            x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
            self.canvas.create_line(x1, y1, x2, y2,
                                    fill=color if major else "#777777",
                                    width=2 if major else 1)

        if not accent:
            return

        if accent == "blood":
            # Splatter flecks and hanging drops, deliberately asymmetric.
            drops = [(-103,-43,4),(-111,-25,2),(103,33,5),(109,48,2),
                     (-48,105,3),(57,-105,3),(-94,70,2),(88,-75,2)]
            for dx, dy, size in drops:
                x, y = cx + dx, cy + dy
                self.canvas.create_oval(x-size-2,y-size-2,x+size+2,y+size+2,
                                        fill="#170609", outline="")
                self.canvas.create_oval(x-size,y-size,x+size,y+size,
                                        fill=color, outline="#4b080d", width=1)
            for dx, dy in [(-100,-65),(99,65),(-68,98)]:
                self.canvas.create_line(cx+dx,cy+dy,cx+dx+2,cy+dy+10,
                                        fill="#5b0b13",width=2)
        elif accent == "sparkles":
            for dx, dy, size in [(-108,-42,6),(108,-40,7),(-108,46,5),(108,45,6),(0,-113,4)]:
                x, y = cx+dx, cy+dy
                self.canvas.create_line(x-size,y,x+size,y,fill="#5b4214",width=4)
                self.canvas.create_line(x,y-size,x,y+size,fill="#5b4214",width=4)
                self.canvas.create_line(x-size,y,x+size,y,fill=color,width=2)
                self.canvas.create_line(x,y-size,x,y+size,fill=color,width=2)
                self.canvas.create_oval(x-2,y-2,x+2,y+2,fill="#fff8d6",outline="")
        elif accent == "tendrils":
            # Branching Entity-like limbs reaching away from the metal rim.
            for deg in (28, 112, 208, 292):
                a = math.radians(deg)
                points = []
                for dist, bend in [(r+1,0),(r+11,8),(r+21,-5),(r+30,5)]:
                    aa = a + math.radians(bend)
                    points.extend([cx+dist*math.cos(aa), cy+dist*math.sin(aa)])
                self.canvas.create_line(*points, fill="#160d20", width=7, smooth=True)
                self.canvas.create_line(*points, fill=color, width=3, smooth=True)
                ex, ey = points[-2:]
                self.canvas.create_oval(ex-3,ey-3,ex+3,ey+3,fill="#e7c6ff",outline="")
        elif accent == "serum":
            # Toxic fluid capsules and small branching cracks.
            for dx, dy, size in [(-108,18,5),(108,-18,5),(0,-112,4),(0,112,5),(-78,-80,3),(80,80,3)]:
                x,y=cx+dx,cy+dy
                self.canvas.create_oval(x-size-3,y-size-3,x+size+3,y+size+3,
                                        fill="#35200b",outline="#7a3d08",width=1)
                self.canvas.create_oval(x-size,y-size,x+size,y+size,
                                        fill=color,outline="#ffe6a0",width=1)
                self.canvas.create_oval(x-size/2-1,y-size/2-1,x-size/2+1,y-size/2+1,
                                        fill="#fff4c2",outline="")
        elif accent == "frost":
            # Six-point ice crystals at cardinal and diagonal positions.
            for deg in (0,45,90,135,180,225,270,315):
                a=math.radians(deg)
                x,y=cx+(r+19)*math.cos(a),cy+(r+19)*math.sin(a)
                self.canvas.create_line(x-6,y,x+6,y,fill="#1b5260",width=4)
                self.canvas.create_line(x,y-6,x,y+6,fill="#1b5260",width=4)
                self.canvas.create_line(x-5,y-5,x+5,y+5,fill=color,width=2)
                self.canvas.create_line(x-5,y+5,x+5,y-5,fill=color,width=2)

    def draw_perk_badge(self, cx, cy):
        if not self.active_event:
            return

        px = cx + 125
        py = cy

        icon = self.perk_icons_side.get(self.active_event)
        if icon:
            self.canvas.create_image(px, py, image=icon)
        else:
            d_outer = 30
            pts_outer = [
                px, py - d_outer,
                px + d_outer, py,
                px, py + d_outer,
                px - d_outer, py,
            ]
            self.canvas.create_polygon(pts_outer, fill="#111111", outline="#000000", width=2)

            d = 26
            points = [px, py - d, px + d, py, px, py + d, px - d, py]
            self.canvas.create_polygon(points, fill="#4b1d6e", outline="#d4af37", width=2)
            short_labels = {
                "coulrophobia": "COUL",
                "merciless_storm": "STORM",
                "madness": "MAD",
                "huntress_lullaby": "LULL",
                "unnerving_presence": "UNNERV",
                "oppression": "OPPR",
                "chaos": "CHAOS",
            }
            self.draw_stroked_text(
                px, py, short_labels.get(self.active_event, "PERK"), ("Segoe UI", 7, "bold")
            )

        if self.entity_favor_active:
            favor_icon = self.perk_icons_side.get("entity_favor")
            if favor_icon:
                self.canvas.create_image(px, py + 43, image=favor_icon)
            else:
                self.draw_stroked_text(
                    px, py + 38, "ENTITY'S FAVOR", ("Segoe UI", 7, "bold"), fill="#70e000"
                )
        elif self.active_event == "merciless_storm":
            self.draw_stroked_text(
                px,
                py + 38,
                f"{self.merciless_hits}/{MERCILESS_HITS_REQUIRED}",
                ("Segoe UI", 9, "bold"),
            )
        elif self.active_event == "huntress_lullaby":
            self.draw_stroked_text(
                px,
                py + 38,
                f"{self.lullaby_tokens}/{LULLABY_MAX_TOKENS}",
                ("Segoe UI", 9, "bold"),
                fill="#ff9f43",
            )

    def draw_wheel(self):
        """Use the original v21 rendering for Classic Survivor; enhance other themes."""
        theme_name = self.settings.get("wheel_theme", "Classic Survivor")
        if theme_name == "Classic Survivor":
            self._draw_classic_survivor_wheel()
        else:
            self._draw_enhanced_wheel()

    def _draw_classic_survivor_wheel(self):
        self.canvas.delete("all")
        cx = (self.width // 2 - 25) if self.active_event else (self.width // 2)
        cy = (self.height // 2) + 10
        r = 85

        theme_name = self.settings.get("wheel_theme", "Classic Survivor")
        theme = WHEEL_THEMES.get(theme_name, WHEEL_THEMES["Classic Survivor"])

        # Active Streak HUD above wheel
        if self.great_streak >= 2:
            self.draw_stroked_text(
                cx, cy - r - 24, f"GREAT STREAK x{self.great_streak}",
                ("Segoe UI", 9, "bold"), fill="#ffd166"
            )
        elif self.hit_streak >= 1:
            self.draw_stroked_text(
                cx, cy - r - 24, f"STREAK x{self.hit_streak}",
                ("Segoe UI", 9, "bold"), fill="#eeeeee"
            )

        # Outer dark stroke
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#111111", width=7)

        ring_color = theme["ring"]
        if self.active_event == "coulrophobia":
            ring_color = "#b86bff"
        elif self.active_event == "merciless_storm":
            ring_color = "#70c5ff"
        elif self.active_event == "madness":
            ring_color = "#4dffb8"
        elif self.active_event == "huntress_lullaby":
            ring_color = "#ff9f43"
        elif self.active_event == "unnerving_presence":
            ring_color = "#ff5964"
        elif self.active_event == "oppression":
            ring_color = "#ffd166"
        elif self.active_event == "chaos":
            ring_color = "#ff3b30"

        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=ring_color, width=3)

        good_size, great_size = self.get_zone_sizes()
        tk_good_start = 90 - (self.target_start + good_size)

        if self.active_event not in ("merciless_storm", "oppression"):
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start - 1.5,
                extent=good_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=14,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start,
                extent=good_size,
                style=tk.ARC,
                outline=theme["good"],
                width=10,
            )

        if self.active_event in ("merciless_storm", "oppression"):
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start - 1.5,
                extent=good_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=15,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start,
                extent=good_size,
                style=tk.ARC,
                outline=theme["great"],
                width=11,
            )
        else:
            tk_great_start = 90 - (self.target_start + great_size)
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_great_start - 1.5,
                extent=great_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=16,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_great_start,
                extent=great_size,
                style=tk.ARC,
                outline=theme["great"],
                width=12,
            )

        key_label = str(self.settings.get("hit_key", "space")).upper()
        box_half_w = max(28, len(key_label) * 4 + 12)
        self.canvas.create_rectangle(
            cx - box_half_w - 2, cy - 14,
            cx + box_half_w + 2, cy + 14,
            fill="#111111", outline="#000000", width=2,
        )
        self.canvas.create_rectangle(
            cx - box_half_w, cy - 12,
            cx + box_half_w, cy + 12,
            fill="#1a1a1a", outline=theme["great"], width=1,
        )
        self.draw_stroked_text(cx, cy, key_label, ("Segoe UI", 9, "bold"), fill=theme["great"])

        self.draw_perk_badge(cx, cy)

        rad = math.radians(self.angle - 90)
        nx = cx + (r + 11) * math.cos(rad)
        ny = cy + (r + 11) * math.sin(rad)
        ix = cx + (r - 15) * math.cos(rad)
        iy = cy + (r - 15) * math.sin(rad)
        self.canvas.create_line(ix, iy, nx, ny, fill="#111111", width=6)

        nx_in = cx + (r + 10) * math.cos(rad)
        ny_in = cy + (r + 10) * math.sin(rad)
        ix_in = cx + (r - 14) * math.cos(rad)
        iy_in = cy + (r - 14) * math.sin(rad)
        self.canvas.create_line(ix_in, iy_in, nx_in, ny_in, fill=theme["needle"], width=3)

    def _draw_enhanced_wheel(self):
        self.canvas.delete("all")
        cx = (self.width // 2 - 25) if self.active_event else (self.width // 2)
        cy = (self.height // 2) + 10
        r = 85

        theme_name = self.settings.get("wheel_theme", "Classic Survivor")
        theme = WHEEL_THEMES.get(theme_name, WHEEL_THEMES["Classic Survivor"])

        # Active Streak HUD above wheel
        if self.great_streak >= 2:
            self.draw_stroked_text(
                cx, cy - r - 24, f"GREAT STREAK x{self.great_streak}",
                ("Segoe UI", 9, "bold"), fill="#ffd166"
            )
        elif self.hit_streak >= 1:
            self.draw_stroked_text(
                cx, cy - r - 24, f"STREAK x{self.hit_streak}",
                ("Segoe UI", 9, "bold"), fill="#eeeeee"
            )

        # Decorative theme accents (only on non-perk or subtle ring base)
        self.draw_theme_accents(cx, cy, r, theme)

        # Layered instrument housing: shadow, bevel, dark face and inner etching.
        self.canvas.create_oval(cx-r-7, cy-r-5, cx+r+7, cy+r+9,
                                fill="#050505", outline="#000000", width=2)
        self.canvas.create_oval(cx-r-3, cy-r-3, cx+r+3, cy+r+3,
                                fill="#242424", outline="#777777", width=2)
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                fill="#101216", outline="#08090b", width=5)
        self.canvas.create_oval(cx-r+8, cy-r+8, cx+r-8, cy+r-8,
                                outline="#34383d", width=1)

        # Subtle engraved radial marks inside the dark dial.
        for deg in range(0, 360, 15):
            a = math.radians(deg - 90)
            inner, outer = r-13, r-8
            x1,y1=cx+inner*math.cos(a),cy+inner*math.sin(a)
            x2,y2=cx+outer*math.cos(a),cy+outer*math.sin(a)
            self.canvas.create_line(x1,y1,x2,y2,fill="#555b62" if deg%45==0 else "#30343a",
                                    width=2 if deg%45==0 else 1)

        ring_color = theme["ring"]
        if self.active_event == "coulrophobia":
            ring_color = "#b86bff"
        elif self.active_event == "merciless_storm":
            ring_color = "#70c5ff"
        elif self.active_event == "madness":
            ring_color = "#4dffb8"
        elif self.active_event == "huntress_lullaby":
            ring_color = "#ff9f43"
        elif self.active_event == "unnerving_presence":
            ring_color = "#ff5964"
        elif self.active_event == "oppression":
            ring_color = "#ffd166"
        elif self.active_event == "chaos":
            ring_color = "#ff3b30"

        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=ring_color, width=4)
        self.canvas.create_oval(cx-r+4, cy-r+4, cx+r-4, cy+r-4,
                                outline="#ffffff", width=1)

        good_size, great_size = self.get_zone_sizes()
        tk_good_start = 90 - (self.target_start + good_size)

        if self.active_event not in ("merciless_storm", "oppression"):
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start - 1.5,
                extent=good_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=14,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start,
                extent=good_size,
                style=tk.ARC,
                outline=theme["good"],
                width=10,
            )

        if self.active_event in ("merciless_storm", "oppression"):
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start - 1.5,
                extent=good_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=15,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_good_start,
                extent=good_size,
                style=tk.ARC,
                outline=theme["great"],
                width=11,
            )
        else:
            tk_great_start = 90 - (self.target_start + great_size)
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_great_start - 1.5,
                extent=great_size + 3,
                style=tk.ARC,
                outline="#111111",
                width=16,
            )
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=tk_great_start,
                extent=great_size,
                style=tk.ARC,
                outline=theme["great"],
                width=12,
            )

        key_label = str(self.settings.get("hit_key", "space")).upper()
        box_half_w = max(28, len(key_label) * 4 + 12)
        self.canvas.create_rectangle(
            cx - box_half_w - 2, cy - 14,
            cx + box_half_w + 2, cy + 14,
            fill="#111111", outline="#000000", width=2,
        )
        self.canvas.create_rectangle(
            cx - box_half_w, cy - 12,
            cx + box_half_w, cy + 12,
            fill="#1a1a1a", outline=theme["great"], width=1,
        )
        self.draw_stroked_text(cx, cy, key_label, ("Segoe UI", 9, "bold"), fill=theme["great"])

        self.draw_perk_badge(cx, cy)

        rad = math.radians(self.angle - 90)
        nx = cx + (r + 11) * math.cos(rad)
        ny = cy + (r + 11) * math.sin(rad)
        ix = cx + (r - 15) * math.cos(rad)
        iy = cy + (r - 15) * math.sin(rad)
        self.canvas.create_line(ix, iy, nx, ny, fill="#111111", width=6)

        nx_in = cx + (r + 10) * math.cos(rad)
        ny_in = cy + (r + 10) * math.sin(rad)
        ix_in = cx + (r - 14) * math.cos(rad)
        iy_in = cy + (r - 14) * math.sin(rad)
        self.canvas.create_line(ix_in, iy_in, nx_in, ny_in, fill=theme["needle"], width=3)
        self.canvas.create_oval(cx-7, cy-7, cx+7, cy+7,
                                fill="#050505", outline=theme["ring"], width=2)
        self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3,
                                fill=theme["great"], outline="#ffffff", width=1)

    def on_hit_key_pressed(self, event):
        if not self.active:
            return

        good_size, great_size = self.get_zone_sizes()

        if self.active_event == "merciless_storm":
            if self.is_angle_in_zone(self.angle, self.target_start, good_size):
                self.root.after(0, self.handle_merciless_hit)
            else:
                self.root.after(0, lambda: self.resolve_check("MISS"))
            return

        if self.active_event == "oppression":
            if self.is_angle_in_zone(self.angle, self.target_start, good_size):
                self.root.after(0, lambda: self.resolve_check("GREAT"))
            else:
                self.root.after(0, lambda: self.resolve_check("MISS"))
            return

        if self.is_angle_in_zone(self.angle, self.target_start, great_size):
            self.root.after(0, lambda: self.resolve_check("GREAT"))
        elif self.is_angle_in_zone(self.angle, self.target_start, good_size):
            self.root.after(0, lambda: self.resolve_check("GOOD"))
        else:
            self.root.after(0, lambda: self.resolve_check("MISS"))

    def handle_merciless_hit(self):
        if not self.active:
            return
        self.merciless_hits += 1
        if self.merciless_hits >= MERCILESS_HITS_REQUIRED:
            self.resolve_check("GREAT")
        else:
            self.sfx.play("good")
            self.direction *= -1
            self.spawn_next_merciless_target()
            self.draw_wheel()

    def show_result_flash(self, label, color, sublabel=None):
        self.canvas.delete("all")
        cx, cy = self.width // 2, self.height // 2
        self.draw_stroked_text(cx, cy - 8, label, ("Segoe UI", 14, "bold"), fill=color)
        if sublabel:
            self.draw_stroked_text(cx, cy + 16, sublabel, ("Segoe UI", 9, "bold"), fill="#ffd166")
        self.feedback_after_id = self.root.after(550, self.hide_overlay)

    def hide_overlay(self):
        self.feedback_after_id = None
        self.canvas.delete("all")
        self.root.withdraw()

    def resolve_check(self, result):
        if not self.active:
            return
        self.active = False

        self.lifetime_total += 1
        if result == "GREAT":
            self.lifetime_great += 1
        elif result == "GOOD":
            self.lifetime_good += 1
        else:
            self.lifetime_misses += 1
        self.settings.update({
            "lifetime_total": self.lifetime_total,
            "lifetime_great": self.lifetime_great,
            "lifetime_good": self.lifetime_good,
            "lifetime_misses": self.lifetime_misses,
        })
        save_settings(self.settings)

        new_record = False
        if result in ("GREAT", "GOOD"):
            self.consecutive_misses = 0
            self.hit_streak += 1
            if self.hit_streak > self.best_hit_streak:
                self.best_hit_streak = self.hit_streak
                self.settings["best_hit_streak"] = self.best_hit_streak
                new_record = True
            if result == "GREAT":
                self.great_streak += 1
                if self.great_streak > self.best_great_streak:
                    self.best_great_streak = self.great_streak
                    self.settings["best_great_streak"] = self.best_great_streak
                    new_record = True
            else:
                self.great_streak = 0
            if new_record:
                save_settings(self.settings)
        else:
            self.hit_streak = 0
            self.great_streak = 0
            self.consecutive_misses += 1

        if self.active_event == "huntress_lullaby":
            if result in ("GREAT", "GOOD"):
                if self.lullaby_tokens >= LULLABY_MAX_TOKENS:
                    self.lullaby_tokens = 0
                else:
                    self.lullaby_tokens += 1
            else:
                self.lullaby_tokens = 0

        if result == "GREAT":
            self.sfx.play("great")
            sub = "NEW BEST STREAK!" if new_record else (f"GREAT x{self.great_streak}" if self.great_streak >= 2 else None)
            self.show_result_flash(f"GREAT! x{self.hit_streak}", "#ffd166", sub)
        elif result == "GOOD":
            self.sfx.play("good")
            sub = "NEW BEST STREAK!" if new_record else None
            self.show_result_flash(f"GOOD x{self.hit_streak}", "#eeeeee", sub)
        else:
            self.sfx.play("miss")
            self.trigger_miss_punishment()
            self.show_result_flash("MISSED!", "#ff4d4d")


if __name__ == "__main__":
    app = SkillCheckOverlay()
    app.root.mainloop()
