@echo off
title ¡¾·şÎñÆ÷-ÇëÎğ¹Ø±Õ¡¿ServerChanPush2TelegramBot 
cd /d %~dp0
:start
waitress-serve --threads=10 --listen=*:5000 ServerChanPush2TelegramBot:app
goto start