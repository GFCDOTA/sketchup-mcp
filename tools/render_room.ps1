param(
  [string]$Eye="340,874,62",
  [string]$Target="250,784,30",
  [string]$Fov="60",
  [string]$Out="planta_74_vray_sala_eye.png",
  [double]$Iso=100, [double]$Fnum=7, [double]$Shutter=160, [double]$Sky=0.3,
  [int]$Width=1500, [int]$Height=1000,
  [string]$Fill=""
)
$ErrorActionPreference="Stop"
$su="C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
$rb="E:\Claude\sketchup-mcp-mobiliar\tools\vray_export.rb"
$base="E:\Claude\sketchup-mcp-mobiliar\artifacts\planta_74\furnished\planta_74_furnished.skp"
$scratch="E:\Claude\sketchup-mcp-mobiliar\.claude\scratch"
$fdir="E:\Claude\sketchup-mcp-mobiliar\artifacts\planta_74\furnished"
$py='E:\Claude\sketchup-mcp\.venv\Scripts\python.exe'
$vray="C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe"
$tex="E:\Claude\sketchup-mcp-mobiliar\assets\textures\procedural"

$baseHash=(Get-FileHash $base -Algorithm SHA256).Hash
$copy="$scratch\vray_room_copy.skp"; Copy-Item $base $copy -Force
$vrs="$scratch\room.vrscene"; $log="$scratch\room_log.txt"
Remove-Item $vrs,$log -ErrorAction SilentlyContinue

$env:VRSCENE_OUT=($vrs -replace '\\','/'); $env:VRAY_LOG=($log -replace '\\','/')
$env:VRAY_EYE=$Eye; $env:VRAY_TARGET=$Target; $env:VRAY_FOV=$Fov; $env:VRAY_TEX_DIR=$tex
$p=Start-Process -FilePath $su -ArgumentList "`"$copy`"","-RubyStartup","`"$rb`"" -PassThru
$deadline=(Get-Date).AddSeconds(75)
while((Get-Date) -lt $deadline){ if(Test-Path $log){ Start-Sleep 2; break }; Start-Sleep 2 }
Start-Sleep 1; taskkill /F /IM SketchUp.exe 2>$null | Out-Null; Start-Sleep 1
if(-not (Test-Path $vrs)){ "EXPORT FAIL"; if(Test-Path $log){ Get-Content $log }; exit 1 }
Copy-Item $vrs "$scratch\room_raw.vrscene" -Force   # raw pristine (so camera) p/ tune rapido sem SU
"vrscene: $((Get-Item $vrs).Length)b"; Get-Content $log | Select-Object -First 6

$tweakArgs = @($vrs,"--iso",$Iso,"--fnum",$Fnum,"--shutter",$Shutter,"--sky",$Sky,"--width",$Width,"--height",$Height,"--materials")
if($Fill -ne ""){ $tweakArgs += @("--fill",$Fill) }
& $py E:\Claude\sketchup-mcp-mobiliar\tools\tweak_vrscene.py @tweakArgs | Out-Null
$img="$fdir\$Out"; Remove-Item $img -ErrorAction SilentlyContinue
(Start-Process -FilePath $vray -ArgumentList "-sceneFile=`"$vrs`"","-imgFile=`"$img`"","-display=0","-autoClose=1" -PassThru -NoNewWindow).WaitForExit(200000) | Out-Null

$baseHash2=(Get-FileHash $base -Algorithm SHA256).Hash
if($baseHash -ne $baseHash2){ "!! BASE MUTATED !!"; exit 2 }
if(Test-Path $img){ "OK $Out $((Get-Item $img).Length)b base_intact=True" } else { "RENDER FAIL"; exit 3 }
