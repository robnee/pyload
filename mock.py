"""
Mock icsp interface for testing.  Implements the serial port protocol that can be wrapped in a Comm object.

Attempting to create a state machine that runs on every call to the serial port read API and reads and writes to and
from the input and output queue until the state machine blocks on a serial read for the next icsp command byte.
At that point the inbound request can be satisfied from one of the two queues.

How to do that?  Perhaps this is an example of coroutine programming with yield?  That might simplify the handoff
in and out of the state machine.  Not sure how to yield out of the state machine without creating a call chain that
goes deeper and deeper.

"""

import time
import random
import logging
import intelhex
import picdevice


CMD_LOAD_CONFIG = b'\x00'
CMD_LOAD_PGM = b'\x02'
CMD_LOAD_DATA = b'\x03'
CMD_READ_PGM = b'\x04'
CMD_READ_DATA = b'\x05'
CMD_INC = b'\x06'
CMD_PROGRAM_INT = b'\x08'
CMD_PROGRAM_EXT = b'\x18'
CMD_PROGRAM_END = b'\x0A'
CMD_ERASE_PGM = b'\x09'
CMD_ERASE_DATA = b'\x0B'
CMD_RESET_ADDRESS = b'\x16'


class Port:
    def __init__(self):
        self._dtr = False
        self.inq = bytes()
        self.outq = bytes()
        self.error_prob = {'write': 0.03, 'read':0.01}

    def _add_noise(self, data: bytes, op: str) -> bytes:
        """simulate transmission errors"""
        if data and random.random() < self.error_prob[op]:
            num_bytes = len(data)
            index = random.randrange(num_bytes)
            noise = bytes([random.randrange(256)])
            data = data[:index] + noise + data[index + 1:]
            logging.info(f'data error {op} {num_bytes}')

        return data

    def clear(self):
        self.inq = bytes()
        self.outq = bytes()

    def reset(self):
        """reset the port.  typically overriddend by Host"""
        self.clear()

    @property
    def port(self):
        return 'mock'

    @property
    def in_waiting(self):
        return len(self.inq)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, state: bool):
        # detect dtr reset
        if self.dtr and not state:
            self.reset()

        self._dtr = state

    @property
    def rts(self):
        """return state of RTS output line"""
        return False

    @property
    def dsr(self):
        """return state of DSR input line"""
        return False

    @property
    def cts(self):
        """return state of CTS input line"""
        return False

    def write(self, data: bytes):
        self.outq += self._add_noise(data, 'write')

    def read(self, num_bytes: int):
        """read data from inq"""
        if len(self.inq) < num_bytes:
            logging.info(f'{self.inq} < {num_bytes} out: {self.outq}')
            
        ret, self.inq = self.inq[: num_bytes], self.inq[num_bytes:]
        logging.debug(f'read: {num_bytes} {ret} in: {self.inq} out: {self.outq}')

        return self._add_noise(ret, 'read')

    def readline(self):
        if len(self.inq) < 1:
            logging.info(f'readline: in: {self.inq} out: {self.outq}')

        nl = self.inq.find(b'\n')
        if nl < 0:
            ret, self.inq = self.inq, bytes()
        else:
            ret, self.inq = self.inq[: nl + 1], self.inq[nl + 1:]

        return self._add_noise(ret, 'read')
        
    def send_break(self, duration: int):
        self.clear()

    def open(self):
        self.clear()
        
    def close(self):
        self.clear()

    def ser_avail(self):
        return self.outq
        
    def ser_get(self) -> bytes:
        # read a byte from outq
        if not self.ser_avail():
            raise EOFError

        ret, self.outq = self.outq[:1], self.outq[1:]
        return ret

    def ser_get_word(self) -> int:
        low = self.ser_get()
        high = self.ser_get()
        return int.from_bytes(low + high, byteorder='little')

    def ser_out(self, data: bytes):
        # add bytes to the inq
        self.inq += data


class Proc:
    """base class for command processor"""
    def __init__(self, port: Port):
        self.port = port

    def reset(self):
        """reset ICSP host"""
        self.ser_out(b'K')
        logging.info(f'Proc reset: {self.port.inq} out: {self.port.outq}')

    def ser_avail(self) -> bytes:
        return self.port.ser_avail()

    def ser_get(self) -> bytes:
        return self.port.ser_get()
        
    def ser_get_word(self) -> int:
        return self.port.ser_get_word()

    def ser_out(self, data: bytes):
        self.port.ser_out(data)


class Target:
    def __init__(self, device_name, firmware):
        self.firmware = firmware
        self.word_address = 0
        self.cmd = None
        self.word = b''
        self.run_state = "HALT"
        
        self.device = picdevice.find_by_name(device_name)
        self._clear_latches()

    @property
    def _latch_count(self):
        return self.device['num_latches']

    def _clear_latches(self):
        self.latch = [None] * self._latch_count
        
    def _load_latch(self):
        pn, bn = divmod(self.word_address, self._latch_count)
        self.latch[bn] = self.word

    def _read_word(self, msb_mask: int):
        """access a two byte firmware word by word address"""
        
        # chip id and revision aren't in firmware file
        if self.word_address == 0x8006:
            chip_id = (0b10_0111_000 << 5) + 0b0_0101
            self.word = chip_id.to_bytes(2, 'little')
        else:
            page_num, word_num = divmod(self.word_address, intelhex.PAGELEN)
            byte_num = word_num * 2
            
            page = self.firmware[page_num]
            if page:
                data = bytes(page)
                self.word = data[byte_num: byte_num + 2]
            else:
                self.word = b'\xff\xff'

            # mask off unused bits
            self.word = bytes([self.word[0], self.word[1] & msb_mask])

    def _program(self):
        # compute page, offset and latch address
        page_num, page_offset = divmod(self.word_address, intelhex.PAGELEN)
        word_offset = (page_offset // self._latch_count) * self._latch_count
  
        if not self.firmware[page_num]:
            self.firmware[page_num] = intelhex.Page()

        for bn in range(self._latch_count):
            if self.latch[bn] is not None:
                self.firmware[page_num][word_offset + bn] = self.latch[bn]

        self._clear_latches()

    def _erase_pgm(self):
        # check if address points to program or config memory
        for page_num in range(self.device['max_page'] + 1):
            self.firmware[page_num] = None

        # clear user id words 
        page_num = self.device['conf_page']
        self.firmware[page_num][0] = None
        self.firmware[page_num][1] = None
        self.firmware[page_num][2] = None
        self.firmware[page_num][3] = None
    
    def _erase_data(self):
        for page_num in range(self.device['min_data'], self.device['max_data'] + 1):
            self.firmware[page_num] = None
        
    def _run(self):
        """ process cmd/word instructions """

        # print(f'cmd: {cmd} addr: {self.word_address: X} word: {self.word}')
        # TODO: check run state to ignore commands
        if self.cmd == CMD_LOAD_CONFIG:
            self.word_address = 0x8000
            self._load_latch()
        elif self.cmd == CMD_LOAD_PGM:
            self._load_latch()
        elif self.cmd == CMD_LOAD_DATA:
            if self.word_address < 0xf000:
                self.word_address = 0xf000
            self._load_latch()
        elif self.cmd == CMD_READ_PGM:
            self._read_word(0x3f)
        elif self.cmd == CMD_READ_DATA:
            if self.word_address < 0xf000:
                self.word_address = 0xf000
            self._read_word(0x00)
        elif self.cmd == CMD_PROGRAM_INT:
            self._program()
        elif self.cmd == CMD_ERASE_PGM:
            self._erase_pgm()
        elif self.cmd == CMD_ERASE_DATA:
            self._erase_data()
        elif self.cmd == CMD_INC:
            self.word_address += 1
        elif self.cmd == CMD_RESET_ADDRESS:
            self.word_address = 0
        else:
            raise RuntimeError('invalid cmd:', self.cmd)
        
        self.cmd = None
              
    def send_cmd(self, cmd: bytes):
        """ send icsp command.  equivalent to clocking in the first six bits """

        # there should be no pending commands when receiving a new one
        if self.cmd is not None:
            raise ValueError(f'sending cmd {cmd} pending {self.cmd}')

        self.cmd = cmd

        # commands that don't require args can be dispatched
        if self.cmd in (CMD_READ_PGM, CMD_READ_DATA, CMD_INC,
                        CMD_ERASE_PGM, CMD_ERASE_DATA, CMD_RESET_ADDRESS,
                        CMD_PROGRAM_INT, CMD_PROGRAM_EXT, CMD_PROGRAM_END):
            self._run()

    def send_arg(self, word):
        """ send optional word portion of command and dispatch it """

        self.word = word
        self._run()

    def send_byte(self, b: bytes):
        # TODO: implement start state management
        pass

    def get_word(self) -> bytes:
        return self.word

    def set_mclr2(self, state: bool):
        pass

    def set_clk(self, state: bool):
        pass


class ICSPProc(Proc):
    def __init__(self, port: Port, device: str, firmware: intelhex.Hexfile=None):
        Proc.__init__(self, port)
        self.target = Target(device, firmware)

    def run(self):
        """dispatch incoming commands"""
        while self.ser_avail():
            time.sleep(0.003)

            # command
            c = self.ser_get()
            logging.debug(f'cmd:{c} in: {self.port.inq} out: {self.port.outq}')
    
            # dispatch
            if c == b'K':  # sync
                self.ser_out(b'K')
    
            elif c == b'C':  # send command
                a = self.ser_get()
                self.target.send_cmd(a)
    
            elif c == b'J':  # jump
                num_words = self.ser_get_word()
                
                for _ in range(num_words):
                    self.target.send_cmd(CMD_INC)
    
            elif c == b'F':  # fetch program words
                num_words = self.ser_get_word()
    
                for _ in range(num_words):
                    self.target.send_cmd(CMD_READ_PGM)
                    word = self.target.get_word()
                    self.ser_out(word)
                    self.target.send_cmd(CMD_INC)
    
            elif c == b'G':  # fetch data words
                num_words = self.ser_get_word()
    
                for _ in range(num_words):
                    self.target.send_cmd(CMD_READ_DATA)
                    word = self.target.get_word()
                    self.ser_out(word)
                    self.target.send_cmd(CMD_INC)

            elif c == b'P':  # pause
                time.sleep(0.005)
    
            elif c == b'R':  # read single program word
                w = self.target.get_word()
                self.ser_out(w)
    
            elif c == b'Q':  # query status
                # send TRISA, TRISB, LATA, LATB plus padding 4 x 0xff
                self.ser_out(b'\x00\x00\x00\x00\x00\x00\x00\x00')
    
            elif c == b'L':
                # Low-level functions.  Fetch sub command and assume it's valid
                a = self.ser_get()
                if a in (b'H', b'L', b'P', b'Q'):
                    # these command need no implementation
                    pass
                elif a == b'I':
                    self.target.set_mclr2(False)
                elif a == b'J':
                    self.target.set_mclr2(True)
                elif a == b'M':
                    self.target.set_clk(False)
                elif a == b'N':
                    self.target.set_clk(True)
                elif a == b'O':
                    self.target.set_clk(True)
                    self.target.set_clk(False)
    
            elif c == b'U':  # send byte
                b = self.ser_get()
                self.target.send_byte(b)
    
            elif c == b'W':  # send word
                word = self.ser_get_word()
                self.target.send_arg(word)
    
            elif c == b'V':  # version
                self.ser_out(b'V1.8\n')
    
            elif c == b'Z':  # release
                pass
    
            else:
                self.ser_out(b'E')


class ICSPHost(Port):
    def __init__(self, device: str, firmware):
        Port.__init__(self)
        
        self.proc = ICSPProc(self, device, firmware)

    def reset(self):
        super().reset()
        self.proc.reset()

    def write(self, data: bytes):
        super().write(data)
        self.proc.run()


class AddressError(Exception):
    """Raised when on a restricted address"""

    def __init__(self, address):
        self.address = address


class ChecksumError(Exception):
    """ raised when command checksum does not match """
    def __inir__(self, recv, calc):
        self.recv = recv
        self.calc = calc
        
        
class BLoadProc(Proc):
    """
    ;   Commands:
    ;
    ;   C [CHK]
    ;   Reads a page of config memory, idlocs, chip id, config and calibration words
    ;
    ;   I [CHK]
    ;   Reports bootloader interface version [1 byte], page of bootloader start
    ;   address, page of bootloader end address, and page of start of eeprom address.
    ;   4 bytes total.
    ;
    ;   R [ADR] [CHK]
    ;   Reads a page of flash program memory.  The command is 4 bytes long, 1 byte
    ;   for the command character 'R', two for the address and 1 checksum byte.
    ;   This command returns [DATA] followed by [CHK] (65 bytes total)
    ;
    ;   W [ADR] [DATA] [CHK]
    ;   Writes a page to flash program memory.  The command is 68 bytes long, 1 byte
    ;   for the command character 'W', two for the address, a 64 byte data frame and
    ;   a checksum byte.
    ;
    ;   E [ADR] [CHK]
    ;   Erases a page of flash program memory.  The command is 4 bytes long, 1 byte
    ;   for the command character 'E', two for the address and 1 checksum byte.
    ;
    ;   D [ADR] [DATA] [CHK]
    ;   Write a page of flash data memory.  The command is 68 bytes long, 1 byte
    ;   for the command character 'D', two for the address, a 64 byte data frame and
    ;   a checksum byte.  Hex files generally choose a high address to represent
    ;   data memory but the boot loader expects the address in the low byte of address
    ;   and a zero in the high byte.
    ;
    ;   F [ADR] [CHK]
    ;   Reads a page of flash data memory.  The command is 4 bytes long, 1 byte
    ;   for the command character 'F', two for the address and 1 checksum byte.
    ;   the high byte of the address is ignored.
    ;   This command returns [DATA] followed by [CHK] (65 bytes total)
    ;   Where:
    ;
    ;   T [ADR] [CHK]
    ;   Test address is writable, i.e. not a protected bootloader address  Does not
    ;   test if address is out of range.
    ;   This command responds with the (K) prompt if address is writable and (R) if
    ;   address is restricted.
    ;
    ;   Z
    ;   Resets the processor
    ;
    ;   [ADR] - The address is two bytes long and is sent low byte first.  The range
    ;   of address (for the 16F819) is 0x0000 - 0x07FF for Read and 0x0020 - 0x06FF
    ;   for read and write.
    ;
    ;   [CHK] - A simple checksum of the databytes transmitted for error checking
    ;   When appended to commands the checksum EXCLUDES the first command byte.
    ;
    ;   [DATA] - represents an entire page of flash program memory.  The page is
    ;   organized as 32 low byte/high byte pairs.
    ;
    ;   Return Codes:
    ;   K - Ready to accept the next command
    ;   R - Address range error
    ;   C - Data checksum error
    ;   E - Invalid command
    ;
    ;   When a command complete successfully the 'K' prompt will be all that is
    ;   sent.  There is no success code.  The absense of a R or C error code is
    ;   enough to indicate success.
    ;
    """
    
    BOOT_VERSION = 0x15
    BOOT_PAGESIZE = 0x40
    BOOT_START = 0x680
    BOOT_SIZE = 0x180
    BOOT_END = BOOT_START + BOOT_SIZE - 1

    def __init__(self, port: Port, device_name: str, firmware: intelhex.Hexfile=None):
        Proc.__init__(self, port)
        self.boot_crc = 0
        self.address = 0
        self.boot_data = bytearray(intelhex.PAGEBYTES)
        self.reset_time = 0
        self.running = False
        self.device = picdevice.find_by_name(device_name)
        self.firmware = firmware

    def reset(self):
        """reset ICSP host"""
        self.reset_time = time.time()

    def send_break(self):
        """break handler"""
        self.running = True
        self.ser_out(b'K')

    @property
    def code_end(self):
        return (self.device['max_page'] + 1) * self.BOOT_PAGESIZE // 2 - 1

    @property
    def eeprom_start(self):
        return self.device['min_data'] * self.BOOT_PAGESIZE // 2

    @property
    def eeprom_end(self):
        return self.device['max_data'] * self.BOOT_PAGESIZE // 2 
    
    @property
    def conf_page_num(self):
        return self.device['conf_page']

    def boot_check(self):
        c = self.ser_get()
        if self.boot_crc % 0x100 != c[0]:
            raise ChecksumError(c[0], self.boot_crc)
    
    def boot_address(self):
        self.address = self.ser_get_word()
        self.boot_crc = sum(divmod(self.address, 0x100))

    def boot_range(self):
        """check if address is in range and raise an exception if not"""
        if self.BOOT_START <= self.address < self.BOOT_END:
            raise AddressError(self.address)

    def boot_load_data(self):
        """read a page of data from the host"""
        for idx in range(intelhex.PAGEBYTES):
            byte = self.ser_get()[0]
            self.boot_data[idx] = byte

        self.boot_crc += sum(self.boot_data)

    def calc_crc(self, data: bytes):
        crc = sum(data) % 0x100
         
        return bytes([crc])
        
    def get_page_num(self):
        page_num, word_num = divmod(self.address, intelhex.PAGELEN)
        if word_num != 0:
            raise AddressError

        return page_num

    def boot_info(self):
        """send bootloader info record"""
        info = [
            self.BOOT_VERSION,
            self.BOOT_PAGESIZE // 2,
            *reversed(divmod(self.BOOT_START, 0x100)),
            *reversed(divmod(self.BOOT_SIZE, 0x100)),
            *reversed(divmod(self.eeprom_start, 0x100)),
            *reversed(divmod(self.eeprom_end, 0x100)),
            *reversed(divmod(self.code_end, 0x100)),
            0x0,
            0x0,
            0x0,
            0x0,
        ]

        data = bytes(info)
        self.ser_out(data)
        self.ser_out(self.calc_crc(data))

    def boot_config(self):
        """read config words"""
        page_num = self.conf_page_num
        page = self.firmware[page_num]

        chip_id = (0b10_0111_000 << 5) + 0b0_0101
        page[6] = chip_id
        
        data = page.tobytes(b'\xff\x3f')
        
        self.ser_out(data)
        self.ser_out(self.calc_crc(data))

    def boot_read(self, null):
        """ send program words """
        page_num = self.get_page_num()
        page = self.firmware[page_num]
        
        if page:
            data = page.tobytes(null)
        else:
            data = null * intelhex.PAGELEN
        
        self.ser_out(data)
        self.ser_out(self.calc_crc(data))

    def flash_erase(self):
        """erase program page"""
        page_num = self.get_page_num()

        if self.firmware[page_num]:
            del self.firmware[page_num]

    def flash_write(self):
        """update a firmware page"""
        page_num = self.get_page_num()
        page = intelhex.Page(self.boot_data)

        # Remove NULL words
        for offset in range(0, len(page)):
            if page[offset] == 0xFFFF:
                page[offset] = None

        self.firmware[page_num] = page

    def run(self):
        """dispatch incoming commands"""
        if not self.running:
            return

        while self.ser_avail():
            time.sleep(0.002)

            # command
            c = self.ser_get()
            
            self.boot_crc = 0

            # dispatch
            try:
                if c == b'C':  # read config words
                    self.boot_check()
                    self.boot_config()
                elif c == b'I':  # info
                    self.boot_check()
                    self.boot_info()
                elif c == b'R':  # read program page
                    self.boot_address()
                    self.boot_check()
                    self.boot_read(b'\xff\x3f')
                elif c == b'F':  # read data page
                    self.boot_address()
                    self.boot_check()
                    self.boot_read(b'\xff\x00')
                elif c == b'W':  # write program page
                    self.boot_address()
                    self.boot_load_data()
                    self.boot_check()
                    self.boot_range()
                    self.flash_erase()
                    self.flash_write()
                elif c == b'D':  # write data page
                    self.boot_address()
                    self.boot_load_data()
                    self.boot_check()
                    self.flash_write()
                elif c == b'E':  # erase program page
                    self.boot_address()
                    self.boot_check()
                    self.flash_erase()
                elif c == b'T':  # test address
                    self.boot_info()
                elif c == b'Z':  # reset
                    self.reset()
                    return
                else:
                    self.ser_out(b'E')
            except ChecksumError:
                self.ser_out(b'CK')
                continue

            self.ser_out(b'K')
        

class BLoadHost(Port):
    def __init__(self, device: str, firmware):
        Port.__init__(self)
        
        self.proc = BLoadProc(self, device, firmware)

    def reset(self):
        super().reset()
        self.proc.reset()
        
    def send_break(self, duration: int):
        super().send_break(duration)
        self.proc.send_break()

    def write(self, data: bytes):
        """intercept incoming data and call Proc to process it"""
        super().write(data)

        # Process the data
        self.proc.run()

       
if __name__ == "__main__":
    import pyload
    pyload.run(['--port', 'mock', 'x.hex'])
