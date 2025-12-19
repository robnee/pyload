
"""Device parameters for PIC processors
"""

from typing import TypedDict, NotRequired

class Param(TypedDict):
    name: str
    family: str
    max_page: int
    conf_page: int
    conf_len: int
    min_data: int
    max_data: int
    rev_loc: NotRequired[int]
    id_mask: tuple
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
        'id_mask':     (0x3FF, 0x00F),
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
        'id_mask':     (0x3FE, 0x01F),
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
        'id_mask':     (0x3FE, 0x01F),
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
        'rev_loc':     0x05,
        'id_mask':     (0x3FFF, 0x0000),
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
        'rev_loc':     0x05,
        'id_mask':     (0x3FFF, 0x0000),
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
        'rev_loc':     0x05,
        'id_mask':     (0x3FFF, 0x0000),
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
        'rev_loc':     0x05,
        'id_mask':     (0x3FFF, 0x0000),
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
        'id_mask':     (0x3FE, 0x01F),
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
        'id_mask':     (0x3FE, 0x01F),
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
        'id_mask':     (0x3FE, 0x01F),
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
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 32
    })
}


def find_by_name(name: str):
    device, = [x for x in PARAM.values() if x['name'] == name]

    return device
