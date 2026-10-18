param(
  [string]$Fill="", [string]$Out="planta_74_vray_sala_tune.png",
  [double]$Iso=100, [double]$Fnum=7, [double]$Shutter=160, [double]$Sky=0.3,
  [string]$FillColor="1.0,0.8,0.55",
  [int]$Width=1500, [int]$Height=1000
)
$ErrorActionPreference="Stop"
$scratch="E:\Claude\sketchup-mcp-mobiliar\.claude\scratch"
$fdir="E:\Claude\sketchup-mcp-mobiliar\artifacts\planta_74\furnished"
$py='E:\Claude\sketchup-mcp\.venv\Scripts\python.exe'
$vray="C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe"
$raw="$scratch\room_raw.vrscene"
if(-not (Test-Path $raw)){ "NO room_raw.vrscene (rode render_room.ps1 antes)"; exit 1 }
$tuned="$scratch\room_tuned.vrscene"; Copy-Item $raw $tuned -Force
$a=@($tuned,"--iso",$Iso,"--fnum",$Fnum,"--shutter",$Shutter,"--sky",$Sky,"--width",$Width,"--height",$Height,"--materials","--fill-color",$FillColor)
if($Fill -ne ""){ $a += @("--fill",$Fill) }
& $py E:\Claude\sketchup-mcp-mobiliar\tools\tweak_vrscene.py @a
$img="$fdir\$Out"; Remove-Item $img -ErrorAction SilentlyContinue
(Start-Process -FilePath $vray -ArgumentList "-sceneFile=`"$tuned`"","-imgFile=`"$img`"","-display=0","-autoClose=1" -PassThru -NoNewWindow).WaitForExit(200000) | Out-Null
if(Test-Path $img){ "OK $Out $((Get-Item $img).Length)b" } else { "RENDER FAIL" }
