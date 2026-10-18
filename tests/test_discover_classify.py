"""item_type rules (config/selectors.yaml) against real index link texts seen in step 1.1."""
from pathlib import Path

import pytest
import yaml

from cbtn.discover import classify

RULES = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "selectors.yaml")
                       .read_text(encoding="utf-8"))["item_type_rules"]


@pytest.mark.parametrize("text,kind", [
    ("Statistical Report 1970 Joseph Anderson", "report"),
    ("Audit Report Wilford G. Edling", "report"),
    ("Church Auditing Department Report, 2004 Robert W. Cantwell", "report"),
    ("The Church Audit Committee Report Wilford G. Edling", "report"),
    ("Church Finance Committee Report Wilford G. Edling", "report"),
    ("The Annual Report of the Church", "report"),
    ("The Sustaining of Church Officers N. Eldon Tanner", "sustaining"),
    ("Solemn Assembly D. Todd Christofferson", "sustaining"),
    ("Video: The Light That Shineth in Darkness", "video"),
    ("Faith in Every Footstep: The Epic Pioneer Journey [Video Presentation]", "video"),
    ("A Report of My Stewardship Spencer W. Kimball", "talk"),
    ("Sustaining the Prophets David B. Haight", "talk"),
    ("Sustainable Societies D. Todd Christofferson", "talk"),
    ("“Who Hath Believed Our Report?” Bruce R. McConkie", "talk"),
])
def test_classify(text, kind):
    assert classify(text, RULES) == kind
