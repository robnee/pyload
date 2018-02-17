# -------------------------------------------------------------------------------

import sys
import hexfile
import comm

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
FAMILY_NAMES = {MID: 'Midrange', ENH: 'Enhanced Midrange'}

"""ICSP high-level API"""


def show_progress(cmd: bytes):
    if cmd in (b'G', b'D'):
        sys.stderr.write('.')
    elif cmd == b'E':
        sys.stderr.write('x')
    elif cmd == b'S':
        sys.stderr.write('>')
    elif cmd in (b'L', b'F'):
        sys.stderr.write(':')
        
    sys.stderr.flush()


def write_config(com: comm.Comm, firmware_list, device):
    conf_page_num = device['conf_page']
    conf_page_len = device['conf_len']

    load_config(com)

    page = firmware_list[conf_page_num]
    if page is None:
        return

    data = bytes(page)[:conf_page_len * 2]
    # config words must be programed one at a time so use 1 for num latches
    # write_program_page(com, device, conf_page_num, bytes(data), num_latches=1)
    write_page(com, device, b'L', bytes(data), num_latches=1)

    print()


def read_config(com: comm.Comm, device) -> bytes:
    conf_page_len = device['conf_len']

    load_config(com)

    # read specified number of config words
    data = read_page(com, b'F', conf_page_len)

    count = len(data)

    if count != conf_page_len * 2:
        print(f"Short config read [{count} {conf_page_len}]")
        print("[", hexfile.bytes_to_hex(data), "]")

    return data


def write_page(com: comm.Comm, device, cmd_code: bytes, data: bytes, num_latches=None):
    """"Write a single page or skip the range if empty"""

    # Check for empty page and skip
    if data is None:
        jump(com, PAGESIZE // 2)
        show_progress(b'S')
        return

    if not num_latches:
        num_latches = device['num_latches']

    show_progress(cmd_code)

    word_count = 1
    for word_num in range(0, len(data), 2):
        word = data[word_num: word_num + 2]

        # Issue a program command at the end of the set of data latches or if
        # this is the last word on the page
        if cmd_code == b'D':
            load_data(com, word)
            program(com, device)
            inc(com)
        elif word_count % num_latches == 0 or word_count == len(data):
            load_program(com, word)
            program(com, device)
            inc(com)
        else:
            load_program_inc(com, word)

        word_count += 1


def write_pages(com: comm.Comm, device, cmd_code: bytes, page_list, firmware_list):
    for page_num in page_list:
        page = firmware_list[page_num]
        data = bytes(page) if page else None
        write_page(com, device, cmd_code, data)

    print()


def write_program_pages(com: comm.Comm, firmware_list, device):
    page_list = range(0, device['max_page'] + 1)
    write_pages(com, device, b'L', page_list, firmware_list)


def write_data_pages(com: comm.Comm, firmware_list, device):
    page_list = range(device['min_data'], device['max_data'] + 1)
    write_pages(com, device, b'D', page_list, firmware_list)


def read_page(com: comm.Comm, cmd_code: bytes, req_count: int) -> bytes:
    # read program memory
    cmd = cmd_code + req_count.to_bytes(2, 'little')
    com.write(cmd)

    count, data = com.read(req_count * 2)
    if count != req_count * 2:
        raise RuntimeError("Error [c={}|d={} {}".format(count, data,
                           hexfile.bytes_to_hex(data)))

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError(f'Error [{prompt}] command:{cmd} ICSP')

    return data


def read_pages(com: comm.Comm, cmd_code: bytes, page_nums):
    """ read all pages and create a list """

    page_list = []

    for page_num in page_nums:
        data = read_page(com, cmd_code, PAGESIZE // 2)

        count = len(data)
        if count != PAGESIZE:
            print(f"Short page num {page_num} [{count}]")
            print("[", hexfile.bytes_to_hex(data), "]")

        show_progress(cmd_code)

        page_list.append(data)

    return page_list


def read_program(com: comm.Comm, device) -> hexfile.Hexfile:
    page_nums = range(0, device['max_page'] + 1)
    page_list = read_pages(com, b'F', page_nums)

    pages = hexfile.Hexfile()

    # Read all pages and create a list
    for page_num, data in zip(page_nums, page_list):
        if data:
            page = hexfile.Page(data)

            # Remove NULL words
            for offset in range(0, len(page), 2):
                word = page[offset: offset + 2]
                if word == ['FF', '3F']:
                    page[offset] = None
                    page[offset + 1] = None

            if any(page):
                pages[page_num] = page

    return pages


def read_data(com: comm.Comm, device):
    page_nums = range(device['min_data'], device['max_data'] + 1)
    data_list = read_pages(com, b'G', page_nums)

    pages = hexfile.Hexfile()

    for page_num, data in zip(page_nums, data_list):
        if data:
            page = hexfile.Page(data)

            for offset in range(0, len(page), 2):
                word = [page[offset], '00']
                if word == ['FF', '00']:
                    page[offset] = None
                    page[offset + 1] = None

            if any(page):
                pages[page_num] = page

    return pages

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


def send_command(com: comm.Comm, cmd: bytes, data=None):
    """"package and send command with data"""

    if data is None:
        data = b''

    com.write(cmd + data)

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError(f'Error expecting prompt [{prompt}] command:{cmd} data:{data} ICSP')


def send_start(com: comm.Comm, method):
    """reset target and start ICSP"""
    send_command(com, b'S', method)


def send_end(com: comm.Comm, method):
    """icsp_end"""
    send_command(com, b'E', method)


def get_version(com: comm.Comm):
    """Get Host controller version"""

    cmd = b'V'
    com.write(cmd)

    ver = com.read_line()

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError(f'Error [{ver} {prompt}] command:{cmd} ICSP')

    return ver.decode('utf-8').rstrip()


def erase_program(com: comm.Comm, device):
    """Switch to config segment and load a word"""
    method = MID if device['family'] == 'mid' else ENH
    send_command(com, b'B', method)


def load_config(com: comm.Comm):
    """Switch to config segment and load a word"""
    send_command(com, b'C\x00\x00')


def load_data(com: comm.Comm, data):
    """load data memory"""
    send_command(com, b'D', data)


def load_program(com: comm.Comm, data):
    send_command(com, b'L', data)


def load_program_inc(com: comm.Comm, data):
    send_command(com, b'M', data)


def program(com: comm.Comm, device):
    """icsp internally or externally timed write depending on the method"""
    method = MID if device['family'] == 'mid' else ENH
    send_command(com, b'P', method)


def inc(com: comm.Comm):
    """increment address"""
    send_command(com, b'I')


def jump(com: comm.Comm, count):
    # jump address
    send_command(com, b'J' + count.to_bytes(2, 'little'))


def reset_address(com: comm.Comm):
    # reset address to zero
    send_command(com, b'X')


def hard_reset(com: comm.Comm):
    # reset
    send_command(com, b'Z')


def reset(com: comm.Comm, device):
    """reset"""

    if device['family'] == 'mid':
        # hard reset followed by a restart
        hard_reset(com)
        send_start(com, MID)
    else:
        # ENH parts have a reset address command
        reset_address(com)


def erase_data(com: comm.Comm, device):
    """erase data memory"""
    method = MID if device['family'] == 'mid' else ENH
    send_command(com, b'A', method)


def test_low_level(com: comm.Comm, arg: bytes):
    """ Low level API tests """
    send_command(com, b'T', arg)
