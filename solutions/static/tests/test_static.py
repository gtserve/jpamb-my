from static import State
from abstractions import SignSet


def signs(code: str) -> SignSet:
    return SignSet.from_sign(code)


def test_state_order_is_pointwise():
    precise = State((signs("+"),), (signs("0"),))
    general = State((signs("0+"),), (signs("-0+"),))

    assert precise <= general
    assert not general <= precise


def test_state_join_and_meet_are_pointwise():
    left = State((signs("-0"),), (signs("+"),))
    right = State((signs("0+"),), (signs("0+"),))

    assert left | right == State((signs("-0+"),), (signs("0+"),))
    assert left & right == State((signs("0"),), (signs("+"),))
