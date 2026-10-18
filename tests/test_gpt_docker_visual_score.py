"""Contract tests for the visual-score answer parser (pure, no network/git)."""
from __future__ import annotations

from tools.gpt_docker_visual_score import parse_visual_answer

URL = "https://raw.githubusercontent.com/x/y/develop/r.png"

SAMPLE = (
    "NOTA: 3/10\n\n"
    "FACTIVEL_10: sim - da pra chegar a 9-10 refazendo luz e materiais.\n\n"
    "PORQUE: a iluminacao esta ruim e a faixa preta inferior quebra a imagem.\n\n"
    "CAMINHO_PRO_10: 1) refazer a luz. 2) corrigir a camera. 3) trocar o sofa.\n"
)


def test_parses_nota_from_first_line() -> None:
    s = parse_visual_answer(URL, SAMPLE)
    assert s.nota == 3
    assert s.image_viewed is True


def test_splits_each_section_without_bleeding_into_the_next() -> None:
    s = parse_visual_answer(URL, SAMPLE)
    assert "chegar a 9-10" in s.factivel_10
    assert "NOTA" not in s.porque and "CAMINHO_PRO_10" not in s.porque
    assert s.porque.startswith("a iluminacao")
    assert s.caminho_pro_10.startswith("1) refazer a luz")


def test_image_not_viewed_yields_no_nota_and_not_viewed() -> None:
    s = parse_visual_answer(URL, "IMAGE_NOT_VIEWED")
    assert s.nota is None
    assert s.image_viewed is False


def test_missing_nota_line_returns_none_not_crash() -> None:
    s = parse_visual_answer(URL, "PORQUE: sem nota aqui.")
    assert s.nota is None
    assert s.image_viewed is True  # it saw the image, just didn't format the score


def test_nota_10_is_parsed() -> None:
    assert parse_visual_answer(URL, "NOTA: 10/10\nPORQUE: perfeito.").nota == 10
