@echo off
chcp 65001 >nul
python app.py
if not defined in_subprocess (cmd /k set in_subprocess=y ^& python app.py) else (pause)
pause