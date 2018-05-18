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
import hexfile


CMD_LOAD_CONFIG = b'\x00'
CMD_LOAD_PGM = b'\x02'
CMD_LOAD_DATA = b'\x03'
CMD_READ_PGM = b'\x04'
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
        self.break_dur = 0
        self.inq = bytes()
        self.outq = bytes()

    @property
    def in_waiting(self):
        return len(self.inq)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, state: bool):
        if self._dtr and not state:
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

    def read(self, num_bytes: int):
        while len(self.inq) < num_bytes:
            self.run()
            
        ret, self.inq = self.inq[: num_bytes], self.inq[num_bytes:]
        # print(f'read: {num_bytes} {ret} in: {self.inq} out: {self.outq}') 
        return ret

    def readline(self):
        if len(self.inq) < 1:
            self.run()
            
        nl = self.inq.find(b'\n')
        if nl < 0:
            ret, self.inq = self.inq, bytes()
        else:
            ret, self.inq = self.inq[: nl + 1], self.inq[nl + 1:]

        return ret
        
    def send_break(self, duration: int):
        self.break_dur = duration
        self.outq = bytes()

    def write(self, data: bytes):
        self.outq += data

    def open(self):
        self.inq = bytes()
        self.outq = bytes()
        self.break_dur = 0
        
    def close(self):
        pass

    def ser_avail(self):
        return self.outq
        
    def ser_get(self):
        if not self.ser_avail():
            raise EOFError

        ret, self.outq = self.outq[:1], self.outq[1:]
        
        print('ser_out in:', self.inq, 'out:', self.outq)
        return ret

    def ser_out(self, data: bytes):
        self.inq += data
        print('ser_out in:', self.inq, 'out:', self.outq)

class ICSP:
    def __init__(self):
        pass

    def reset(self):
        self.ser_out(b'K')
        print('reset in:', self.inq, 'out:', self.outq)
        
    def run(self):
        print('running addr:', hex(self.address), 'in:', self.inq, 'out:', self.outq)
        while self.ser_avail():
            # command
            c = self.ser_get()

            if c == b'K':  # sync
                self.ser_out(b'K')

            elif c == b'C':  # send command
                a = self.ser_get()
                self.icsp_send_cmd(a)

            elif c == b'J':  # jump
                l = self.ser_get()
                h = self.ser_get()
                c = int.from_bytes(l + h, byteorder='little')
                for _ in range(c):
                    self.icsp_send_cmd(CMD_INC)

            elif c == b'F':  # fetch program words
                a = self.ser_get()
                b = self.ser_get()
                num_words = int.from_bytes(a + b, 'little')

                for _ in range(num_words):
                    if self.address == 0x8006:
                        chip_id = (0b10_0111_000 << 5) + 0b0_0101
                        self.ser_out(chip_id.to_bytes(2, 'little'))
                    else:
                        word = self.get_word(self.address)
                        self.ser_out(word)
                    self.address += 1

            elif c == b'G':  # fetch data words
                a = self.ser_get()
                b = self.ser_get()
                num_words = int.from_bytes(a + b, 'little')
                if self.address < 0xF000:
                    self.address = 0xF000

                for _ in range(num_words):
                    self.ser_out(b'\xFF')
                    self.address += 1

            elif c == b'P':  # pause
                time.sleep(0.005)

            elif c == b'R':  # read single program word
                w = self.icsp_read_word()
                self.send_word(w)

            elif c == b'Q':  # query status
                # send TRISA, TRISB, LATA, LATB plus padding 4 x 0xff
                self.serout(b'\x00\x00\x00\x00\x00\x00\x00\x00')

            elif c == b'L':
                # Low-level functions.  Fetch sub command and assume it's valid
                a = self.ser_get()
                if a in (b'H', b'L', b'P', b'Q'):
                    # these command need no implementation
                    pass
                elif a == b'I':
                    self.set_mclr2(False)
                elif a == b'J':
                    self.set_mclr2(True)
                elif a == b'M':
                    self.set_clk(False)
                elif a == b'N':
                    self.set_clk(True)
                elif a == b'O':
                    self.set_clk(True)
                    self.set_clk(False)

            elif c == b'U':  # send byte
                b = self.ser_get()
                self.icsp_send_byte(b)

            elif c == b'W':  # send word
                l = self.ser_get()
                h = self.ser_get()
                w = l + h
                self.icsp_send_word(w)

            elif c == b'V':  # version
                self.ser_out(b'V1.8\n')

            elif c == 'Z':  # release
                pass

            else:
                self.ser_out(b'E')

        # print('done in:', self.inq, 'out:', self.outq)

        
class Target:
    def __init__(self, firmware=None):
        self.firmware = firmware
        self.address = 0
        self.run_state = "HALT"

    def get_word(self, word_address: int):
        """access a two byte firmware word by word address"""
        page_num, word_num = divmod(word_address, hexfile.PAGESIZE // 2)
        byte_num = word_num * 2

        print(word_address, 'pn:', page_num, 'bn:', byte_num, 'wn:', word_num)

        if page_num < len(self.firmware):
            page = bytes(self.firmware[page_num])

            return page[byte_num: byte_num + 2]

    def icsp_send_cmd(self, cmd: bytes):
        # TODO: check run state to ignore commands
        print(f'addr: {self.address} cmd: {cmd}')
        if cmd == CMD_LOAD_CONFIG:
            self.address = 0x8000
        elif cmd == CMD_INC:
            self.address += 1
        elif cmd == CMD_RESET_ADDRESS:
            self.address = 0

    def icsp_send_byte(self, b: bytes):
        pass

    def icsp_send_word(self, w: bytes):
        pass

    def set_mclr2(self, state: bool):
        pass

    def set_clk(self, state: bool):
        pass

class ICSPHost(Port, ICSP, Target):
    def __init__(self, firmware):
        Port.__init__(self)
        ICSP.__init__(self)
        Target.__init__(self, firmware)
