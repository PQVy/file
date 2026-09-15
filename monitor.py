import os
import time
import threading


class InternetUsageMonitor:
    """
    Internet traffic monitor cho Linux/OpenWrt.

    Không cần:
        - tcpdump
        - scapy
        - package ngoài
        - AF_PACKET

    Chỉ đọc kernel interface counters:

        /sys/class/net/<iface>/statistics/rx_bytes
        /sys/class/net/<iface>/statistics/tx_bytes

    Ưu điểm:
        - CPU cực thấp
        - RAM cực thấp
        - Không bắt packet
        - Không parse packet
        - Không lưu IP/port/connection
        - Chạy 24/7 phù hợp
        - Tự tìm interface của default route
    """

    def __init__(
        self,
        interval=10,
        log_file="/mnt/mmcblk0p1/network_usage.log",
        auto_route=True,
        interface=None,
        print_output=False,
    ):

        self.interval = max(5, int(interval))

        self.log_file = log_file

        self.auto_route = auto_route

        # Nếu muốn cố định interface:
        #
        # interface="eth1"
        #
        self.interface = interface

        self.print_output = print_output

        self._stop_event = threading.Event()
        self._thread = None

        self._lock = threading.Lock()

        # Tổng traffic kể từ khi monitor start.
        self._rx_bytes = 0
        self._tx_bytes = 0

        # Packet counters của kernel.
        self._rx_packets = 0
        self._tx_packets = 0

        # Tốc độ hiện tại.
        self._rx_speed = 0
        self._tx_speed = 0

        self._last_rx = None
        self._last_tx = None
        self._last_time = None

        self._route_interface = None

    # =========================================================
    # START
    # =========================================================

    def start(self):

        if self._thread and self._thread.is_alive():
            return False

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._worker,
            name="internet-usage",
            daemon=True,
        )

        self._thread.start()

        return True

    # =========================================================
    # STOP
    # =========================================================

    def stop(self):

        self._stop_event.set()

        if self._thread:

            self._thread.join(
                timeout=2
            )

        self._thread = None

    # =========================================================
    # WORKER
    # =========================================================

    def _worker(self):

        # Xác định interface ban đầu.
        self._update_interface()

        while not self._stop_event.wait(
            self.interval
        ):

            try:

                # Kiểm tra lại route mỗi lần refresh.
                #
                # Nếu eth1 mất và default route chuyển
                # sang wwan0 thì monitor tự chuyển theo.
                self._update_interface()

                self._read_counters()

            except Exception as e:

                self._write_log(
                    "[network] error: %s"
                    % e
                )

    # =========================================================
    # FIND DEFAULT ROUTE
    # =========================================================

    def _find_default_interface(self):

        """
        Đọc:

            /proc/net/route

        để tìm interface của default route.

        Tương đương:

            route

        hoặc:

            ip route
        """

        try:

            with open(
                "/proc/net/route",
                "r",
            ) as f:

                lines = f.readlines()

        except Exception:

            return None

        for line in lines[1:]:

            parts = line.split()

            if len(parts) < 11:
                continue

            iface = parts[0]
            destination = parts[1]
            flags = parts[3]

            # Destination 00000000 = default route.
            if destination != "00000000":
                continue

            try:
                flags_value = int(
                    flags,
                    16
                )
            except ValueError:
                continue

            # RTA_UP = 0x1
            # RTA_GATEWAY = 0x2
            #
            # UG = 0x3
            if not (flags_value & 0x1):
                continue

            if self.interface:
                return self.interface

            return iface

        return None

    # =========================================================
    # UPDATE INTERFACE
    # =========================================================

    def _update_interface(self):

        if self.interface:

            new_interface = self.interface

        elif self.auto_route:

            new_interface = (
                self._find_default_interface()
            )

        else:

            new_interface = None

        if not new_interface:
            return

        if new_interface != self._route_interface:

            old = self._route_interface

            self._route_interface = new_interface

            # Reset baseline khi route thay đổi.
            self._last_rx = None
            self._last_tx = None
            self._last_time = None

            self._write_log(
                "[network] default interface: %s -> %s"
                % (
                    old or "-",
                    new_interface,
                )
            )

    # =========================================================
    # READ KERNEL COUNTERS
    # =========================================================

    def _read_counter(self, name):

        path = (
            "/sys/class/net/%s/statistics/%s"
            % (
                self._route_interface,
                name,
            )
        )

        try:

            with open(
                path,
                "r",
            ) as f:

                return int(
                    f.read().strip()
                )

        except Exception:

            return 0

    # =========================================================
    # READ TRAFFIC
    # =========================================================

    def _read_counters(self):

        interface = self._route_interface

        if not interface:
            return

        rx = self._read_counter(
            "rx_bytes"
        )

        tx = self._read_counter(
            "tx_bytes"
        )

        rx_packets = self._read_counter(
            "rx_packets"
        )

        tx_packets = self._read_counter(
            "tx_packets"
        )

        now = time.monotonic()

        # -----------------------------------------------------
        # First sample
        # -----------------------------------------------------

        if self._last_rx is None:

            self._last_rx = rx
            self._last_tx = tx
            self._last_time = now

            return

        elapsed = now - self._last_time

        if elapsed <= 0:
            elapsed = 1

        # -----------------------------------------------------
        # Delta
        # -----------------------------------------------------

        delta_rx = rx - self._last_rx
        delta_tx = tx - self._last_tx

        # Interface reset / reconnect có thể làm counter
        # nhỏ hơn lần trước.
        if delta_rx < 0:
            delta_rx = 0

        if delta_tx < 0:
            delta_tx = 0

        rx_speed = delta_rx / elapsed
        tx_speed = delta_tx / elapsed

        # -----------------------------------------------------
        # Save
        # -----------------------------------------------------

        with self._lock:

            self._rx_bytes = rx
            self._tx_bytes = tx

            self._rx_packets = rx_packets
            self._tx_packets = tx_packets

            self._rx_speed = rx_speed
            self._tx_speed = tx_speed

        self._last_rx = rx
        self._last_tx = tx
        self._last_time = now

        # -----------------------------------------------------
        # Log
        # -----------------------------------------------------

        self._write_report()

    # =========================================================
    # REPORT
    # =========================================================

    def _write_report(self):

        with self._lock:

            interface = (
                self._route_interface
                or "-"
            )

            rx = self._rx_bytes
            tx = self._tx_bytes

            rx_packets = self._rx_packets
            tx_packets = self._tx_packets

            rx_speed = self._rx_speed
            tx_speed = self._tx_speed

        now = time.strftime(
            "%H:%M:%S"
        )

        text = (
            "\n"
            "[%s] INTERNET USAGE\n"
            "-----------------------------------------\n"
            "Interface  %s\n"
            "\n"
            "IN         %s\n"
            "OUT        %s\n"
            "\n"
            "Speed IN   %s/s\n"
            "Speed OUT  %s/s\n"
            "\n"
            "Packets IN   %d\n"
            "Packets OUT  %d\n"
            "-----------------------------------------\n"
            % (
                now,
                interface,
                self._format_bytes(rx),
                self._format_bytes(tx),
                self._format_bytes(rx_speed),
                self._format_bytes(tx_speed),
                rx_packets,
                tx_packets,
            )
        )

        if self.print_output:
            print(
                text,
                flush=True
            )

        self._write_log(text)

    # =========================================================
    # GET STATS
    # =========================================================

    def get_stats(self):

        with self._lock:

            return {
                "interface": (
                    self._route_interface
                ),
                "rx_bytes": self._rx_bytes,
                "tx_bytes": self._tx_bytes,
                "rx_packets": self._rx_packets,
                "tx_packets": self._tx_packets,
                "rx_speed": self._rx_speed,
                "tx_speed": self._tx_speed,
            }

    # =========================================================
    # LOG
    # =========================================================

    def _write_log(self, text):

        if not self.log_file:
            return

        try:

            directory = os.path.dirname(
                self.log_file
            )

            if directory:
                os.makedirs(
                    directory,
                    exist_ok=True,
                )

            with open(
                self.log_file,
                "a",
                encoding="utf-8",
            ) as f:

                f.write(text)

        except Exception:
            # Logging không được phép ảnh hưởng MGWP.
            pass

    # =========================================================
    # FORMAT
    # =========================================================

    @staticmethod
    def _format_bytes(value):

        value = float(value)

        units = (
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        )

        for unit in units:

            if value < 1024:
                return "%.2f %s" % (
                    value,
                    unit,
                )

            value /= 1024

        return "%.2f PB" % value



# network_monitor = InternetUsageMonitor(
#     interval=10,
#     auto_route=True,
#     log_file="/mnt/mmcblk0p1/network_usage.log",
#     print_output=False,
# )

# network_monitor.start()

if __name__ == "__main__":

    monitor = InternetUsageMonitor(
        interval=5,
        auto_route=True,
        log_file="/tmp/network_usage.log",
        print_output=True,
    )

    print("Starting Internet Usage Monitor...")
    print("Press Ctrl+C to stop.")

    monitor.start()

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        monitor.stop()
        print("Stopped.")