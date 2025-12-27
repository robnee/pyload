
"""Device parameters for PIC processors
"""

from typing import TypedDict, Optional

class Param(TypedDict):
    name: str
    family: str
    max_page: int
    conf_page: int
    conf_len: int
    min_data: int
    max_data: int
    chip_id: int
    id_loc: tuple
    rev_loc: tuple
    num_latches: int

PARAM = {
    0x04E: Param({
        'name':        '16F819',
        'family':      'mid',
        'max_page':    0x3F,
        'conf_page':   0x100,
        'conf_len':    0x0A,
        'min_data':    0x108,
        'max_data':    0x10F,
        'chip_id':     0b0001001110_0000,
        'id_loc':      (0x06, 0x3FF),
        'rev_loc':     (0x06, 0x00F),
        'num_latches': 4
    }),
    0x138: Param({
        'name':        '12F1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b100111000_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 16
    }),
    0x140: Param({
        'name':        '12LF1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b101000000_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 16
    }),
    0x3049: Param({
        'name':        '16F1713',
        'family':      'enh',
        'max_page':    0x7F,
        'conf_page':   0x400,
        'conf_len':    0x11,
        'min_data':    0x0,
        'max_data':    0x0,
        'chip_id':     0b11_0000_1000_1001,
        'id_loc':      (0x06, 0x3FFF),
        'rev_loc':     (0x05, 0x0FFF),
        'num_latches': 32
    }),
    0x304B: Param({
        'name':        '16LF1713',
        'family':      'enh',
        'max_page':    0x7F,
        'conf_page':   0x400,
        'conf_len':    0x11,
        'min_data':    0x0,
        'max_data':    0x0,
        'chip_id':     0b11_0000_1000_1011,
        'id_loc':      (0x06, 0x3FFF),
        'rev_loc':     (0x05, 0x0FFF),
        'num_latches': 32
    }),
    0x3048: Param({
        'name':        '16F1716',
        'family':      'enh',
        'max_page':    0xFF,
        'conf_page':   0x400,
        'conf_len':    0x11,
        'min_data':    0x0,
        'max_data':    0x0,
        'chip_id':     0b11_0000_1000_1000,
        'id_loc':      (0x06, 0x3FFF),
        'rev_loc':     (0x05, 0x0FFF),
        'num_latches': 32
    }),
    0x304A: Param({
        'name':        '16LF1716',
        'family':      'enh',
        'max_page':    0xFF,
        'conf_page':   0x400,
        'conf_len':    0x11,
        'min_data':    0x0,
        'max_data':    0x0,
        'chip_id':     0b11_0000_1000_1010,
        'id_loc':      (0x06, 0x3FFF),
        'rev_loc':     (0x05, 0x0FFF),
        'num_latches': 32
    }),
    0x13C: Param({
        'name':        '16F1826',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b100111100_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 8
    }),
    0x13D: Param({
        'name':        '16F1827',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b100111101_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 8
    }),
    0x0DC: Param({
        'name':        '12F1840',
        'family':      'enh',
        'max_page':    0x7F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b011011100_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 32
    }),
    0x0A4: Param({
        'name':        '16F1847',
        'family':      'enh',
        'max_page':    0xFF,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'chip_id':     0b010100100_00101,
        'id_loc':      (0x06, 0x3FE),
        'rev_loc':     (0x06, 0x01F),
        'num_latches': 32
    })
}


def find_by_name(name: str):
    device, = [x for x in PARAM.values() if x['name'] == name.upper()]

    return device


def find_by_chip_id(chip_id: int) -> Optional[Param]:
    for device_id, param in PARAM.items():
        id_addr, id_mask = param['id_loc']
        if chip_id & id_mask == param['chip_id'] & id_mask:
            return param
    return None


def get_id_rev(param, chip_id, chip_rev):
    id_addr, id_mask = param['id_loc']
    rev_addr, rev_mask = param['rev_loc']
    if id_addr == rev_addr:
        shift = rev_mask.bit_length()
        return chip_id >> shift, chip_id & rev_mask
    else:
        return chip_id, chip_rev
