# -------------------------------------------------------------------------------
#
# $Id: comm.py 787 2018-01-14 15:33:52Z rnee $
#
# Serial port comm routines
#
# -------------------------------------------------------------------------------

# import serial
import time
import os


class serial:
    def __init__(self, port: str):
        self.port = port
        self.in_waiting = 0

    def read(self, num_bytes: int):
        return b'\x45' * num_bytes

    def readline(self):
        return '123\n'

    def send_break(duration: int):
        time.sleep(duration)

    def write(self, data):
        pass

    def close(self):
        pass


class Comm:
    def __init__(self, ser, logf=None):
        self.ser = ser
        self.logf = logf

        # print('timeout', ser.timeout)
        # print('xonxoff', ser.xonxoff)
        # print('rtscts', ser.rtscts)
        # print('dsrdtr', ser.dsrdtr)

        self.read_count = 0
        self.write_count = 0

    def read(self, request=None):
        """ read a requested number of bytes.  If request is missing or zero read available """
        if not request:
            request = self.avail()

        data = self.ser.read(request)
        total = len(data)

        self.read_count += total

        if total > 0:
            self.log(data, "READ")

        return total, data

    def read_line(self):
        data = self.ser.readline()

        self.log(data, "RDLN")

        return data

    def write(self, data):
        self.ser.write(data)

        self.write_count += len(data)

        self.log(data, "WRIT")

    def avail(self):
        """ return number of bytes available to read """
        return self.ser.in_waiting

    def flush(self):
        waiting = self.avail()
        if waiting > 0:
            (count, data) = self.read(waiting)
            self.log(data, "DISC")

    def log(self, data, desc):
        if self.logf:
            self.logf.write("%8.3f %s %3d : " % (0, desc, len(data)))
            for c in data:
                if ord(' ') <= c <= ord('~'):
                    self.logf.write("%02x[%s] " % (c, chr(c)))
                else:
                    self.logf.write("%02x " % c)
    
            self.logf.write("\n")

    def close(self):
        self.ser.close()
        self.ser = None

        if self.logf:
            self.logf.write("\nbytes read: {} bytes writen: {}".format(
                self.read_count, self.write_count))

    def dtr_active(self, state):
        self.ser.dtr = state
        self.log(b'high' if state else b'low', "ADTR")

    def pulse_dtr(self, duration):
        self.ser.dtr = True
        time.sleep(duration / 1000.0)
        self.ser.dtr = False

        self.log(bytes("{0}".format(duration), 'utf-8'), "PDTR")

    def pulse_break(self, duration):
        self.ser.send_break(duration / 1000.0)

        self.log(bytes("{0}".format(duration), 'utf-8'), "PBRK")

