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
import intelhex


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
        """read data from inq"""
        if len(self.inq) < num_bytes:
            print(f'read: {num_bytes} in: {self.inq} out: {self.outq}')
            raise EOFError
            
        ret, self.inq = self.inq[: num_bytes], self.inq[num_bytes:]
        # print(f'read: {num_bytes} {ret} in: {self.inq} out: {self.outq}')
        return ret

    def readline(self):
        if len(self.inq) < 1:
            print(f'readline: in: {self.inq} out: {self.outq}')
            raise EOFError

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
        print(f'write: {data} in: {self.inq} out: {self.outq}')
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
        # read a byte from outq
        if not self.ser_avail():
            raise EOFError

        ret, self.outq = self.outq[:1], self.outq[1:]
        return ret

    def ser_out(self, data: bytes):
        # add bytes to the inq
        self.inq += data


class ICSP:
    def __init__(self, port: Port, firmware: intelhex.Hexfile=None):
        self.port = port
        self.target = Target(firmware)

    def reset(self):
        """reset ICSP host"""
        self.ser_out(b'K')
        print('reset in:', self.port.inq, 'out:', self.port.outq)
        
    def run(self):
        """dispatch incoming commands"""
        # command
        c = self.ser_get()
        print(f'cmd:{c} addr: {hex(self.address)} in: {self.port.inq} out: {self.port.outq}')

        # dispatch
        if c == b'K':  # sync
            self.ser_out(b'K')

        elif c == b'C':  # send command
            a = self.ser_get()
            self.target.icsp_send_cmd(a)

        elif c == b'J':  # jump
            low = self.ser_get()
            high = self.ser_get()
            c = int.from_bytes(low + high, byteorder='little')
            for _ in range(c):
                self.target.icsp_send_cmd(CMD_INC)

        elif c == b'F':  # fetch program words
            a = self.ser_get()
            b = self.ser_get()
            num_words = int.from_bytes(a + b, 'little')

            # TODO: move this to Target
            for _ in range(num_words):
                if self.address == 0x8006:
                    chip_id = (0b10_0111_000 << 5) + 0b0_0101
                    self.ser_out(chip_id.to_bytes(2, 'little'))
                else:
                    word = self.target.icsp_read_word(self.address)
                    self.ser_out(word if word else b'\xff\x3f')
                self.address += 1

        elif c == b'G':  # fetch data words
            a = self.ser_get()
            b = self.ser_get()
            num_words = int.from_bytes(a + b, 'little')
            # TODO: move address set/get to Target
            if self.address < 0xF000:
                self.address = 0xF000

            for _ in range(num_words):
                self.ser_out(b'\xFF\x00')
                self.address += 1

        elif c == b'P':  # pause
            time.sleep(0.005)

        elif c == b'R':  # read single program word
            w = self.target.icsp_read_word()
            self.target.icsp_send_word(w)

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
            self.target.icsp_send_byte(b)

        elif c == b'W':  # send word
            low = self.ser_get()
            high = self.ser_get()
            word = low + high
            self.target.icsp_send_word(word)

        elif c == b'V':  # version
            self.ser_out(b'V1.8\n')

        elif c == b'Z':  # release
            pass

        else:
            self.ser_out(b'E')

    def ser_get(self):
        return self.port.ser_get()

    def ser_out(self, data: bytes):
        self.port.ser_out(data)

        # process the new data
        while self.port.ser_avail():
            self.run()


class Target:
    def __init__(self, firmware):
        self.firmware = firmware
        self.word_address = 0
        self.run_state = "HALT"

    def icsp_read_word(self):
        """access a two byte firmware word by word address"""
        page_num, word_num = divmod(self.word_address, intelhex.PAGELEN // 2)
        byte_num = word_num * 2

        page = self.firmware[page_num]
        if page:
            data = bytes(page)
            return data[byte_num: byte_num + 2]

    def icsp_send_cmd(self, cmd: bytes):
        # TODO: check run state to ignore commands
        if cmd == CMD_LOAD_CONFIG:
            self.word_address = 0x8000
        elif cmd == CMD_INC:
            self.word_address += 1
        elif cmd == CMD_RESET_ADDRESS:
            self.word_address = 0

    def icsp_send_byte(self, b: bytes):
        pass

    def icsp_send_word(self, w: bytes):
        pass

    def set_mclr2(self, state: bool):
        pass

    def set_clk(self, state: bool):
        pass


class ICSPHost(Port):
    def __init__(self, firmware):
        Port.__init__(self)
        
        self.host = ICSP(self, firmware)
        
    def reset(self):
        self.host.reset()
