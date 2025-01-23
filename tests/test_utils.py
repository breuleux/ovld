import pytest

from ovld import call_next, recurse
from ovld.utils import UsageError


def test_unusable_special_form():
    with pytest.raises(UsageError, match="recurse.. can only be used from inside an @ovld"):
        recurse()

    with pytest.raises(UsageError, match="call_next.. can only be used from inside an @ovld"):
        call_next()

    with pytest.raises(UsageError, match="recurse.. can only be used from inside an @ovld"):
        recurse.next


def test_special_form_str():
    assert str(recurse) == repr(recurse) == "<SpecialForm recurse>"
