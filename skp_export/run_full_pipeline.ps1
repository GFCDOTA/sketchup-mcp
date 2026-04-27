# run_full_pipeline.ps1
# Pipeline V6.2 completa: build .skp + screenshot topview/iso + side-by-side PDF
# Pre-condicao: welcome dialog do SU 2026 ja dismissado uma vez (login_session.dat presente).
# Uso: powershell -File run_full_pipeline.ps1

$ErrorActionPreference = "Continue"
$SU = "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
$TEMPLATE = "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\Temp01a - Simple.skp"
$HEADLESS = "E:\Claude\sketchup-mcp\skp_export\headless_consume_and_quit.rb"
$SCREENSHOT = "E:\Claude\sketchup-mcp\skp_export\screenshot_consensus.rb"
$RUN_DIR = "E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74"

$env:CONSUME_SCALE_OVERRIDE = "0.0135"
Write-Output "[pipeline] CONSUME_SCALE_OVERRIDE = $env:CONSUME_SCALE_OVERRIDE"

# Cleanup
Get-Process -Name SketchUp,sketchup_webhelper -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Remove-Item "$RUN_DIR\generated_from_consensus.skp","$RUN_DIR\headless_run.log","$RUN_DIR\skp_topview_v62.png","$RUN_DIR\skp_iso_v62.png","$RUN_DIR\screenshot_run.log" -ErrorAction SilentlyContinue

# Step 1 — headless build
Write-Output "[pipeline] Step 1/3: headless build via -RubyStartup"
$proc = Start-Process -FilePath $SU -ArgumentList @("-RubyStartup", "`"$HEADLESS`"", "`"$TEMPLATE`"") -PassThru -WindowStyle Minimized
$out = "$RUN_DIR\generated_from_consensus.skp"
for ($i = 1; $i -le 30; $i++) {
  Start-Sleep -Seconds 2
  if ((Test-Path $out) -and ((Get-Item $out).Length -gt 1000)) {
    Write-Output "[pipeline]   .skp gerado em ~$($i*2)s ($((Get-Item $out).Length) bytes)"
    Start-Sleep -Seconds 4
    break
  }
}
Get-Process -Name SketchUp,sketchup_webhelper -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

if (-not (Test-Path $out)) {
  Write-Output "[pipeline] FAIL: .skp not generated. Headless log:"
  Get-Content "$RUN_DIR\headless_run.log" -ErrorAction SilentlyContinue
  exit 1
}

Write-Output ""
Write-Output "[pipeline] Headless log:"
Get-Content "$RUN_DIR\headless_run.log" -ErrorAction SilentlyContinue

# Step 2 — screenshot topview + iso
Write-Output ""
Write-Output "[pipeline] Step 2/3: screenshot topview + iso"
$proc2 = Start-Process -FilePath $SU -ArgumentList @("-RubyStartup", "`"$SCREENSHOT`"", "`"$TEMPLATE`"") -PassThru -WindowStyle Minimized
$top = "$RUN_DIR\skp_topview_v62.png"
$iso = "$RUN_DIR\skp_iso_v62.png"
for ($i = 1; $i -le 30; $i++) {
  Start-Sleep -Seconds 2
  if ((Test-Path $top) -and (Test-Path $iso) -and ((Get-Item $top).Length -gt 5000) -and ((Get-Item $iso).Length -gt 5000)) {
    Write-Output "[pipeline]   PNGs prontos em ~$($i*2)s (top=$((Get-Item $top).Length) iso=$((Get-Item $iso).Length))"
    Start-Sleep -Seconds 3
    break
  }
}
Get-Process -Name SketchUp,sketchup_webhelper -ErrorAction SilentlyContinue | Stop-Process -Force

# Step 3 — side-by-side via Python+PIL
Write-Output ""
Write-Output "[pipeline] Step 3/3: side-by-side PDF + topview + iso"
& "E:/Python312/python.exe" -c @"
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

PDF = 'E:/Claude/sketchup-mcp-exp-dedup/planta_74.pdf'
TOP = '$top'.replace(chr(92), '/')
ISO = '$iso'.replace(chr(92), '/')
OUT = 'E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/pdf_vs_skp_v62_SCALE_0_0135.png'

pdf = pdfium.PdfDocument(PDF)
pdf_img = pdf[0].render(scale=2.0).to_pil().convert('RGB')
top_img = Image.open(TOP).convert('RGB')
iso_img = Image.open(ISO).convert('RGB')

target_h = 700
def resize(im, h):
    w, hh = im.size
    return im.resize((int(w * h / hh), h), Image.LANCZOS)

pdf_img = resize(pdf_img, target_h)
top_img = resize(top_img, target_h)
iso_img = resize(iso_img, target_h)

pad = 10
total_w = pdf_img.size[0] + top_img.size[0] + iso_img.size[0] + pad * 4
total_h = target_h + 50
canvas = Image.new('RGB', (total_w, total_h), 'white')
canvas.paste(pdf_img, (pad, 40))
canvas.paste(top_img, (pad * 2 + pdf_img.size[0], 40))
canvas.paste(iso_img, (pad * 3 + pdf_img.size[0] + top_img.size[0], 40))

draw = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype('arial.ttf', 20)
except: font = None
draw.text((pad, 10), 'PDF planta_74 (74,93m²)', fill='black', font=font)
draw.text((pad * 2 + pdf_img.size[0], 10), 'SKP TOP V6.2 SCALE=0.0135', fill='black', font=font)
draw.text((pad * 3 + pdf_img.size[0] + top_img.size[0], 10), 'SKP ISO V6.2 SCALE=0.0135', fill='black', font=font)
canvas.save(OUT, 'PNG', optimize=True)

print(f'side-by-side: {canvas.size[0]}x{canvas.size[1]} -> {OUT}')
"@

Write-Output ""
Write-Output "[pipeline] DONE"
Write-Output "  .skp:           $out"
Write-Output "  topview:        $top"
Write-Output "  iso:            $iso"
Write-Output "  side-by-side:   $RUN_DIR\pdf_vs_skp_v62_SCALE_0_0135.png"
