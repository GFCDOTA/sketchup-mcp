# Fluxograma — RAG do Ateliê 74 (chat + memória vetorial)

> Renderiza direto no GitHub (bloco ```mermaid). Ver ADR-0002 pro texto corrido.
> Baseado no diagrama que o Felipe desenhou em texto (Knowledge Base → chunks →
> embedding → Vector DB → Retriever → Agent) — este documenta o que ficou
> implementado de fato, com os módulos reais do repo.

```mermaid
flowchart TD
  subgraph fontes["Fontes de conhecimento"]
    F1["felipe_style_dna.md<br/>(gosto — 16 regras carregadas)"]
    F2["resumos por cômodo<br/>(interior-designer, 8 registros)"]
    F3["felipe_visual_judge_rules.json<br/>(regra técnica)"]
    F4["skill interior-project-audit<br/>(12 gates)"]
    F5["HANDOFF.md / ITERATIONS.md<br/>(decisão anterior do projeto)"]
    F6["PDFs de arquitetura/norma/ergonomia<br/>(AINDA NÃO EXISTE — só o extrator pronto)"]
  end

  F1 -->|save_preference| CHUNK
  F2 -->|save_preference| CHUNK
  F3 -->|index_file| CHUNK
  F4 -->|index_file| CHUNK
  F5 -->|index_file| CHUNK
  F6 -.->|"tools/pdf_knowledge/ingest_pdfs.py<br/>(pypdf, pronto, sem input real)"| JSONL[pdf_pages.jsonl]
  JSONL -.->|index_jsonl, não rodado ainda| CHUNK

  CHUNK["chunk<br/>(1200 chars / 150 overlap)"] --> EMBED
  EMBED["embedding<br/>Ollama nomic-embed-text (768d)"] --> VDB

  subgraph vdb["Qdrant — vector DB (local, Docker)"]
    COL1[("felipe_preferences<br/>gosto pessoal")]
    COL2[("knowledge_base<br/>regra técnica + decisão")]
    COL3[("rag_chunks<br/>RAG de fidelidade — outro domínio, ADR-0001")]
  end
  VDB --> COL1
  VDB --> COL2

  USER(["Felipe digita no chat<br/>'como melhorar esse banheiro?'"]) --> RETR

  RETR["Retriever<br/>rag_chat.search_preferences()<br/>+ knowledge_ingest.search_knowledge()"]
  COL1 -->|busca por similaridade| RETR
  COL2 -->|busca por similaridade| RETR

  RETR -->|"contexto: preferências relevantes<br/>+ conhecimento técnico relevante"| PROMPT
  PROMPT["Prompt montado<br/>(SYSTEM_PROMPT + contexto + histórico recente)"] --> AGENT

  AGENT["Agent conversa<br/>Ollama llama3.1:8b<br/>(NÃO o modelo 'interior-designer' — esse é fixo em JSON de layout)"]
  AGENT --> REPLY["Resposta ao Felipe<br/>(cita fonte quando usa regra/decisão)"]
  REPLY --> UI["Ateliê 74 — chat na página"]

  UI -->|"clique '💾 salvar na memória'"| SAVE["POST /api/chat/save"]
  SAVE -->|embed + upsert| COL1

  style F6 stroke-dasharray: 5 5
  style JSONL stroke-dasharray: 5 5
  style COL3 fill:#2a2a2a,color:#999
```

## Legenda

- **Linha sólida** = caminho implementado e testado ponta a ponta nesta sessão.
- **Linha tracejada** = peça que existe no código mas ainda não tem dado real
  fluindo (falta o Felipe fornecer PDFs em `references/pdfs/`).
- **`rag_chunks`** (cinza) é um domínio separado, do pipeline de fidelidade
  PDF→SKP (ADR-0001) — não é tocado por este fluxo, só compartilha a mesma
  instância Qdrant.
