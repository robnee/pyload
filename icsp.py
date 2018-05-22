"""
The Host controller understands the following commands

Cn  - Send command code
S	- Start programming.  Hold MCLR on target low and send MCHP signature
E	- End programming.  Release MCLR on target
Jnn - Jump the Address counter a given number of locations
R	- Read Word
Fnn	- Fetch program memory words
Gnn	- Get data memory words
Ln  - Low-level API to manipulate control lines based on subcommand n
Q   - Query line status
V	- ICSP version
K	- Sync command.  Illicit a K in response
Wnn - Send Word
Z   - Release all programmer lines

Low level API (command L)

A
B
C
D

E - MCLR1 output
F - MCLR1 low
G - MCLR1 high
H - MCLR2 output
I - MCLR2 low
J - MCLR2 high

K - Reserved

L - CLK output
M - CLK low
N - CLK high
O - CLK Pulse

P - DAT input
Q - DAT output
R - DAT low
S - DAT high

T - VON low
U - VON high

V
W
X
Y
Z

"""

import sys
import intelhex
import comm
from typing import Iterable

# -------------------------------------------------------------------------------
# Processor memory layout

PAGELEN = 32
PAGEBYTES = PAGELEN * 2

CMD_LOAD_CONFIG = b'C\x00'
CMD_LOAD_PGM = b'C\x02'
CMD_LOAD_DATA = b'C\x03'
CMD_READ_PGM = b'C\x04'
CMD_INC = b'C\x06'
CMD_PROGRAM_INT = b'C\x08'
CMD_PROGRAM_EXT = b'C\x18'
CMD_PROGRAM_END = b'C\x0A'
CMD_ERASE_PGM = b'C\x09'
CMD_ERASE_DATA = b'C\x0B'
CMD_RESET_ADDRESS = b'C\x16'
CMD_JUMP = b'J'
CMD_READ_PAGE = b'F'
CMD_READ_DATA = b'G'
CMD_SEND_WORD = b'W'
CMD_SYNC = b'K'
CMD_PAUSE = b'P'
CMD_RELEASE = b'Z'
CMD_STATUS = b'Q'
CMD_VERSION = b'V'

"""ICSP high-level API"""


def show_progress(cmd: bytes):
    """Display a progress tick unbuffered"""
    if cmd in (b'G', b'D'):
        sys.stdout.write('.')
    elif cmd == b'E':
        sys.stdout.write('x')
    elif cmd == b'S':
        sys.stdout.write('>')
    elif cmd in (b'L', b'F'):
        sys.stdout.write(':')
        
    sys.stdout.flush()


def write_config(com: comm.Comm, firmware_list, device):
    """Write config page to target"""
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
    """Read config page from target"""
    conf_page_len = device['conf_len']

    load_config(com)

    # read specified number of config words
    data = read_page(com, CMD_READ_PAGE, conf_page_len)

    count = len(data)

    if count != conf_page_len * 2:
        print(f"Short config read [{count} {conf_page_len}]")
        print("[", data, "]")

    return data


def write_page(com: comm.Comm, device, cmd_code: bytes, data: bytes, num_latches=None):
    """"Write a single page or skip the range if empty"""

    # Check for empty page and skip
    if data is None:
        jump(com, PAGELEN)
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
            send_command(com, CMD_LOAD_DATA)
            send_command(com, CMD_SEND_WORD, word)
            program(com)
            send_command(com, CMD_INC)
        elif word_count % num_latches == 0 or word_count == len(data):
            send_command(com, CMD_LOAD_PGM)
            send_command(com, CMD_SEND_WORD, word)
            program(com)
            send_command(com, CMD_INC)
        else:
            send_command(com, CMD_LOAD_PGM)
            send_command(com, CMD_SEND_WORD, word)
            send_command(com, CMD_INC)

        word_count += 1


def write_pages(com: comm.Comm, device, cmd_code: bytes, page_nums: Iterable[int], firmware_list):
    """write pages specified in page_list"""
    for page_num in page_nums:
        page = firmware_list[page_num]
        data = bytes(page) if page else None
        write_page(com, device, cmd_code, data)

    print()


def write_program_pages(com: comm.Comm, firmware_list, device):
    """write program pages"""
    page_list = range(0, device['max_page'] + 1)
    write_pages(com, device, b'L', page_list, firmware_list)


def write_data_pages(com: comm.Comm, firmware_list, device):
    """write data pages"""
    page_list = range(device['min_data'], device['max_data'] + 1)
    write_pages(com, device, b'D', page_list, firmware_list)


def read_page(com: comm.Comm, cmd_code: bytes, req_count: int) -> bytes:
    """read next program or data page"""
    cmd = cmd_code + req_count.to_bytes(2, 'little')
    com.write(cmd)

    count, data = com.read(req_count * 2)
    if count != req_count * 2:
        raise RuntimeError(f"Error [c={count}|d={data}")

    return data


def read_pages(com: comm.Comm, cmd_code: bytes, page_nums: Iterable[int]):
    """ read all pages and create a list """

    page_list = []

    for page_num in page_nums:
        data = read_page(com, cmd_code, PAGELEN)

        count = len(data)
        if count != PAGEBYTES:
            print(f"Short page num {page_num} [{count}]")
            print("[", data, "]")

        show_progress(cmd_code)

        page_list.append(data)

    return page_list


def read_program(com: comm.Comm, device) -> intelhex.Hexfile:
    """read all program pages"""
    page_nums = range(0, device['max_page'] + 1)
    page_list = read_pages(com, CMD_READ_PAGE, page_nums)

    pages = intelhex.Hexfile()

    # Read all pages and create a list
    for page_num, data in zip(page_nums, page_list):
        if data:
            page = intelhex.Page(data)

            # Remove NULL words
            for offset in range(0, len(page)):
                if page[offset] == 0x3FFF:
                    page[offset] = None

            if any(page):
                pages[page_num] = page

    return pages


def read_data(com: comm.Comm, device):
    """read all data pages"""
    pages = intelhex.Hexfile()

    # if data region is not defined then return an empty list
    if device['min_data'] or device['max_data']:
        page_nums = range(device['min_data'], device['max_data'] + 1)
        data_list = read_pages(com, CMD_READ_DATA, page_nums)

        for page_num, data in zip(page_nums, data_list):
            if data:
                page = intelhex.Page(data)

                for offset in range(0, len(page)):
                    if page[offset] == 0x00FF:
                        page[offset] = None

                if any(page):
                    pages[page_num] = page

    return pages

# ICSP low-level protocol


def send_command(com: comm.Comm, cmd: bytes, data=None):
    """"package and send command with data"""
    if data is None:
        data = b''

    com.write(cmd + data)


def get_version(com: comm.Comm):
    """Get Host controller version"""
    com.write(CMD_VERSION)

    ver = com.read_line()

    return ver.decode('utf-8').rstrip()


def get_status(com: comm.Comm):
    """Get Host controller version"""
    com.write(CMD_STATUS)

    count, status = com.read(8)

    return status


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
        if count == 0 and timeout <= 0:
            break

    return data


def sync(com: comm.Comm):
    """sync commands stream"""
    com.write(CMD_SYNC)

    prompt = wait_k(com)
    if prompt != b'K':
        raise RuntimeError(f'Error [{prompt}] command:{CMD_SYNC} ICSP')

    # There should be no characters waiting at this point
    avail = com.avail()
    if avail > 0:
        raise RuntimeError(f'Sync Error. {avail} bytes still waiting')


def erase_data(com: comm.Comm):
    """erase data memory"""
    send_command(com, CMD_ERASE_DATA)
    send_command(com, CMD_PAUSE)
    sync(com)


def erase_program(com: comm.Comm):
    """erase program memory"""
    send_command(com, CMD_ERASE_PGM)
    send_command(com, CMD_PAUSE)
    sync(com)


def program(com: comm.Comm):
    """
    if cmd_code != b'C':
        send_command(com, CMD_PROGRAM_EXT)
        time.sleep(0.002)
        send_command(com, CMD_PROGRAM_END)
    else:
    """
    send_command(com, CMD_PROGRAM_INT)
    send_command(com, CMD_PAUSE)
    sync(com)


def load_config(com: comm.Comm, data=b'\x00\x00'):
    """Switch to config segment and load a word"""
    # send_command(com, b'C' + data)
    send_command(com, CMD_LOAD_CONFIG)
    send_command(com, CMD_SEND_WORD, data)


def jump(com: comm.Comm, count):
    """jump program counter forward indicated number of words"""
    send_command(com, CMD_JUMP, count.to_bytes(2, 'little'))
    sync(com)


def release(com: comm.Comm):
    """release"""
    send_command(com, CMD_RELEASE)
    sync(com)


def reset_address(com: comm.Comm):
    """soft reset"""
    send_command(com, CMD_RESET_ADDRESS)
    sync(com)


def test_low_level(com: comm.Comm, arg: bytes):
    """ Low level API tests """
    send_command(com, b'T', arg)
