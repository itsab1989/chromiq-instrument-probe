"""A stand-in for USBPcapCMD, tcpdump and pktmon in the tests. It never
touches a device. It writes a small capture where the real program would,
then waits until it is stopped.

  fake_recorder.py -d IFACE -o PATH -A ...   like USBPcapCMD: refuses an existing file
  fake_recorder.py ... -w PATH [filter]      like tcpdump
  fake_recorder.py start|stop|status|filter|etl2pcap ...   like pktmon
"""

import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def pcap(linktype=249):
    from synth import UsbPcapWriter
    w = UsbPcapWriter()
    w.describe(3, 0x1234, 0x5678, [(0x81, 2), (0x02, 2)])
    w.bulk_out(3, 0x02, b"FAKE-COMMAND\r")
    return w.pcap()


def main(argv):
    if argv and argv[0] in ("start", "stop", "status", "filter", "etl2pcap"):
        log = os.environ.get("FAKE_PKTMON_LOG")
        if log:
            with open(log, "a") as fh:
                fh.write(" ".join(argv) + "\n")
        if argv[0] == "status":
            print("Packet Monitor is not running.")
        elif argv[0] == "filter":
            print("There are no filters.")
        elif argv[0] == "start":
            etl = argv[argv.index("--file-name") + 1]
            with open(etl, "wb") as fh:
                fh.write(b"ETL")
        elif argv[0] == "etl2pcap":
            out = argv[argv.index("--out") + 1]
            sys.path.insert(0, HERE)
            from synth import DEV_IP, DEV_MAC, HOST_IP, HOST_MAC, NetWriter, eth, tcp
            w = NetWriter()
            w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 5, 5000, b"PKTMON")))
            with open(out, "wb") as fh:
                fh.write(w.pcapng())
        return 0
    if "-o" in argv:                                   # USBPcapCMD
        path = argv[argv.index("-o") + 1]
        if os.path.exists(path):
            print("Thread started with invalid write handle!")
            return 0                                   # (USBPcapCMD ends with 0 even then)
        with open(path, "xb") as fh:
            fh.write(pcap())
            fh.flush()
            while True:
                time.sleep(0.05)
    if "-w" in argv:                                   # tcpdump
        path = argv[argv.index("-w") + 1]
        with open(path, "ab") as fh:
            fh.write(pcap())
            fh.flush()
            while True:
                time.sleep(0.05)
    print("unknown use:", argv)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
