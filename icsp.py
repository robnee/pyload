# -------------------------------------------------------------------------------

import sys
import hex

"""
The Host controller understands the following commands

Sn	- Start programming.  Hold MCLR on target low and send MCHP signature
En	- End programming.  Release MCLR on target
X	- Reset the Address counter to zero
I	- Increment the Address counter
Jnn - Jump the Address counter a given number of locations
Bn	- Bulk erase program memory.  argument is MID/ENH flag
An	- Bulk erase data memory.  argument is MID/ENH flag 
Cnn	- Set address to 8000h and Load config word
Lnn	- Load program word at current address
Mnn	- Load program word at current address and increment program counter
Pn	- Program commit
R	- Read program memory
Fnn	- Fetch program memory words
Gnn	- Get data memory words
Dn	- Load data byte for programming
Tn  - Low-level API to manipulate control lines
V	- ICSP version
K	- NOP.  Just returns the K prompt

Low level API (command T)

R   - Release all control lines to high impedance 
U   - VCCP low
V   - VCCP high
L   - MCLR low
M   - MCLR high
F   - CLK output
G   - CLK low
H   - CLK high
P   - CLK pulse
A   - DAT output
B   - DAT input 
C   - DAT low
D   - DAT high

"""
# -------------------------------------------------------------------------------
# Processor memory layout

PAGESIZE = 64
MID = b'\x00'
ENH = b'\x01'

"""ICSP high-level API"""


def write_config(com, method, firmware_list, param):
    conf_page_num = param['conf_page']
    conf_page_len = param['conf_len']

    load_config(com)

    page = firmware_list[conf_page_num]
    if page is None:
        return

    # config words must be programed one at a time so use 1 for num latches
    write_program_page(com, method, conf_page_num, page, conf_page_len, num_latches=1)

    print()


def read_config(com, param):
    conf_page_len = param['conf_len']

    load_config(com)

    # read specified number of config words
    data = read_program(com, conf_page_len)

    count = len(data)

    if count != conf_page_len * 2:
        print("Short config read [{} {}]".format(count, conf_page_len))
        print("[", hex.bytes_to_hex(data), "]")

    page = hex.bytes_to_hex(data)

    sys.stderr.write('.')
    sys.stderr.flush()

    # pad the page to full length
    page += "    " * (PAGESIZE // 2 - conf_page_len)

    # Remove NULL commands
    for offset in range(0, len(page), 4):
        if page[offset:offset + 4] == 'FF3F':
            page = page[:offset] + '    ' + page[offset + 4:]

    return page


def write_program_page(com, method, page_num, page, length, num_latches):
    """Write a single program page to the chip"""

    # If page is not defined or if it has no non-whitespace characters then skip
    if page is None or page.isspace():
        jump(com, length)
        sys.stderr.write('.')
        sys.stderr.flush()
        return

    # each word is 4 characters
    byte_count = len(page)
    if byte_count < length * 4:
        raise RuntimeError("Invalid program page size ({}) for page {}".format(byte_count, page_num))

    sys.stderr.write(':')
    sys.stderr.flush()

    word_count = 0
    for word_num in range(0, byte_count, 4):
        chunk = page[word_num: word_num + 4]

        # Replace empty words
        if chunk == '    ':
            chunk = 'FFFF'

        word = hex.hex_to_bytes(chunk, 2)

        word_count += 1

        # Issue a program command at the end of the set of data latches or if
        # this is the last word on the page
        if word_count % num_latches == 0 or word_count == length:
            load_program(com, word)
            program(com, method)
            inc(com)
        else:
            load_program_inc(com, word)


def write_program_pages(com, method, firmware_list, param):
    page_list = range(0, param['max_page'] + 1)
    num_latches = param['num_latches']

    for page_num in page_list:
        if page_num < len(firmware_list):
            write_program_page(com, method, page_num, firmware_list[page_num], PAGESIZE // 2, num_latches)

    print()


def read_program_page(com):
    # read a full page of words (2x number of bytes)
    data = read_program(com, PAGESIZE // 2)

    count = len(data)

    if count != PAGESIZE:
        print("Short page [{}]".format(count))
        print("[", hex.bytes_to_hex(data), "]")

    return data


def read_program_pages(com, param):
    page_list = range(0, param['max_page'] + 1)

    chip_list = []

    # Read all pages and create a list
    for page_num in page_list:
        data = read_program_page(com)

        page = hex.bytes_to_hex(data)

        sys.stderr.write(':')
        sys.stderr.flush()

        # Remove NULL commands
        for offset in range(0, len(page), 4):
            if page[offset:offset + 4] == 'FF3F':
                page = page[:offset] + '    ' + page[offset + 4:]

        if page.strip() != '':
            hex.add_page(chip_list, page_num)
            chip_list[page_num] = page

    return chip_list


def write_data_page(com, method, page_num, page):
    """"Write a single program page to the chip"""

    # Data checks
    if page is None:
        jump(com, PAGESIZE // 2)
        sys.stderr.write('.')
        sys.stderr.flush()
        return

    # each word is 4 characters
    byte_count = len(page)
    if byte_count != PAGESIZE * 2:
        raise RuntimeError("Invalid data page size ({}) for page {}".format(byte_count, page_num))

    sys.stderr.write(':')
    sys.stderr.flush()

    for word_num in range(0, byte_count, 4):
        chunk = page[word_num: word_num + 2]
        if chunk != '  ':
            byte = hex.hex_to_bytes(chunk, 2)
            load_data(com, byte)
            program(com, method)

        inc(com)


def write_data_pages(com, method, data_list, param):
    page_list = range(param['min_data'], param['max_data'] + 1)

    for page_num in page_list:
        if page_num < len(data_list):
            write_data_page(com, method, page_num, data_list[page_num])

    print()


def read_data_page(com):
    # read a half page of words.  Each byte will be padded out with an extra for
    # writing to hex file so that the resultant page will be full size
    data = read_data(com, PAGESIZE // 2)

    count = len(data)
    if count != PAGESIZE // 2:
        print("Short data page [{}]".format(count))
        print("[", hex.bytes_to_hex(data), "]")

    return data


def read_data_pages(com, param):
    page_list = range(param['min_data'], param['max_data'] + 1)

    chip_list = []

    # Read all pages and create a list
    for page_num in page_list:
        data = read_data_page(com)

        # data pages are only bytes.  Convert back to words
        page = ''
        for i in range(0, len(data)):
            page = page + hex.bytes_to_hex(data[i:i + 1]) + '00'

        sys.stderr.write('.')
        sys.stderr.flush()

        # Remove NULL commands
        for offset in range(0, len(page), 4):
            if page[offset:offset + 4] == 'FF00':
                page = page[:offset] + '    ' + page[offset + 4:]

        if page.strip() != '':
            hex.add_page(chip_list, page_num)
            chip_list[page_num] = page

    return chip_list

# ICSP low-level protocol


def wait_k(com):
    """Wait for K (OK) prompt"""

    data = bytes()
    timeout = 3

    while True:
        count, prompt = com.read(1)

        data += prompt
        if prompt == b'K':
            break

        # Check timeout
        timeout -= 1
        if count == 0 and timeout == 0:
            break

    return data


def send_command(com, cmd : bytes, data=None):
    """"package and send command with data"""

    if data is None:
        data = b''

    com.write(cmd + data)

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError('Error [{}] command:{} ICSP'.format(prompt, cmd))


def send_start(com, method):
    """reset target and start ICSP"""

    send_command(com, b'S', method)


def send_end(com, method):
    """icsp_end"""

    send_command(com, b'E', method)


def get_version(com):
    """Get Host controller version"""

    cmd = b'V'
    com.write(cmd)

    ver = com.read_line()

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError('Error [{}] command:{} ICSP'.format(prompt, cmd))

    return ver.decode('utf-8').rstrip()


def erase_program(com, method):
    """Switch to config segment and load a word"""

    send_command(com, b'B', method)


def load_config(com):
    # Switch to config segment and load a word
    send_command(com, b'C\x00\x00')


def load_program(com, data):
    send_command(com, b'L', data)


def load_program_inc(com, data):
    send_command(com, b'M', data)


def program(com, method):
    """icsp internally or externally timed write depending on the method"""
    send_command(com, b'P', method)


def inc(com):
    """increment address"""
    send_command(com, b'I')


def jump(com, count):
    # jump address
    send_command(com, b'J' + count.to_bytes(2, 'little'))


def reset_address(com):
    # reset address to zero
    send_command(com, b'X')


def hard_reset(com):
    # reset
    send_command(com, b'Z')


def reset(com, method):
    """reset"""

    if method == MID:
        # hard reset followed by a restart
        hard_reset(com)
        send_start(com, MID)
    else:
        # ENH parts have a reset address command
        reset_address(com)


def read_program(com, req_count):
    # read program memory
    cmd = b'F' + req_count.to_bytes(2, 'little')

    com.write(cmd)

    count, data = com.read(req_count * 2)
    if count != req_count * 2:
        raise RuntimeError("Error [c={}|d={} {}".format(count, data,
                           hex.bytes_to_hex(data)))

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError('Error [{}] command:{} ICSP'.format(prompt, cmd))

    return data


def erase_data(com, method):
    """erase data memory"""
    send_command(com, b'A', method)


def load_data(com, data):
    """load data memory"""
    send_command(com, b'D', data)


def read_data(com, req_count):
    """read data"""
    cmd = b'G' + req_count.to_bytes(2, 'little')

    com.write(cmd)

    count, data = com.read(req_count)

    if count != req_count:
        raise RuntimeError("Error [c={}|d={} {}".format(count, data,
                           hex.bytes_to_hex(data)))

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError('Error [{}] command:{} ICSP'.format(prompt, cmd))

    return data


def test_low_level(com, arg : bytes):
    """ Low leve API tests """
    send_command(b'T', arg)