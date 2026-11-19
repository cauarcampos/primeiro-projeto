from bridge_poc.domain import Lang, Transcript, Word
from bridge_poc.glossary import Glossary
from bridge_poc.pipeline import is_fragment

TEXT = """
# comentário
Cauã
Katya
Kátia => Katya   # correção
"""


def test_parse_names_and_corrections():
    g = Glossary.parse(TEXT)
    assert g.names == ["Cauã", "Katya"]
    assert len(g.corrections) == 1
    assert g.prompt("Cauã, Kyiv") == "Cauã, Kyiv, Katya."


def test_corrections_are_whole_word_and_case_insensitive():
    g = Glossary.parse("ana => Anna")
    assert g.correct_text("ANA e banana") == "Anna e banana"


def test_corrected_word_stops_being_uncertain():
    g = Glossary.parse(TEXT)
    tr = Transcript("oi Kátia", Lang.PT, 1.0, (Word(" oi", 0.9, False), Word(" Kátia", 0.2, True)), -0.3, 0.0, False)
    out = g.correct_transcript(tr)
    assert out.text == "oi Katya"
    assert out.words[1] == Word(" Katya", 0.2, False)


def test_missing_file_gives_empty_glossary(tmp_path):
    g = Glossary.load(str(tmp_path / "nao_existe.txt"))
    assert not g and g.prompt(None) is None


def test_example_file_is_valid():
    import pathlib

    g = Glossary.load(str(pathlib.Path(__file__).parent.parent / "glossario.exemplo.txt"))
    assert "Katya" in g.names and g.corrections


def test_fragment_detection():
    assert is_fragment("Então, o Pedro")
    assert is_fragment("eu fui no mercado e comprei,")
    assert not is_fragment("Eu fui ao mercado hoje.")
    assert not is_fragment("Tudo bem?")
    assert not is_fragment("eu fui no mercado hoje de manhã cedo com a minha mãe")


def test_prompt_uses_only_names_in_the_language_alphabet():
    g = Glossary.parse("Katya\nКатя\nKátia => Katya")
    prompts = g.prompts("Cauã")
    assert prompts[Lang.PT] == "Cauã, Katya."
    assert prompts[Lang.UK] == "Катя."


def test_ellipsis_means_the_sentence_was_cut():
    assert is_fragment("Então, Lakkha Singh...")
    assert is_fragment("Então…")
