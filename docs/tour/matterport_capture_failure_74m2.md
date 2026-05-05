# Matterport Capture — Persistence Method Audit

> Why a single Matterport tour produced exactly **one** persisted image
> file in the repo (`references/matterport_74m2/01_living_room_official.jpg`)
> instead of the eight viewpoints requested. Documents the exact methods
> tried and the exact technical block, so the next session knows which
> fallback to use first.

## Tour reference

- URL: https://discover.matterport.com/space/rLoqyVDHfzC
- Title: **Living Grand Wish Jardim - 74m²**
- Capture: Matterport Pro2 (2023-08-23 timestamp on photo filenames)
- Public viewer: 27 scan positions, 36 photos in the gallery, dollhouse
  + top-down + FPV all functional
- Host: PIPERZ HOST (publicly listed)
- Asset CDN: `cdn-2.matterport.com/apifs/models/rLoqyVDHfzC/images/...`

## Methods attempted

### A. Chrome MCP `screenshot` action with `save_to_disk: true`

```
mcp__Claude_in_Chrome__computer
  action: screenshot
  save_to_disk: true
  tabId: <tour tab>
```

Tool returned `Successfully captured screenshot (1568x744, jpeg) - ID: ss_<uuid>`
on every call. **No file path returned in the tool result.** Search for
the file in the obvious places came up empty:

```bash
$ find /tmp $env:TEMP $env:USERPROFILE/Downloads $env:USERPROFILE/Pictures \
       $env:LOCALAPPDATA/Anthropic $env:APPDATA/claude \
       -mmin -3 -size +10k -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) \
       2>/dev/null
# (empty)
```

**Block confirmed:** `save_to_disk: true` on this tool installation
returns the image bytes inline in the tool response (visible in the
conversation transcript as `output_image`) but does NOT write a file
the local shell can read. The "saved path" promised by the tool
description is not surfaced.

### B. `cdn-2.matterport.com` direct curl with stripped URL

```bash
$ curl -s -o tmp.jpg -w "HTTP %{http_code}\n" \
  "https://cdn-2.matterport.com/apifs/models/rLoqyVDHfzC/images/.../GFhsm6jpyHB-Living_Room.jpg"
HTTP 401
```

Matterport's CDN requires the signed query string the in-browser viewer
appends. Stripping the auth token returns 401 on every asset.

### C. JavaScript `fetch` + blob download via `<a download>`

In-browser:

```javascript
const r = await fetch(img.src);   // signed URL inherited from page
const blob = await r.blob();
const a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = 'matterport_test_001.jpg';
document.body.appendChild(a);
a.click();
```

**First call: SUCCESS.** File appeared in `~/Downloads/matterport_test_001.jpg`,
640×360 JPEG, valid image of the living room. Persisted.

**Subsequent calls: BLOCKED.** A loop over the remaining 35 asset URLs
inside a single JS execution returned `{ ok: true, size: ... }` for
every fetch, but only **the first one** ever materialized as a file.
The remaining 35 downloads were silently dropped by Chrome.

The same pattern repeated when the loop was re-shaped as
`browser_batch` of `[click(neutral) → js download → wait 2s → click → js
download → ...]`. The JS reported `{ ok: true, size: 61194 }` for image
#2 (different bytes than #1 — fetch did succeed) and similar for #3,
but `~/Downloads/` ended up still containing only `matterport_test_001.jpg`.

This is the standard Chrome **"automatic downloads"** content-setting
block. Chromium docs:
https://support.google.com/chrome/answer/2511403 — "Sites can ask to
automatically download multiple files" defaults to "ask first", and
when the JS `<a.click()>` is not preceded by a real user-gesture, the
2nd onward downloads are dropped silently (no permission popup either,
because the gesture-token from the first click was already consumed).

### D. PowerShell GDI screenshot of the Chrome window

Not attempted in this session — it would capture whatever Chrome happens
to be displaying in the foreground, which is a viable path **if a human
is at the keyboard** and can position the window. From inside an
agentic Bash/PowerShell context with no guarantee Chrome is foreground,
the screenshot would be unreliable. Listed here as the next-fallback
option for the next session.

## What was actually persisted

```
references/matterport_74m2/01_living_room_official.jpg  640x360  37 KB
```

This single file is the official Matterport-curated Living Room photo
(filename `GFhsm6jpyHB-Living_Room.jpg` on the CDN). It shows the sofá
branco in L, with the porta-balcão glass to the right and the
TV-marble panel ahead — directly comparable to the SKP top render's
"SALA DE ESTAR" room. **It is sufficient evidence for V1** (sala is
clearly rectangular, with no diagonal cut).

## Where the rest of the evidence is

The Chrome MCP screenshot inline data — even though not written to
disk — IS visible to the user in the conversation transcript that
this session produced. Specifically:

- Dollhouse view of the whole apartment (full layout context)
- Top-down floorplan view
- FPV from the entry point (living + dining + glass to terraço)
- FPV from the A.S. corridor (kitchen + dining)
- FPV showing the "Lavabo" mattertag with the porta-balcão glass behind
- Photos 3, 5, 6, 10, 15, 23 from the gallery (clicked through)

These screenshots prove V1 / V4 / V5 verdicts but cannot be
re-attached to the repo without a working capture method.

## Gallery URL inventory (for whoever solves this next)

The Matterport CDN exposes 36 unique paths under
`/apifs/models/rLoqyVDHfzC/images/<scanId>/<filename>` and a few under
`/models/<modelId>/assets/render/`. Of those, **12 images are 640×360**
(viewer-resolution photos suitable for evidence) and 24 are 213×120
thumbnails. JS-side enumeration confirmed the count and stored the
signed URLs in `window.__mp_dl_queue` during the session. Filenames
include:

```
GFhsm6jpyHB-Living_Room.jpg              <- already persisted
UdHzUwjCQ6K-Dollhouse_View.jpg
animation-0001-480.jpg                   (rotating dollhouse animation, 480p)
08.23.2023_<HH.MM.SS>.jpg                <- the FPV scan thumbnails (24)
```

The auth-token query string ROTATES per session, so re-running the JS
extraction is required each time.

## Recommended next-session method

Two paths, in order of preference:

1. **User flips the Chrome content setting** before the agent session:
   `chrome://settings/content/automaticDownloads` → "Sites can ask to
   automatically download multiple files" → toggle on for
   `https://discover.matterport.com`. Then JS `<a download>` loop
   completes 36/36 instead of 1/36. All assets land in
   `~/Downloads/mp_<idx>_<filename>` and a single `mv` populates
   `references/matterport_74m2/`.

2. **User captures manually** the 8 viewpoints listed in
   `docs/tour/matterport_visual_findings_74m2.md` "Manual screenshots
   needed" section (revised) and drops them into
   `references/matterport_74m2/` with the requested filenames.

Either path produces durable evidence that survives session end.

## Why this matters

V1 (SALA DE ESTAR diagonal bite) is already evidenced enough to start a
technical fix on `tools/rooms_from_seeds.py` — the persisted living
room photo proves the sala is rectangular. **V2 (TERRACO SOCIAL
pentagonal)** still wants the wood-deck top-down crop and a
terraço-interior FPV before the same patch can be confidently extended
to it. Until the multi-download block is resolved, V2's verdict stays
"likely contradicted, not definitive".
