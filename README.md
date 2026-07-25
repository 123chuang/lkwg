# 通用区域点击器

一个本地桌面自动点击工具，支持：

- 框选点击区域
- 随机区域点击
- 模板目标识别后点击
- 启动、暂停、停止
- 设置运行时长、点击间隔、目标匹配阈值和点击偏移
- 鼠标曲线轨迹移动，可设置每次移动耗时、随机速度变化、点击前停顿和按压时间
- 测试模式：只移动鼠标，不真正点击
- 全局热键：`F8` 启动/暂停，`F9` 停止

## Windows 运行环境

推荐在 Windows 上安装 Python 3.11 或 3.12，并在安装时勾选 “Add Python to PATH”。

### 方式一：直接运行源码

把整个目录复制到 Windows 后，可以直接双击：

```bat
run_windows.bat
```

也可以手动运行：

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python auto_clicker.py
```

如果目标程序以管理员身份运行，这个工具也需要以管理员身份运行，否则 Windows 可能会阻止模拟点击。高分屏缩放下程序会自动启用 DPI 感知，减少框选区域和实际点击位置偏移。

### 方式二：打包成 exe

在一台已经安装 Python 的 Windows 电脑上执行：

```bat
build_windows.bat
```

打包完成后，可执行文件在：

```text
dist\GenericAutoClicker.exe
```

把这个 exe 复制到没有 Python 环境的 Windows 电脑上即可运行。第一次启动时，杀毒软件可能会扫描较久；这是单文件 PyInstaller 程序的常见现象。

注意：建议在 Windows 上构建 Windows 版 exe。Linux 上直接运行 PyInstaller 通常只能生成 Linux 可执行文件，不能直接生成 Windows exe。

### 方式三：不在 Windows 安装 Python

如果 Windows 电脑没有 Python，也不想安装 Python，可以用 GitHub Actions 云端打包：

1. 把这个项目上传到 GitHub 仓库。
2. 打开仓库的 `Actions` 页面。
3. 选择 `Build Windows EXE`。
4. 点击 `Run workflow`。
5. 构建完成后，在运行记录的 `Artifacts` 里下载 `GenericAutoClicker-windows`。
6. 解压后得到 `GenericAutoClicker.exe`，复制到 Windows 电脑运行。

这个流程里的 Python 和 PyInstaller 都是在 GitHub 的 Windows 构建机上安装，不需要装到你的 Windows 电脑。

## Linux 开发环境

Linux 上可以用于开发和调试界面：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python auto_clicker.py
```

Linux 桌面环境下，截图和鼠标控制通常需要 X11 会话。Wayland 环境可能会限制屏幕截图或模拟点击。

## 使用流程

1. 点击“选择点击区域”，在屏幕上拖拽出允许点击的范围。
2. 选择模式：
   - “区域随机点击”：在框选区域内随机点击。
   - “目标识别点击”：在框选区域内查找模板图，匹配成功后点击目标中心。
3. 目标识别模式下，点击“框选目标模板”直接从屏幕截取模板，或点击“加载模板图片”选择本地图片。
4. 设置运行时长、最小/最大点击间隔、匹配阈值。
5. 需要让鼠标移动更像人工操作时，勾选“鼠标按曲线轨迹移动到点击点”，并设置“曲线移动耗时”。需要每段移动快慢不固定时，勾选“移动速度随机变化”。需要点击前轻微等待或模拟按住鼠标时，设置点击前停顿和按压时间范围。
6. 需要先校准时，勾选“测试模式：只移动鼠标，不点击”。
7. 点击“启动”，需要暂停时点击“暂停”或按 `F8`。

## 安全停止

- 按 `F9` 立即停止。
- `pyautogui` 的安全角默认开启：把鼠标快速移到屏幕左上角会触发异常并停止点击。

## Windows 注意事项

- 优先使用窗口化或无边框窗口模式，独占全屏可能导致截图或点击不可用。
- 如果点击位置有偏移，先把 Windows 显示缩放临时调到 100% 再测试。
- 如果热键不生效，先点击工具窗口一次，或用管理员身份运行。
