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
    def __init__(self, port, baud=9600, data=8, timeout=1.0, logf=None):
        # self.ser = serial.serial_for_url(port)
        self.ser = serial(port)
        self.ser.baudrate = baud
        self.ser.bytesize = data
        self.set_timeout(timeout)

        self.log_filename = logf
        if self.log_filename and os.path.exists(self.log_filename):
            os.unlink(self.log_filename)

        # print('timeout', ser.timeout)
        # print('xonxoff', ser.xonxoff)
        # print('rtscts', ser.rtscts)
        # print('dsrdtr', ser.dsrdtr)

        self.read_count = 0
        self.write_count = 0

    def set_timeout(self, timeout):
        self.ser.timeout = timeout

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
        if self.log_filename:
            # log the data
            with open(self.log_filename, 'a') as log:
                log.write("%8.3f %s %3d : " % (0, desc, len(data)))
                for c in data:
                    if ord(' ') <= c <= ord('~'):
                        log.write("%02x[%s] " % (c, chr(c)))
                    else:
                        log.write("%02x " % c)

                log.write("\n")

    def close(self):
        self.ser.close()
        self.ser = None

        if self.log_filename:
            with open(self.log_filename, 'a') as log:
                log.write("\nbytes read: {} bytes writen: {}".format(
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

