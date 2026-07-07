@echo off
REM ============================================================
REM   RODE COMO ADMINISTRADOR
REM   (botao direito neste arquivo -> "Executar como administrador")
REM   Libera a porta 8783 pra acessar a vitrine pelo CELULAR
REM   (celular tem que estar na MESMA rede Wi-Fi do desktop)
REM ============================================================
netsh advfirewall firewall delete rule name="vitrine-8783" >nul 2>&1
netsh advfirewall firewall add rule name="vitrine-8783" dir=in action=allow protocol=TCP localport=8783
echo.
echo Porta 8783 liberada no firewall.
echo.
echo No celular, abra no navegador:
echo    http://192.168.15.4:8783/
echo.
echo (Se nao abrir, o IP pode ter mudado: rode "ipconfig" e
echo  procure o "IPv4" que comeca com 192.168.15)
echo.
pause
