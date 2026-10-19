// Cliente MCP em Node (SDK oficial @modelcontextprotocol/sdk 1.29.0, o mesmo que clientes Node usam) falando com o servidor sketchup.
// Mede: lista de tools, su_status.server_job (Job Object em que o servidor ficou), e o efeito de FECHAR o cliente sobre um SketchUp aberto por su_open.
// uso: node node_client.mjs <repo> <acao> [skp]      acao = status | open
const SDK = "file:///E:/Claude/apps/system-design-specialist-lab/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/";
const { Client } = await import(SDK + "index.js");
const { StdioClientTransport } = await import(SDK + "stdio.js");
const [, , repo, action, skp] = process.argv;
const py = "E:/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe";
const transport = new StdioClientTransport({
  command: py, args: ["-m", "tools.mcp_server.server"], cwd: repo,
  env: { ...process.env, PYTHONPATH: repo, PT_TO_M: "0.0259" }, stderr: "pipe",
});
const client = new Client({ name: "p3b-node-client", version: "1.0.0" }, { capabilities: {} });
const t0 = Date.now();
await client.connect(transport);
const connectMs = Date.now() - t0;
const tools = (await client.listTools()).tools.map((t) => t.name);
const parse = (r) => { try { return JSON.parse(r.content[0].text); } catch { return { raw: r.content?.[0]?.text }; } };
const out = { client: "node", sdk: "1.29.0", node: process.version, connect_ms: connectMs, tool_count: tools.length, tools };
const st = parse(await client.callTool({ name: "su_status", arguments: {} }));
out.su_status = { server_job: st.server_job, instances: st.instances, mode_default: st.mode_default, proof_state: st.proof_state };
if (action === "open") {
  const r = parse(await client.callTool({ name: "su_open", arguments: { skp_path: skp } }, undefined, { timeout: 120000 }));
  out.su_open = { status: r.status, pid: r.pid, reason: r.reason };
}
await client.close();                         // fecha o stdin/encerra o servidor
console.log(JSON.stringify(out));
process.exit(0);
