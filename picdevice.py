# -------------------------------------------------------------------------------
#
# $Id: picdevice.py 713 2017-10-28 17:33:32Z rnee $
#
# Device parameters for PIC processors
#
# -------------------------------------------------------------------------------

PARAM = {
    0x04E: {
        'desc':        '16F819',
        'family':      'mid',
        'max_page':    0x3F,
        'conf_page':   0x100,
        'conf_len':    0x10,
        'min_data':    0x108,
        'max_data':    0x10F,
        'num_latches': 4
    },
    0x138: {
        'name':        '16F1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 16
    },
    0x140: {
        'name':        '16LF1822',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 16
    },
    0x13C: {
        'name':        '16F1826',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 8
    },
    0x13D: {
        'name':        '16F1827',
        'family':      'enh',
        'max_page':    0x3F,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 8
    },
    0x0DC: {
        'name':        '16F1840',
        'family':      'enh',
        'max_page':    0x7F,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 32
    },
    0x0A4: {
        'name':        '16F1847',
        'family':      'enh',
        'max_page':    0xFF,
        'conf_page':   0x400,
        'conf_len':    0x10,
        'min_data':    0x780,
        'max_data':    0x787,
        'num_latches': 32
    }
}
