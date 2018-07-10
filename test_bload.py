
import pytest
import bload


@pytest.fixture()
def com():
    class Com:
        def read(self, count):
            return 1, b'K'
            
    return Com()
        
        
class TestBload:
    """ test the bload module functions"""
    
    def test_1(self):
        assert bload.get_address(12) == b'\x80\x01'

    def test_2(self): 
        assert bload.calc_checksum(b'abcd') == 138
        
    def test_3(self): 
        assert bload. calc_checksum(b'') == 0

    def test_4(self):
        assert bload.get_command(b'X', 12, b'1234') == b'X\x80\x011234K'
        
    def test_5(self, com):
        assert bload.sync(com) is True
