@echo off
REM Sobe a VITRINE sketchup-mcp (:8783) num container Docker que reinicia sozinho (sobrevive reboot).
REM Roda de qualquer lugar: ele entra na pasta do projeto sozinho.
cd /d "%~dp0\..\.."
echo Recriando o container da vitrine...
docker rm -f sketchup-grafo >nul 2>&1
docker build -f tools/vitrine/Dockerfile.grafo -t sketchup-grafo . || goto :err
docker run -d --name sketchup-grafo --restart unless-stopped -p 8783:8783 -v E:/Claude:/workspace -w /workspace/apps/sketchup-mcp sketchup-grafo || goto :err
echo.
echo Vitrine no ar: http://localhost:8783/
goto :eof
:err
echo ERRO ao subir a vitrine. Docker Desktop esta rodando?
pause
