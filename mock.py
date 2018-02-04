"""
Mock icsp interface for testing.  Implements the serial port protocol that can be wrapped in a Comm object.  

Attempting to create a state machine that runs on every call to the serial port read API and reads and writes to and from the input and output queue until the state machine blocks on a serial read for the next icsp command byte.  At that point the inbound request can be satisfied from one of the two queues.

How to do that?  Perhaps this is an example of coroutine programming with yield?  That might simplify the handoff in and out of the state machine.  Not sure how to yield out of the state machine without creating a call chain that goes deeper and deeper.

"""


class ICSP:
    def __init__(self):
        self._dtr = False
        self.open()

    @property
    def in_waiting(self):
        return len(self.inq)

    @property
    def dtr(self):
        return _dtr

    @dtr.setter(self, state: bool):
        if _dtr and not state:
            self.reset()
        _dtr = state

    def read(self, num_bytes: int):
        while len(self.inq) < num_bytes:
            self.run()
            
        ret, self.inq = self.inq[: num_bytes], self.inq[num_bytes:]
        return ret

    def readline(self):
        nl = self.inq.find('\n')
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
            
        ret, self.outq = self.outq[0], self.outq[1:]
        
        return ret

    def ser_out(self, data: bytes):
        self.inq += data

    def reset(self):
        self.ser_out(b'K')
        
    def run(self):
        while True:
            b = self.ser_get()
        
            if b == b'V':
                self.ser_out(b'V1.4\n')
            
            self.ser_out(b'K')
            
            if not self.ser_avail():
                break
