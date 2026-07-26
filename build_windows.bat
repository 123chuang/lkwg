@echo off
setlocal

if not exist .venv (
    py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --hidden-import pynput ^
    --name KeyMouseSignalSender ^
    auto_clicker.py

echo.
echo Build finished. EXE path:
echo dist\KeyMouseSignalSender.exe
