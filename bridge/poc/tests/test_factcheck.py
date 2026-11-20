from bridge_poc.domain import Lang
from bridge_poc.factcheck import check, numbers

PT, UK = Lang.PT, Lang.UK


def test_wrong_weekday_is_detected():
    src = "Não vou trabalhar amanhã, só na quinta-feira às 15h."
    assert check(src, "Ні, я не буду працювати завтра, лише в п'ятницю о 15:00.", PT, UK)
    assert check(src, "Я не працюватиму завтра, лише в четвер о 15:00.", PT, UK) == []


def test_ordinal_is_not_a_weekday():
    assert check("É a segunda vez que eu vejo.", "Я бачу це вдруге.", PT, UK) == []
    assert check("Toda segunda eu corro.", "Щопонеділка я бігаю.", PT, UK) == []


def test_numbers():
    assert numbers("às 15h, 3,5 km e 1.000 pessoas") == {"15", "3.5", "1000"}
    assert check("Custa 250 reais.", "Коштує 520 реалів.", PT, UK)
    assert check("Я народилася 12 травня.", "Eu nasci em 12 de maio.", UK, PT) == []


def test_wrong_month_is_detected():
    assert check("Я приїду в липні.", "Eu chego em junho.", UK, PT)
    assert check("Я приїду в липні.", "Eu chego em julho.", UK, PT) == []


def test_apostrophe_variants():
    assert check("Na sexta-feira.", "У пʼятницю.", PT, UK) == []


def test_bare_terca_without_context_is_not_a_day():
    assert check("A terça parte do bolo.", "Третина торта.", PT, UK) == []
    assert check("Até terça!", "До вівторка!", PT, UK) == []


class _Fixed:
    def __init__(self, out):
        self.out, self.calls = out, 0

    def translate(self, text, src, tgt):
        self.calls += 1
        return self.out


def test_checked_translator_swaps_to_secondary_when_facts_differ():
    from bridge_poc.translate import CheckedTranslator

    ai = _Fixed("Лише в п'ятницю о 15:00.")
    nllb = _Fixed("Тільки в четвер о 15:00.")
    out, warn = CheckedTranslator(ai, nllb).translate_checked("Só na quinta-feira às 15h.", PT, UK)
    assert out == "Тільки в четвер о 15:00." and warn == []


def test_checked_translator_does_not_call_secondary_when_ok():
    from bridge_poc.translate import CheckedTranslator

    ai, nllb = _Fixed("Лише в четвер."), _Fixed("x")
    assert CheckedTranslator(ai, nllb).translate_checked("Só na quinta-feira.", PT, UK) == ("Лише в четвер.", [])
    assert nllb.calls == 0


def test_checked_translator_warns_when_both_fail():
    from bridge_poc.translate import CheckedTranslator

    out, warn = CheckedTranslator(_Fixed("У п'ятницю."), _Fixed("У суботу.")).translate_checked(
        "Na quinta-feira.", PT, UK
    )
    assert out == "У п'ятницю." and warn == ["dia da semana diferente"]


def test_routed_translator_uses_engine_per_direction_and_checks_facts():
    from bridge_poc.translate import RoutedTranslator

    a, b = _Fixed("Na sexta."), _Fixed("У четвер.")
    r = RoutedTranslator({(UK, PT): a, (PT, UK): b})
    assert r.translate_checked("Na quinta-feira.", PT, UK) == ("У четвер.", [])
    out, warn = r.translate_checked("У четвер.", UK, PT)
    assert out == "Na sexta." and warn == ["dia da semana diferente"]
    assert (a.calls, b.calls) == (1, 1)
