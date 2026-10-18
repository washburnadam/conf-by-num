"""Square brackets (CP-2.4): editor's insertions count; bracketed source references are citations."""
from cbtn.citations import strip_citations
from cbtn.tokenize import tokens


def keys(s):
    return [k for k, _ in tokens(s)]


def test_editorial_letters_join_the_word():
    assert keys("[s]he said [a]nd left") == ["she", "said", "and", "left"]
    assert keys("the Savior[s] of Zion") == ["the", "saviors", "of", "zion"]


def test_editor_insertions_are_kept():
    for s in ["she [my wife] said", "he [Hyrum Smith] was there", "in [1847] they came"]:
        assert strip_citations(s)[0] == s


def test_bracketed_citations_are_removed():
    assert strip_citations("Give, said the river [Gospel Doctrine, p. 304.] and so on")[0] == "Give, said the river and so on"
    assert strip_citations("woe unto them [Isa. 5:20] that call evil good")[0] == "woe unto them that call evil good"
    assert strip_citations("a hymn [Hymns, 1985, no. 19] we love")[0] == "a hymn we love"
