# FP-060 MT-04 — testes do coordenador do `codex_reviewer` dentro de um AppContainer provado

Evidência datada (2026-11-15) de uma execução **real** de `codex_reviewer.run_coordinator_tests` sobre este repositório, no
commit `32947e0` (árvore limpa), Windows 11, Python 3.12.13. Refs #623 e #606.

## O que é

Até aqui `run_coordinator_tests` era fail-closed e nunca executava nada: todo parecer chegava com
`tests_skipped_no_sandbox` e `tests_passed=None`, então um APPROVE do Codex nunca podia ser publicado. Agora ele roda os testes
selecionados do diff através de `sandboxed_tests.run_pytest` (AppContainer sem capacidades, Job Object) e só devolve
`isolation == "os_sandbox"` quando o **token do processo** lido do kernel (AppContainer, zero capacidades) **e** um **canário**
fora do workspace (que a sonda não lê nem escreve) passaram **na mesma execução**. Qualquer outra situação — fora do Windows,
sandbox que não sobe, sonda reprovada, prova ausente — continua devolvendo `tests_skipped_no_sandbox` com `tests_passed=None`, e
nada roda fora do sandbox. A guarda de publicação de APPROVE em `review_pr` não mudou: exige exatamente o rótulo `os_sandbox`.

## Resultado (`evidence.json`)

| Caso | Testes selecionados | Isolamento | Resultado | Tempo |
|---|---|---|---|---|
| diff que toca `outbox_publisher.py` | `tests/test_outbox_publisher.py` | `os_sandbox`, provado | **17 passed**, `tests_passed = true` | 25 s |
| diff que toca `event_store.py` | `tests/test_event_store.py` | `os_sandbox`, provado | **7 failed, 74 passed**, `tests_passed = false` | 29 s |

Nos dois casos: `is_appcontainer = true`, `capabilities = 0`, canário negado para leitura e escrita, workspace removido, 27
distribuições no runtime (as dependências do projeto, lidas do `pyproject.toml` do coordenador).

## O limite que isto expõe

As 7 falhas do segundo caso são todas de `TestRealProcesses`: testes que sobem processos filhos com `multiprocessing` e usam
pipes nomeados no namespace global, que um AppContainer não pode criar (`WinError 5`). O sandbox está fazendo o que foi
desenhado para fazer, mas o efeito é que **um diff cujos testes selecionados incluam esses testes recebe `tests_passed=False` e
não é aprovado automaticamente**: isso bloqueia APPROVE (fail-closed), e a decisão passa para um humano. Pular ou reescrever
esses testes para "ficar verde" seria alterar a prova, então não foi feito.

## O que foi preciso para os testes reais rodarem no sandbox

- as dependências do projeto no runtime, lidas do pyproject do **coordenador**, nunca do código sob revisão;
- uma lista de entradas de nível superior que não são código e ficam de fora da cópia (`artifacts/` tem 351 dos 429 MB
  rastreados);
- um shim de `os.mkdir` no bootstrap do sandbox: o Python 3.12 no Windows transforma `mkdir(mode=0o700)` em uma ACL só do
  usuário, que não inclui o perfil do AppContainer, e o processo isolado perdia acesso aos diretórios que ele mesmo criava
  (`tmp_path` do pytest e `tempfile`); sem o `mode`, o diretório herda a ACL do workspace;
- `--basetemp` dentro do workspace;
- uma guarda que recusa uma raiz de sandbox dentro da árvore copiada (a primeira versão dos testes copiava o workspace para
  dentro de si mesmo e travou).

## O que NÃO é

- **Não é o M2 completo.** Não há Codex, nem GitHub, nem publicação nesta evidência: só a camada de execução dos testes.
- **O rótulo `os_sandbox` não é confinamento geral de arquivos.** O sandbox nega o que a ACL não concede a um AppContainer
  (arquivos e credenciais do usuário) e a rede, mas o código testado lê o que a ACL abre a todo AppContainer (Windows,
  Program Files, qualquer arquivo concedido a `ALL APPLICATION PACKAGES`); medido em
  `../../m1_closed_loop/2026-11-15_fs_boundary/` depois de uma pré-revisão do Codex apontar isso no #617. Ele é a condição para
  publicar um APPROVE, não uma garantia de que um arquivo específico não foi lido.
- **Não garante integridade do resultado**: o código testado roda no mesmo processo do pytest e controla o exit code; o
  sandbox restringe o que ele alcança, não o que ele declara.
- **Não há limite de CPU, memória ou disco** dentro do workspace; o timeout é do coordenador (10 min).
- **Perfil e workspace ficam órfãos** se o coordenador morrer no meio dos testes (sem reaper); uma interrupção forçada
  durante o desenvolvimento deixou 2 perfis, removidos à mão.
- Medição de uma execução por caso: é demonstração, não distribuição de tempos. O custo depende do cache do disco (a cópia das
  dependências levou 58 s a frio em C: e 0,5 s a quente em E:).

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_codex_reviewer.py tests/test_sandboxed_tests.py -q
PYTHONPATH=. $PY artifacts/review/fp060/mt04_codex_reviewer_sandbox/2026-11-15/mt04_real_run.py <dir novo>   # exige commit limpo
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `evidence.json` | commit sob prova e, por caso: arquivos alterados, testes selecionados, isolamento, `tests_passed`, última linha do pytest, falhas, fatos do sandbox |
| `mt04_real_run.py` | o script que gerou a evidência (estado de governança num diretório de saída novo, nunca em `runs/governance` de produção) |
