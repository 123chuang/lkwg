from __future__ import annotations

import platform
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import tkinter as tk
from tkinter import messagebox, ttk


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
        from pynput import keyboard
    except ModuleNotFoundError:
        keyboard = None
        missing.append("pynput")

    if platform.system() != "Windows":
        try:
            from pynput import mouse
        except ModuleNotFoundError:
            mouse = None
            if "pynput" not in missing:
                missing.append("pynput")
    else:
        mouse = None

    if missing:
        deps = " ".join(missing)
        raise RuntimeError(
            "缺少运行依赖："
            + ", ".join(missing)
            + f"\n\n请先运行：\npython3 -m pip install {deps}"
        )

    return keyboard, mouse


class SignalSender(Protocol):
    def tap_space(self, hold_seconds: float) -> None:
        ...

    def left_down(self) -> None:
        ...

    def left_up(self) -> None:
        ...


class WindowsSendInputSender:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes

        ULONG_PTR = wintypes.WPARAM

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            )

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            )

        class INPUTUNION(ctypes.Union):
            _fields_ = (
                ("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
            )

        class INPUT(ctypes.Structure):
            _fields_ = (
                ("type", wintypes.DWORD),
                ("union", INPUTUNION),
            )

        self.INPUT = INPUT
        self.KEYBDINPUT = KEYBDINPUT
        self.MOUSEINPUT = MOUSEINPUT
        self.INPUT_KEYBOARD = 1
        self.INPUT_MOUSE = 0
        self.KEYEVENTF_KEYUP = 0x0002
        self.MOUSEEVENTF_LEFTDOWN = 0x0002
        self.MOUSEEVENTF_LEFTUP = 0x0004
        self.VK_SPACE = 0x20

        self.send_input = ctypes.windll.user32.SendInput
        self.send_input.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        )
        self.send_input.restype = wintypes.UINT

    def tap_space(self, hold_seconds: float) -> None:
        self._send_keyboard(self.VK_SPACE, key_up=False)
        if hold_seconds > 0:
            time.sleep(hold_seconds)
        self._send_keyboard(self.VK_SPACE, key_up=True)

    def left_down(self) -> None:
        self._send_mouse(self.MOUSEEVENTF_LEFTDOWN)

    def left_up(self) -> None:
        self._send_mouse(self.MOUSEEVENTF_LEFTUP)

    def _send_keyboard(self, vk: int, key_up: bool) -> None:
        flags = self.KEYEVENTF_KEYUP if key_up else 0
        event = self.INPUT()
        event.type = self.INPUT_KEYBOARD
        event.union.ki = self.KEYBDINPUT(vk, 0, flags, 0, 0)
        self._send(event)

    def _send_mouse(self, flags: int) -> None:
        event = self.INPUT()
        event.type = self.INPUT_MOUSE
        event.union.mi = self.MOUSEINPUT(0, 0, 0, flags, 0, 0)
        self._send(event)

    def _send(self, event) -> None:
        sent = self.send_input(1, self.ctypes.byref(event), self.ctypes.sizeof(event))
        if sent != 1:
            raise OSError("SendInput 调用失败")


class PynputSender:
    def __init__(self, keyboard_module, mouse_module) -> None:
        self.keyboard_module = keyboard_module
        self.keyboard = keyboard_module.Controller()
        self.mouse = mouse_module.Controller()

    def tap_space(self, hold_seconds: float) -> None:
        self.keyboard.press(self.keyboard_module.Key.space)
        if hold_seconds > 0:
            time.sleep(hold_seconds)
        self.keyboard.release(self.keyboard_module.Key.space)

    def left_down(self) -> None:
        self.mouse.press(self.mouse_module.Button.left)

    def left_up(self) -> None:
        self.mouse.release(self.mouse_module.Button.left)


def create_signal_sender(keyboard_module, mouse_module) -> SignalSender:
    if platform.system() == "Windows":
        return WindowsSendInputSender()
    return PynputSender(keyboard_module, mouse_module)


enable_windows_dpi_awareness()

try:
    keyboard, mouse = load_runtime_dependencies()
except RuntimeError as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("依赖缺失", str(exc))
    print(exc, file=sys.stderr)
    sys.exit(1)


@dataclass(frozen=True)
class SignalSettings:
    duration: float
    min_interval: float
    max_interval: float
    left_hold_min: float
    left_hold_max: float
    space_hold: float
    start_delay: float
    send_space: bool
    send_left: bool
    minimize_on_start: bool


class SignalSenderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("键鼠信号发送器")
        self.root.geometry("520x520")
        self.root.minsize(500, 500)

        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.sender = create_signal_sender(keyboard, mouse)

        self.duration_seconds = tk.StringVar(value="60")
        self.min_interval = tk.StringVar(value="0.8")
        self.max_interval = tk.StringVar(value="1.8")
        self.left_hold_min = tk.StringVar(value="0.04")
        self.left_hold_max = tk.StringVar(value="0.12")
        self.space_hold = tk.StringVar(value="0.03")
        self.start_delay = tk.StringVar(value="3")
        self.send_space = tk.BooleanVar(value=True)
        self.send_left = tk.BooleanVar(value=True)
        self.minimize_on_start = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="未启动")
        self.backend_text = tk.StringVar(value=self.describe_backend())

        self.build_ui()
        self.bind_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def describe_backend(self) -> str:
        if platform.system() == "Windows":
            return "发送方式：Windows SendInput"
        return "发送方式：pynput 兼容模式"

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="键鼠信号发送器", font=("Arial", 18, "bold"))
        title.pack(anchor=tk.W)

        status_row = ttk.Frame(outer)
        status_row.pack(fill=tk.X, pady=(12, 8))
        ttk.Label(status_row, text="状态：").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.status).pack(side=tk.LEFT)

        ttk.Label(outer, textvariable=self.backend_text, foreground="#555").pack(anchor=tk.W)

        actions = ttk.LabelFrame(outer, text="发送信号")
        actions.pack(fill=tk.X, pady=10)
        ttk.Checkbutton(actions, text="发送键盘空格", variable=self.send_space).grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=8,
            pady=(8, 4),
        )
        ttk.Checkbutton(actions, text="发送鼠标左键", variable=self.send_left).grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=8,
            pady=(4, 8),
        )

        settings = ttk.LabelFrame(outer, text="设置")
        settings.pack(fill=tk.X, pady=8)
        self.add_entry(settings, 0, "运行时长(秒，0=不限)", self.duration_seconds)
        self.add_entry(settings, 1, "左键信号间隔最小(秒)", self.min_interval)
        self.add_entry(settings, 2, "左键信号间隔最大(秒)", self.max_interval)
        self.add_entry(settings, 3, "左键持续最短时间(秒)", self.left_hold_min)
        self.add_entry(settings, 4, "左键持续最长时间(秒)", self.left_hold_max)
        self.add_entry(settings, 5, "空格持续时间(秒)", self.space_hold)
        self.add_entry(settings, 6, "启动前延迟(秒)", self.start_delay)
        ttk.Checkbutton(settings, text="启动后最小化窗口", variable=self.minimize_on_start).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky=tk.W,
            padx=8,
            pady=(6, 8),
        )

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(16, 8))
        ttk.Button(controls, text="启动", command=self.start).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="暂停/继续", command=self.toggle_pause).pack(side=tk.LEFT, padx=8)
        ttk.Button(controls, text="停止", command=self.stop).pack(side=tk.LEFT, padx=8)

        hint = ttk.Label(
            outer,
            text="热键：F8 启动/暂停，F9 停止。信号会发送到当前获得焦点的窗口。",
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

    def parse_settings(self) -> SignalSettings:
        duration = max(0.0, float(self.duration_seconds.get()))
        min_interval = max(0.01, float(self.min_interval.get()))
        max_interval = max(min_interval, float(self.max_interval.get()))
        left_hold_min = max(0.0, float(self.left_hold_min.get()))
        left_hold_max = max(left_hold_min, float(self.left_hold_max.get()))
        space_hold = max(0.0, float(self.space_hold.get()))
        start_delay = max(0.0, float(self.start_delay.get()))
        return SignalSettings(
            duration=duration,
            min_interval=min_interval,
            max_interval=max_interval,
            left_hold_min=left_hold_min,
            left_hold_max=left_hold_max,
            space_hold=space_hold,
            start_delay=start_delay,
            send_space=self.send_space.get(),
            send_left=self.send_left.get(),
            minimize_on_start=self.minimize_on_start.get(),
        )

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            self.pause_event.clear()
            self.status.set("运行中")
            return

        try:
            settings = self.parse_settings()
        except ValueError:
            messagebox.showerror("设置错误", "请确认时长、间隔、持续时间和启动延迟都是数字。")
            return

        if not settings.send_space and not settings.send_left:
            messagebox.showwarning("缺少信号", "请至少选择一种要发送的信号。")
            return

        self.stop_event.clear()
        self.pause_event.clear()
        if settings.minimize_on_start:
            self.root.iconify()
        self.worker = threading.Thread(
            target=self.run_loop,
            args=(settings,),
            daemon=True,
        )
        self.worker.start()
        self.status.set("运行中")

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

    def run_loop(self, settings: SignalSettings) -> None:
        left_is_down = False
        try:
            if settings.start_delay > 0:
                self.set_status_threadsafe(f"等待启动：{settings.start_delay:g} 秒")
                self.sleep_interruptibly(settings.start_delay)
                if self.stop_event.is_set():
                    return

            start_time = time.monotonic()
            action_count = 0

            while not self.stop_event.is_set():
                if settings.duration and time.monotonic() - start_time >= settings.duration:
                    break

                while self.pause_event.is_set() and not self.stop_event.is_set():
                    time.sleep(0.03)
                if self.stop_event.is_set():
                    break

                if settings.send_space:
                    self.sender.tap_space(settings.space_hold)
                    if self.stop_event.is_set():
                        break

                if settings.send_left:
                    self.sender.left_down()
                    left_is_down = True
                    self.sleep_until_stop(
                        random.uniform(settings.left_hold_min, settings.left_hold_max)
                    )
                    self.sender.left_up()
                    left_is_down = False

                action_count += 1
                self.set_status_threadsafe(f"运行中：已发送 {action_count} 轮")
                self.sleep_interruptibly(random.uniform(settings.min_interval, settings.max_interval))
        except Exception as exc:
            if left_is_down:
                try:
                    self.sender.left_up()
                except Exception:
                    pass
            self.root.after(0, lambda: messagebox.showerror("运行错误", str(exc)))
            self.root.after(0, lambda: self.status.set("错误"))
        else:
            self.root.after(
                0,
                lambda: self.status.set("已完成" if not self.stop_event.is_set() else "已停止"),
            )
        finally:
            if left_is_down:
                try:
                    self.sender.left_up()
                except Exception:
                    pass
            self.stop_event.set()

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

    def sleep_until_stop(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.03, remaining))

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
    SignalSenderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
