
"""Device parameters for PIC processors

$Id: picdevice.py 896 2018-04-27 03:00:14Z rnee $
"""

PARAM = {
    0x04E: {
        'desc':        '16F819',
        'family':      'mid',
        'max_page':    0x3F,
        'conf_page':   0x100,
        'conf_len':    0x0A,
        'min_data':    0x108,
        'max_data':    0x10F,
        'id_mask':     (0x3FF, 0x00F),
        'num_latches': 4
    },
    0x138: {
        'name':        '12F1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 16
    },
    0x140: {
        'name':        '12LF1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 16
    },
    0x3049: {
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
    },
    0x304B: {
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
    },
    0x3048: {
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
    },
    0x304A: {
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
    },
    0x13C: {
        'name':        '16F1826',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE0, 0x001F),
        'num_latches': 8
    },
    0x13D: {
        'name':        '16F1827',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 8
    },
    0x0DC: {
        'name':        '12F1840',
        'family':      'enh',
        'max_page':    0x7F,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 32
    },
    0x0A4: {
        'name':        '16F1847',
        'family':      'enh',
        'max_page':    0xFF,
        'conf_page':   0x400,
        'conf_len':    0x0A,
        'min_data':    0x780,
        'max_data':    0x787,
        'id_mask':     (0x3FE, 0x01F),
        'num_latches': 32
    }
}
