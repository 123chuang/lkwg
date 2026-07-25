from __future__ import annotations

import random
import sys
import threading
import time
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def enable_windows_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return

    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        return


def load_runtime_dependencies():
    missing: list[str] = []

    try:
        import pyautogui
    except ModuleNotFoundError:
        pyautogui = None
        missing.append("pyautogui")

    try:
        import mss
    except ModuleNotFoundError:
        mss = None
        missing.append("mss")

    try:
        import cv2
    except ModuleNotFoundError:
        cv2 = None
        missing.append("opencv-python")

    try:
        from PIL import Image
    except ModuleNotFoundError:
        Image = None
        missing.append("Pillow")

    try:
        from pynput import keyboard
    except ModuleNotFoundError:
        keyboard = None
        missing.append("pynput")

    if missing:
        deps = " ".join(missing)
        raise RuntimeError(
            "缺少运行依赖："
            + ", ".join(missing)
            + f"\n\n请先运行：\npython3 -m pip install {deps}"
        )

    return pyautogui, mss, cv2, Image, keyboard


enable_windows_dpi_awareness()

try:
    pyautogui, mss, cv2, Image, keyboard = load_runtime_dependencies()
except RuntimeError as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("依赖缺失", str(exc))
    print(exc, file=sys.stderr)
    sys.exit(1)


pyautogui.FAILSAFE = True


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def random_point(self) -> tuple[int, int]:
        return (
            random.randint(self.left, max(self.left, self.right - 1)),
            random.randint(self.top, max(self.top, self.bottom - 1)),
        )


@dataclass(frozen=True)
class ClickSettings:
    duration: float
    min_delay: float
    max_delay: float
    confidence: float
    offset_x: int
    offset_y: int
    use_curve: bool
    move_duration: float
    random_speed: bool
    pre_click_min: float
    pre_click_max: float
    press_min: float
    press_max: float
    start_delay: float
    minimize_on_start: bool


class RegionSelector(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        on_selected: Callable[[Region], None],
        on_cancel: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.on_selected = on_selected
        self.on_cancel = on_cancel
        self.completed = False
        self.start_x = 0
        self.start_y = 0
        self.rect_id: int | None = None

        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.28)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.overrideredirect(True)

        self.canvas = tk.Canvas(self, cursor="crosshair", bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(
            self.winfo_screenwidth() // 2,
            36,
            text="拖拽选择区域，按 Esc 取消",
            fill="white",
            font=("Arial", 18),
        )

        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event: tk.Event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="#22c55e",
            width=3,
        )

    def on_drag(self, event: tk.Event) -> None:
        if self.rect_id is not None:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event: tk.Event) -> None:
        left, right = sorted((self.start_x, event.x))
        top, bottom = sorted((self.start_y, event.y))
        if right - left < 5 or bottom - top < 5:
            self.cancel()
            return

        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        self.completed = True
        self.on_selected(Region(root_x + left, root_y + top, right - left, bottom - top))
        self.destroy()

    def cancel(self) -> None:
        if not self.completed and self.on_cancel is not None:
            self.on_cancel()
        self.destroy()


class AutoClickerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("通用区域点击器")
        self.root.geometry("560x760")
        self.root.minsize(520, 740)

        self.region: Region | None = None
        self.template_image = None
        self.template_path: Path | None = None
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.lock = threading.Lock()

        self.mode = tk.StringVar(value="random")
        self.duration_seconds = tk.StringVar(value="60")
        self.min_interval = tk.StringVar(value="0.8")
        self.max_interval = tk.StringVar(value="1.8")
        self.confidence = tk.StringVar(value="0.82")
        self.offset_x = tk.StringVar(value="0")
        self.offset_y = tk.StringVar(value="0")
        self.use_curve = tk.BooleanVar(value=True)
        self.move_duration = tk.StringVar(value="0.35")
        self.random_speed = tk.BooleanVar(value=True)
        self.pre_click_min = tk.StringVar(value="0.05")
        self.pre_click_max = tk.StringVar(value="0.18")
        self.press_min = tk.StringVar(value="0.04")
        self.press_max = tk.StringVar(value="0.12")
        self.start_delay = tk.StringVar(value="3")
        self.minimize_on_start = tk.BooleanVar(value=True)
        self.dry_run = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="未启动")
        self.region_text = tk.StringVar(value="未选择")
        self.template_text = tk.StringVar(value="未加载")

        self.build_ui()
        self.bind_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="通用区域点击器", font=("Arial", 18, "bold"))
        title.pack(anchor=tk.W)

        status_row = ttk.Frame(outer)
        status_row.pack(fill=tk.X, pady=(12, 8))
        ttk.Label(status_row, text="状态：").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.status).pack(side=tk.LEFT)

        region_frame = ttk.LabelFrame(outer, text="区域")
        region_frame.pack(fill=tk.X, pady=8)
        ttk.Button(region_frame, text="选择点击区域", command=self.select_region).pack(
            side=tk.LEFT, padx=8, pady=10
        )
        ttk.Label(region_frame, textvariable=self.region_text).pack(side=tk.LEFT, padx=8)

        mode_frame = ttk.LabelFrame(outer, text="模式")
        mode_frame.pack(fill=tk.X, pady=8)
        ttk.Radiobutton(
            mode_frame,
            text="区域随机点击",
            variable=self.mode,
            value="random",
        ).pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Radiobutton(
            mode_frame,
            text="目标识别点击",
            variable=self.mode,
            value="target",
        ).pack(anchor=tk.W, padx=8, pady=(2, 8))

        template_frame = ttk.LabelFrame(outer, text="目标模板")
        template_frame.pack(fill=tk.X, pady=8)
        ttk.Button(template_frame, text="框选目标模板", command=self.capture_template).pack(
            side=tk.LEFT, padx=8, pady=10
        )
        ttk.Button(template_frame, text="加载模板图片", command=self.load_template).pack(
            side=tk.LEFT, padx=8, pady=10
        )
        ttk.Label(template_frame, textvariable=self.template_text).pack(side=tk.LEFT, padx=8)

        settings = ttk.LabelFrame(outer, text="设置")
        settings.pack(fill=tk.X, pady=8)

        self.add_entry(settings, 0, "运行时长(秒，0=不限)", self.duration_seconds)
        self.add_entry(settings, 1, "最小间隔(秒)", self.min_interval)
        self.add_entry(settings, 2, "最大间隔(秒)", self.max_interval)
        self.add_entry(settings, 3, "匹配阈值(0-1)", self.confidence)
        self.add_entry(settings, 4, "点击偏移 X", self.offset_x)
        self.add_entry(settings, 5, "点击偏移 Y", self.offset_y)
        self.add_entry(settings, 6, "曲线移动耗时(秒)", self.move_duration)
        self.add_entry(settings, 7, "点击前停顿最小(秒)", self.pre_click_min)
        self.add_entry(settings, 8, "点击前停顿最大(秒)", self.pre_click_max)
        self.add_entry(settings, 9, "按压最短时间(秒)", self.press_min)
        self.add_entry(settings, 10, "按压最长时间(秒)", self.press_max)
        self.add_entry(settings, 11, "启动前延迟(秒)", self.start_delay)
        ttk.Checkbutton(settings, text="鼠标按曲线轨迹移动到点击点", variable=self.use_curve).grid(
            row=12,
            column=0,
            columnspan=2,
            sticky=tk.W,
            padx=8,
            pady=(6, 2),
        )
        ttk.Checkbutton(settings, text="移动速度随机变化", variable=self.random_speed).grid(
            row=13,
            column=0,
            columnspan=2,
            sticky=tk.W,
            padx=8,
            pady=(2, 2),
        )
        ttk.Checkbutton(settings, text="启动后最小化窗口", variable=self.minimize_on_start).grid(
            row=14,
            column=0,
            columnspan=2,
            sticky=tk.W,
            padx=8,
            pady=(2, 2),
        )
        ttk.Checkbutton(settings, text="测试模式：只移动鼠标，不点击", variable=self.dry_run).grid(
            row=15,
            column=0,
            columnspan=2,
            sticky=tk.W,
            padx=8,
            pady=(2, 8),
        )

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(16, 8))
        ttk.Button(controls, text="启动", command=self.start).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="暂停/继续", command=self.toggle_pause).pack(side=tk.LEFT, padx=8)
        ttk.Button(controls, text="停止", command=self.stop).pack(side=tk.LEFT, padx=8)

        hint = ttk.Label(
            outer,
            text="热键：F8 启动/暂停，F9 停止。安全角：鼠标移到屏幕左上角会中断点击。",
            foreground="#555",
        )
        hint.pack(anchor=tk.W, pady=(8, 0))

    def add_entry(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, padx=8, pady=5)
        ttk.Entry(parent, textvariable=variable, width=12).grid(
            row=row,
            column=1,
            sticky=tk.W,
            padx=8,
            pady=5,
        )
        parent.columnconfigure(2, weight=1)

    def bind_hotkeys(self) -> None:
        def on_press(key) -> None:
            try:
                if key == keyboard.Key.f8:
                    self.root.after(0, self.hotkey_start_or_pause)
                elif key == keyboard.Key.f9:
                    self.root.after(0, self.stop)
            except RuntimeError:
                return

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def hotkey_start_or_pause(self) -> None:
        if self.worker and self.worker.is_alive():
            self.toggle_pause()
        else:
            self.start()

    def select_region(self) -> None:
        self.root.withdraw()
        self.root.after(180, lambda: RegionSelector(self.root, self.set_region, self.root.deiconify))

    def set_region(self, region: Region) -> None:
        self.root.deiconify()
        with self.lock:
            self.region = region
        self.region_text.set(
            f"x={region.left}, y={region.top}, w={region.width}, h={region.height}"
        )

    def capture_template(self) -> None:
        self.root.withdraw()

        def selected(region: Region) -> None:
            self.root.deiconify()
            image = self.screenshot(region)
            with self.lock:
                self.template_image = self.pil_to_cv_gray(image)
                self.template_path = None
            self.template_text.set(f"已框选模板 {region.width}x{region.height}")

        self.root.after(180, lambda: RegionSelector(self.root, selected, self.root.deiconify))

    def load_template(self) -> None:
        path = filedialog.askopenfilename(
            title="选择模板图片",
            filetypes=(
                ("图片文件", "*.png *.jpg *.jpeg *.bmp"),
                ("所有文件", "*.*"),
            ),
        )
        if not path:
            return
        image = Image.open(path).convert("RGB")
        with self.lock:
            self.template_image = self.pil_to_cv_gray(image)
            self.template_path = Path(path)
        self.template_text.set(Path(path).name)

    def screenshot(self, region: Region):
        with mss.mss() as screen:
            raw = screen.grab(
                {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height,
                }
            )
        return Image.frombytes("RGB", raw.size, raw.rgb)

    def pil_to_cv_gray(self, image):
        import numpy as np

        array = np.array(image.convert("RGB"))
        return cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)

    def parse_settings(self) -> ClickSettings:
        duration = max(0.0, float(self.duration_seconds.get()))
        min_delay = max(0.01, float(self.min_interval.get()))
        max_delay = max(min_delay, float(self.max_interval.get()))
        confidence = min(1.0, max(0.0, float(self.confidence.get())))
        offset_x = int(float(self.offset_x.get()))
        offset_y = int(float(self.offset_y.get()))
        move_duration = max(0.0, float(self.move_duration.get()))
        pre_click_min = max(0.0, float(self.pre_click_min.get()))
        pre_click_max = max(pre_click_min, float(self.pre_click_max.get()))
        press_min = max(0.0, float(self.press_min.get()))
        press_max = max(press_min, float(self.press_max.get()))
        start_delay = max(0.0, float(self.start_delay.get()))
        return ClickSettings(
            duration=duration,
            min_delay=min_delay,
            max_delay=max_delay,
            confidence=confidence,
            offset_x=offset_x,
            offset_y=offset_y,
            use_curve=self.use_curve.get(),
            move_duration=move_duration,
            random_speed=self.random_speed.get(),
            pre_click_min=pre_click_min,
            pre_click_max=pre_click_max,
            press_min=press_min,
            press_max=press_max,
            start_delay=start_delay,
            minimize_on_start=self.minimize_on_start.get(),
        )

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            self.pause_event.clear()
            self.status.set("运行中")
            return

        if self.region is None:
            messagebox.showwarning("缺少区域", "请先选择点击区域。")
            return
        if self.mode.get() == "target" and self.template_image is None:
            messagebox.showwarning("缺少模板", "目标识别模式需要先框选或加载目标模板。")
            return

        try:
            settings = self.parse_settings()
        except ValueError:
            messagebox.showerror("设置错误", "请确认时长、间隔、阈值、偏移、移动、点击和启动延迟参数都是数字。")
            return

        with self.lock:
            region = self.region
            mode = self.mode.get()
            template = self.template_image
            dry_run = self.dry_run.get()

        self.stop_event.clear()
        self.pause_event.clear()
        if settings.minimize_on_start:
            self.root.iconify()
        self.worker = threading.Thread(
            target=self.run_loop,
            args=(region, mode, template, settings, dry_run),
            daemon=True,
        )
        self.worker.start()
        self.status.set("测试运行中" if dry_run else "运行中")

    def toggle_pause(self) -> None:
        if not self.worker or not self.worker.is_alive():
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.status.set("运行中")
        else:
            self.pause_event.set()
            self.status.set("已暂停")

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()
        self.status.set("已停止")

    def run_loop(
        self,
        region: Region | None,
        mode: str,
        template,
        settings: ClickSettings,
        dry_run: bool,
    ) -> None:
        try:
            if settings.start_delay > 0:
                self.set_status_threadsafe(f"等待启动：{settings.start_delay:g} 秒")
                self.sleep_interruptibly(settings.start_delay)
                if self.stop_event.is_set():
                    return

            start_time = time.monotonic()
            action_count = 0
            miss_count = 0

            while not self.stop_event.is_set():
                if settings.duration and time.monotonic() - start_time >= settings.duration:
                    break

                if self.pause_event.is_set():
                    time.sleep(0.1)
                    continue

                if region is None:
                    break

                if mode == "target":
                    point = self.find_target(region, template, settings.confidence)
                    if point is None:
                        miss_count += 1
                        if miss_count == 1 or miss_count % 10 == 0:
                            self.set_status_threadsafe(f"运行中：未找到目标({miss_count})")
                        time.sleep(0.2)
                        continue
                    miss_count = 0
                    x, y = point
                    x += settings.offset_x
                    y += settings.offset_y
                else:
                    x, y = region.random_point()

                self.move_mouse(x, y, settings)
                if self.stop_event.is_set():
                    break

                if dry_run:
                    pass
                else:
                    self.perform_click(x, y, settings)
                action_count += 1
                action_name = "已移动" if dry_run else "已点击"
                self.set_status_threadsafe(f"运行中：{action_name} {action_count} 次")
                time.sleep(random.uniform(settings.min_delay, settings.max_delay))
        except pyautogui.FailSafeException:
            self.root.after(0, lambda: self.status.set("安全角已触发，已停止"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("运行错误", str(exc)))
            self.root.after(0, lambda: self.status.set("错误"))
        else:
            self.root.after(
                0,
                lambda: self.status.set("已完成" if not self.stop_event.is_set() else "已停止"),
            )
        finally:
            self.stop_event.set()

    def perform_click(self, x: int, y: int, settings: ClickSettings) -> None:
        self.sleep_interruptibly(random.uniform(settings.pre_click_min, settings.pre_click_max))
        if self.stop_event.is_set():
            return

        pyautogui.mouseDown(x=x, y=y)
        try:
            self.sleep_interruptibly(random.uniform(settings.press_min, settings.press_max))
        finally:
            pyautogui.mouseUp(x=x, y=y)

    def set_status_threadsafe(self, text: str) -> None:
        self.root.after(0, lambda: self.status.set(text))

    def sleep_interruptibly(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self.pause_event.is_set():
                time.sleep(0.03)
            else:
                time.sleep(min(0.03, remaining))

    def move_mouse(self, x: int, y: int, settings: ClickSettings) -> None:
        if not settings.use_curve or settings.move_duration <= 0:
            pyautogui.moveTo(x=x, y=y)
            return

        start_x, start_y = pyautogui.position()
        distance = ((x - start_x) ** 2 + (y - start_y) ** 2) ** 0.5
        if distance < 2:
            pyautogui.moveTo(x=x, y=y)
            return

        steps = max(8, min(80, int(settings.move_duration * 60)))
        normal_x = -(y - start_y) / distance
        normal_y = (x - start_x) / distance
        arc = random.uniform(-0.25, 0.25) * distance
        control_x = (start_x + x) / 2 + normal_x * arc
        control_y = (start_y + y) / 2 + normal_y * arc
        intervals = self.build_move_intervals(settings.move_duration, steps, settings.random_speed)

        for index in range(1, steps + 1):
            if self.stop_event.is_set():
                return
            while self.pause_event.is_set() and not self.stop_event.is_set():
                time.sleep(0.03)

            t = index / steps
            eased = t * t * (3 - 2 * t)
            inverse = 1 - eased
            next_x = (
                inverse ** 2 * start_x
                + 2 * inverse * eased * control_x
                + eased ** 2 * x
            )
            next_y = (
                inverse ** 2 * start_y
                + 2 * inverse * eased * control_y
                + eased ** 2 * y
            )
            pyautogui.moveTo(x=round(next_x), y=round(next_y), duration=0)
            time.sleep(intervals[index - 1])

    def build_move_intervals(
        self,
        move_duration: float,
        steps: int,
        random_speed: bool,
    ) -> list[float]:
        interval = move_duration / steps
        if not random_speed:
            return [interval] * steps

        weights = [random.uniform(0.45, 1.75) for _ in range(steps)]
        total_weight = sum(weights)
        return [move_duration * weight / total_weight for weight in weights]

    def find_target(self, region: Region, template, confidence: float) -> tuple[int, int] | None:
        if template is None:
            return None

        screenshot = self.pil_to_cv_gray(self.screenshot(region))
        template_height, template_width = template.shape[:2]
        if screenshot.shape[0] < template_height or screenshot.shape[1] < template_width:
            return None

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(result)
        if max_value < confidence:
            return None

        return (
            region.left + max_location[0] + template_width // 2,
            region.top + max_location[1] + template_height // 2,
        )

    def on_close(self) -> None:
        self.stop_event.set()
        if hasattr(self, "listener"):
            self.listener.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    AutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
