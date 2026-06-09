# Oracle request package

Status: **unavailable**
Reason: bridge unreachable at http://localhost:8765: URLError(ConnectionRefusedError(10061, 'Nenhuma conexão pôde ser feita porque a máquina de destino as recusou ativamente', None, 10061, None))

## How to use

1. Open the destination (e.g. ChatGPT desktop, web).
2. Paste the contents of `prompt.md`.
3. Drag the three images from `images/` into the conversation.
4. Optionally attach `context.json` with the geometry stats.
5. Expect the reply to follow `expected_schema.json`
   (`visual_findings.v1`).

## Why this package exists

The automated oracle path could not deliver visual judgment in
this run (status above). To keep the validator honest, the request
was written to disk so a human reviewer can stand in for the oracle.

Once the bridge gains real image-attachment support OR a Vision API
is plugged in, this package is no longer needed for that fixture.
