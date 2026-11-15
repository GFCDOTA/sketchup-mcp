# FP-060 MT-01 — fronteira de arquivos do sandbox AppContainer, medida depois de duas pré-revisões do Codex

Evidência datada (2026-11-15). Refs #606. Medida no commit `1eaa0fc` (árvore limpa), Windows 11, Python 3.12.13.

## O que é

Duas execuções **reais** do Codex CLI, pelo caminho de produção do `codex_reviewer` (testes no AppContainer, **sem publicar
nada**), revisaram o #617. Cada uma devolveu `REQUEST_CHANGES`; cada achado foi verificado antes de ser corrigido.

| Passada | HEAD revisado | Achados | Verificação | Resposta |
|---|---|---|---|---|
| 1 (`codex_prereview_617_verdict.json`) | `3b9efef` | HIGH: a sonda prova a negação de **um** canário, não que nenhum arquivo fora do workspace é legível | medido: arquivo concedido a `ALL APPLICATION PACKAGES`, binários do Windows e Program Files são legíveis | o **contrato foi reduzido** ao que é verdade (não se alargou o sandbox) e travado com um teste |
| 2 (`codex_prereview_617_verdict_2.json`) | `ac717cb` | HIGH: a cópia recusa reparse points mas aceita **hard links**, e um hard link para um arquivo privado seria copiado para dentro do sandbox | reproduzido por teste: o teste passou a falhar sem a guarda | `_copy_tree` recusa qualquer arquivo com mais de um link (usa `lstat`: `DirEntry.stat()` devolve `st_nlink = 0` no Windows) |
| 2 | `ac717cb` | MEDIUM: a minha medição tratava alvo ausente como "permitida" e qualquer falha de leitura, inclusive arquivo inexistente, como "negada" | reproduzido: era verdade | o script registra cada tentativa explicitamente e **recusa** evidência incompleta; o teste de fronteira exige `PermissionError` e há um controle negativo para "arquivo inexistente" |

A passada 2 também reportou que os testes do coordenador "não ficaram verdes" (23 falhas, 42 erros): são os testes do próprio laboratório
rodando dentro do sandbox. A causa é o `PATH` do sandbox ser só `System32`: o `git` não é encontrado (`WinError 2`, 52 casos) e outros
recursos fora do workspace são negados, por desenho. É um **limite documentado**, não um defeito do sandbox (ver abaixo).

## Resultado da medição (`evidence.json`)

Cada alvo tem uma tentativa registrada pelo próprio teste dentro do sandbox (`RESULT {...}`); o script recusaria a evidência se faltasse
uma, se houvesse timeout ou erro de coleta, ou se algum alvo fosse inexistente ou falhasse por outra causa que não permissão.

| Alvo | Leitura dentro do sandbox |
|---|---|
| arquivo comum do usuário (sem concessão a AppContainer) | **NEGADA** (`PermissionError`) |
| arquivo do usuário com ACL concedendo `ALL APPLICATION PACKAGES` | **PERMITIDA** |
| `C:\Windows\System32\cmd.exe` | **PERMITIDA** |
| `C:\Windows\System32\drivers\etc\hosts` | **PERMITIDA** |
| `C:\Program Files\GitHub CLI\gh.exe` | **PERMITIDA** |

O isolamento foi provado na execução (token AppContainer com zero capacidades e canário negado).

## O que mudou no código

- o docstring de `sandboxed_tests.py`, o do laboratório e seus limites e os READMEs de evidência dizem que o sandbox **nega o que
  a ACL não concede a um AppContainer** (arquivos, pastas e credenciais do usuário), mas **lê o que a ACL abre a todo
  AppContainer**; `proves_isolation` prova o token e **um** canário, não confinamento geral de arquivos;
- um teste do Windows trava a fronteira medida (negado / legível / legível) com `PermissionError`, e um controle negativo prova que um
  arquivo inexistente **não** passa como negado;
- `_copy_tree` recusa **hard links**, com teste unitário e teste que roda o sandbox.

## O que NÃO é

- **Não confina o código testado em todo o sistema de arquivos.** Segredo num arquivo legível por todo AppContainer (por exemplo, em
  `C:\ProgramData` com ACL aberta) é legível pelo código testado, e a saída dele vai para os logs que o processo herda. O rótulo
  `os_sandbox` **não é garantia** de que um arquivo específico não é lido: confira a ACL dele.
- **Testes que dependem de `git` ou de outra ferramenta no `PATH` não rodam no sandbox** (o `PATH` é só `System32`). Um diff cujos testes
  selecionados incluam o laboratório closed-loop recebe `tests_passed=False` e não é aprovado automaticamente.
- Não mediu todos os arquivos do sistema: foram 5 alvos representativos. É medição desta versão do Windows, não prova formal.
- **Duas pré-revisões do Codex não são a revisão independente do PR**: são a pré-revisão adversarial do ciclo. A revisão independente
  do #617 continua pendente.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_sandboxed_tests.py -q -k "documented_file_boundary or missing_file or hard_link"
PYTHONPATH=. $PY artifacts/review/fp060/m1_closed_loop/2026-11-15_fs_boundary/measure_fs_boundary.py <dir novo>   # exige commit limpo
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `evidence.json` | commit sob medição, prova do sandbox e o resultado explícito de cada uma das 5 tentativas |
| `measure_fs_boundary.py` | o script da medição (estrito: recusa evidência incompleta) |
| `codex_prereview_617_verdict.json` | parecer bruto da passada 1 (`REQUEST_CHANGES`, HIGH) |
| `codex_prereview_617_verdict_2.json` | parecer bruto da passada 2 (`REQUEST_CHANGES`: HIGH hard link, MEDIUM medição) |
