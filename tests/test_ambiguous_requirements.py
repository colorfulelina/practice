"""Week 3: ambiguous requirements are documented one-sentence deletions."""

from semanticdrift.protocols import list_protocols
from semanticdrift.requirement_edits import collapse, deleted_sentence, load_edits


def test_each_protocol_has_an_ambiguous_requirement():
    for proto in list_protocols():
        assert proto.requirement_ambiguous.strip(), proto.name
        assert proto.requirement_ambiguous != proto.requirement_precise, proto.name


def test_ambiguous_is_precise_minus_the_documented_sentence():
    edits = load_edits()
    assert set(edits["edits"]) == {p.name for p in list_protocols()}
    for proto in list_protocols():
        deleted = deleted_sentence(proto.name)
        precise = collapse(proto.requirement_precise)
        ambiguous = collapse(proto.requirement_ambiguous)
        assert deleted
        assert deleted in precise, proto.name
        assert deleted not in ambiguous, proto.name
        rebuilt = collapse(precise.replace(deleted, " "))
        assert rebuilt == ambiguous, proto.name
