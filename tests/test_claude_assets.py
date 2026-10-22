"""Guarda das instrucoes do agente (.claude/): CLAUDE.md, rules e skills seguem as regras oficiais e nao apodrecem.

Regras de fonte: doc de memoria do Claude Code (CLAUDE.md < 200 linhas; `@import` relativo ao arquivo que importa, ate 4
saltos; rules com `paths:`) e guia de autoria de Agent Skills (`name` minusculo-hifen <= 64 sem "anthropic"/"claude";
`description` nao vazia <= 1024 sem tag XML, dizendo o que faz e quando usar; corpo < 500 linhas). O resto e deste repo:
caminho citado precisa existir e oraculo removido nao pode voltar a ser instrucao.
"""
from __future__ import annotations

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude"
SKILLS = sorted(p for p in (CLAUDE / "skills").iterdir() if (p / "SKILL.md").is_file())
RULES = sorted((CLAUDE / "rules").glob("*.md"))
INSTRUCTION_FILES = [CLAUDE / "CLAUDE.md", *RULES, *(p / "SKILL.md" for p in SKILLS)]
# raizes do repo cujos caminhos citados entre crases tem de existir (runs/ e scratch ficam fora de proposito)
CHECKED_ROOTS = ("tools/", "core/", "tests/", "docs/", "artifacts/", "fixtures/", "references/", ".claude/", ".ai_bridge/")


def frontmatter(text: str) -> tuple[dict, str]:
    """Parser minimo do subconjunto usado aqui (chave: valor, bloco `>-`/`>`/`|`, lista `- item`). Sem PyYAML no venv."""
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "frontmatter ausente"
    data: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if re.match(r"^[A-Za-z_-]+:", line):
            key, _, value = line.partition(":")
            value = value.strip()
            data[key] = [] if value == "" else ("" if value in (">", ">-", "|", "|-") else value.strip('"'))
        elif key is not None and line.strip().startswith("- ") and isinstance(data[key], list):
            data[key].append(line.strip()[2:].strip().strip('"'))
        elif key is not None and isinstance(data[key], str):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data, text[m.end():]


def imports(path: Path) -> list[str]:
    out, fenced = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("@"):
            out.append(line[1:].strip())
    return out


def tracked_files() -> list[str]:
    return subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True).splitlines()


def test_project_claude_md_is_short_and_every_import_resolves_from_its_own_file():
    text = (CLAUDE / "CLAUDE.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 200
    for path in (ROOT / "CLAUDE.md", CLAUDE / "CLAUDE.md"):
        for target in imports(path):
            # relativo ao arquivo que importa — `@.claude/x` dentro de .claude/CLAUDE.md apontaria para .claude/.claude/x
            assert (path.parent / target).is_file(), f"{path.relative_to(ROOT)}: @{target} nao resolve"


def test_imports_stay_within_the_four_hop_limit():
    def depth(path: Path, seen: tuple = ()) -> int:
        assert path not in seen, f"import circular em {path}"
        children = [path.parent / t for t in imports(path)]
        return 1 + max((depth(c, seen + (path,)) for c in children if c.is_file()), default=0)
    assert depth(ROOT / "CLAUDE.md") <= 5                     # o arquivo raiz + no maximo 4 saltos


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter_follows_the_authoring_rules(skill):
    meta, body = frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
    name, desc = meta.get("name"), meta.get("description", "")
    assert name == skill.name and re.fullmatch(r"[a-z0-9-]{1,64}", name)
    assert "anthropic" not in name and "claude" not in name
    assert 40 <= len(desc) <= 1024 and not re.search(r"<[^>]*>", desc), "descricao vazia/longa ou com tag XML"
    assert re.search(r"\b(Use|Usar|use)\b", desc), "descricao precisa dizer QUANDO usar"
    assert not desc.startswith(("Use ", "I ", "You ", "Você")), "comecar pelo que a skill faz, em 3a pessoa"
    assert len(body.splitlines()) < 500


def test_dormant_and_legacy_oracle_skills_are_not_auto_invoked():
    for name in ("gpt-docker-consult", "gpt-review-gate"):
        meta, _ = frontmatter((CLAUDE / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
        assert meta.get("disable-model-invocation") == "true", name


@pytest.mark.parametrize("rule", RULES, ids=lambda p: p.name)
def test_path_scoped_rules_match_real_files(rule):
    meta, body = frontmatter(rule.read_text(encoding="utf-8"))
    globs = meta.get("paths")
    assert isinstance(globs, list) and globs, "rule sem `paths:` carregaria em toda sessao — usar CLAUDE.md"
    files = tracked_files()
    for g in globs:
        assert any(fnmatch(f, g) or fnmatch(f, g.replace("**/", "")) for f in files), f"{rule.name}: {g} nao casa nada"
    assert body.strip()


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_paths_cited_in_instructions_exist(path):
    text = path.read_text(encoding="utf-8")
    missing = []
    for raw in re.findall(r"`([^`\s]+)`", text):
        ref = raw.rstrip(".,;:)")
        if not ref.startswith(CHECKED_ROOTS) or re.search(r"[<>*{}]|\.\.\.|…", ref):
            continue
        candidates = (ROOT / ref, path.parent / ref)
        if not any(c.exists() for c in candidates):
            missing.append(ref)
    assert not missing, f"{path.relative_to(ROOT)} cita caminhos que nao existem: {missing}"


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_removed_noc_oracle_is_never_an_instruction(path):
    """O NOC `:8765` saiu em 2026-07-24. Pode ser citado como historico, nunca como passo a seguir."""
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "8765" in line:
            assert re.search(r"removid|antigo|removed|legad", line, re.I), f"{path.name}:{n}: {line.strip()}"


def test_helpers_read_folded_blocks_lists_and_relative_imports(tmp_path):
    meta, body = frontmatter("---\nname: x\ndescription: >-\n  Faz A.\n  Use quando B.\npaths:\n  - \"a/**\"\n---\ncorpo\n")
    assert meta == {"name": "x", "description": "Faz A. Use quando B.", "paths": ["a/**"]} and body == "corpo\n"
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "constitution.md").write_text("x", encoding="utf-8")
    inner = tmp_path / ".claude" / "CLAUDE.md"
    inner.write_text("@.claude/constitution.md\n```\n@ignorado\n```\n", encoding="utf-8")
    assert imports(inner) == [".claude/constitution.md"]
    assert not (inner.parent / imports(inner)[0]).is_file()      # o bug que existia: relativo ao arquivo, nao ao cwd
