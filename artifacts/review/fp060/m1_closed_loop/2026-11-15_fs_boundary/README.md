# FP-060 MT-01 — fronteira de arquivos do sandbox AppContainer, medida depois da pré-revisão do Codex

Evidência datada (2026-11-15). Refs #606. Medida no commit `5ac5dfd` (árvore limpa), Windows 11, Python 3.12.13.

## O que é

Uma execução **real** do Codex CLI, pelo caminho de produção do `codex_reviewer` (testes no AppContainer, sem publicar nada),
revisou o #617 no HEAD `3b9efef` e devolveu **`REQUEST_CHANGES` com um achado HIGH** (`codex_prereview_617_verdict.json`,
bruto):

> A sonda comprova apenas que o AppContainer não acessa o canário específico sob a raiz escolhida. Um AppContainer sem
> capacidades ainda pode acessar recursos externos cujas ACLs concedam acesso a `ALL APPLICATION PACKAGES` ou ao seu SID;
> portanto, a negação do canário não prova que todo arquivo fora do workspace está protegido.

O achado foi **medido em vez de presumido**. O script `measure_fs_boundary.py` roda, dentro do sandbox, um teste por alvo que
tenta ler 4 bytes e registra quais leituras são permitidas.

## Resultado (`evidence.json`)

| Alvo | Leitura dentro do sandbox |
|---|---|
| arquivo comum do usuário (sem concessão a AppContainer) | **negada** |
| arquivo do usuário com ACL concedendo `ALL APPLICATION PACKAGES` | **permitida** |
| `C:\Windows\System32\cmd.exe` | **permitida** |
| `C:\Windows\System32\drivers\etc\hosts` | **permitida** |
| `C:\Program Files\GitHub CLI\gh.exe` | **permitida** |

O isolamento foi provado em todas as execuções (token AppContainer com zero capacidades e canário negado): a sonda está correta
no que afirma; o que estava errado era o **contrato** que eu escrevi em volta dela.

## O que mudou

Em vez de alargar o sandbox, o contrato foi reduzido ao que é verdade, e travado:

- o docstring de `sandboxed_tests.py`, o docstring e os limites do relatório do laboratório e os dois READMEs de evidência do
  #617 agora dizem que o sandbox **nega o que a ACL não concede a um AppContainer** (arquivos, pastas e credenciais do
  usuário), mas **lê o que a ACL abre a todo AppContainer** (Windows, Program Files, qualquer arquivo concedido a
  `ALL APPLICATION PACKAGES`);
- `proves_isolation` agora diz que prova o token e a negação de **um** canário, e não confinamento geral do sistema de
  arquivos;
- um teste do Windows (`test_the_documented_file_boundary_hides_user_files_but_not_what_every_appcontainer_may_read`) trava a
  fronteira medida: arquivo de usuário sem concessão → negado; arquivo concedido a `ALL APPLICATION PACKAGES` → legível;
  binário do Windows → legível. Se o Windows mudar isso, o teste falha e o contrato precisa mudar junto.

O pedido do Codex tinha duas saídas ("executar em ambiente que imponha o limite para todos os recursos externos" ou "reduzir
o contrato e impedir o uso como garantia"); foi tomada a segunda, porque a primeira exigiria outro mecanismo de isolamento.

## O que NÃO é

- **Não confina o código testado em todo o sistema de arquivos.** Segredo que esteja num arquivo legível por todo AppContainer
  (por exemplo, colocado em `C:\ProgramData` com ACL aberta) é legível pelo código testado, e a saída dele vai para os logs que
  o processo herda. O rótulo `os_sandbox` **não é garantia** de que um arquivo específico não é lido: confira a ACL dele.
- Não mediu a leitura de **todos** os arquivos do sistema: foram 5 alvos representativos.
- Uma execução por alvo: é medição do comportamento desta versão do Windows, não prova formal.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_sandboxed_tests.py -q -k documented_file_boundary
PYTHONPATH=. $PY artifacts/review/fp060/m1_closed_loop/2026-11-15_fs_boundary/measure_fs_boundary.py <dir novo>   # exige commit limpo
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `evidence.json` | commit sob medição, provas do sandbox e a leitura permitida ou negada por alvo |
| `measure_fs_boundary.py` | o script da medição |
| `codex_prereview_617_verdict.json` | o parecer bruto do Codex (`REQUEST_CHANGES`, achado HIGH) que originou a correção |
