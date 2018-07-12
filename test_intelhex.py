import pytest
import intelhex


@pytest.fixture()
def com():
    class Com:
        def read(self, count):
            return 1, b'K'

    return Com()


@pytest.fixture()
def page1():
    p = intelhex.Page()
    p[1] = '    '
    p[2] = '4F2C'
    p[intelhex.PAGELEN - 1] = '9F6C'
    p[23] = 0x5f
    p[5:7] = '12345678'
    p[9] = 'FF3F'

    return p


@pytest.fixture()
def page2():
    q = intelhex.Page(
        '00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ' \
        '00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')

    return q

class TestIntelhex:
    """ test the intelhex module functions"""

    def test_1(self):
        assert list(intelhex.chunks('6F6665623838', 2)) == ['6F', '66', '65', '62', '38', '38']

    def test_2(self):
        assert intelhex.hex_to_sum('afeb88'), 0xaf + 0xeb + 0x88 == (546, 546)

    def test_3(self, page1):
        assert format(page1) == \
               '        4F2C        12345678        FF3F                        ' \
               '                            5F00                            9F6C'

    def test_4(self, page1):
        assert page1[6], page1[9] == (30806, 16383)

    def test_5(self, page1):
        assert page1.tobytes(b'..') == \
               b'....O,....\x124Vx....\xff?.........................._\x00..............\x9fl'

    def test_6(self, page1):
        with pytest.raises(IndexError):
            page1[intelhex.PAGELEN] = '77'

    def test_7(self, page1):
        with pytest.raises(ValueError):
            page1[4] = '4ff'

    def test_8(self, page2):
        assert repr(page2) == \
               "Page('00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28  " \
               "  00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')"

    def test_9(self, page2):
        assert page2.display(0) == \
               '000-0000 : |00308C0001308D00 2100EA3099001A1C 172888018C142523 8C1025231A28    |\n' \
               '000-0010 : |00308C0001308D00 2100EA3099001A1C 172888018C142523 8C1025231A28    |'

    def test_10(self, page2):
        assert page2.tobytes(b'..') == \
               b'\x000\x8c\x00\x010\x8d\x00!\x00\xea0\x99\x00\x1a\x1c\x17(\x88\x01' \
               b'\x8c\x14%#\x8c\x10%#\x1a(..\x000\x8c\x00\x010\x8d\x00!\x00\xea0\x99' \
               b'\x00\x1a\x1c\x17(\x88\x01\x8c\x14%#\x8c\x10%#\x1a(..'
