
#!/usr/bin/env python3

import binascii

import serial
import time
import re
import json
import argparse


# ============================================================
# CONFIG
# ============================================================

PORT = "/dev/ttyUSB1"
BAUDRATE = 115200


# ============================================================
# SMS TRA CỨU DATA
#
# Điền số điện thoại + nội dung SMS tương ứng.
#
# Ví dụ:
#
# "viettel": {
#     "number": "191",
#     "message": "KTTB"
# }
#
# Hãy thay bằng cú pháp bạn đang sử dụng thực tế.
# ============================================================

DATA_CHECK_SMS = {

    "viettel": {
        "number": "191",
        "message": "KTTK",
    },

    "mobifone": {
        "number": "9199",
        "message": "KT ALL",
    },

    "vinaphone": {
        "number": "888",
        "message": "DATA",
    },
}


# ============================================================
# MCC / MNC
# ============================================================

OPERATORS = {

    # Viettel
    "45204": "viettel",

    # MobiFone
    "45201": "mobifone",

    # VinaPhone
    "45202": "vinaphone",
}


# ============================================================
# AT MODEM
# ============================================================

class ATModem:

    def __init__(
        self,
        port,
        baudrate=115200,
        timeout=2,
        retries=2
    ):

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.retries = retries

        self.ser = None

    # --------------------------------------------------------
    # OPEN
    # --------------------------------------------------------

    def open(self):

        print(
            f"[MODEM] Opening {self.port} ..."
        )

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
            write_timeout=self.timeout
        )

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        time.sleep(0.5)

        print(
            "[MODEM] Port opened"
        )

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    def close(self):

        if self.ser and self.ser.is_open:

            self.ser.close()

            print(
                "[MODEM] Port closed"
            )

    # --------------------------------------------------------
    # AT COMMAND
    # --------------------------------------------------------

    def command(
        self,
        cmd,
        timeout=None,
        debug=True
    ):
        """
        Gửi AT command và đọc response.

        Kết thúc khi nhận:
            OK
            ERROR
            +CME ERROR
        """

        if not self.ser or not self.ser.is_open:

            raise RuntimeError(
                "Serial port chưa được mở"
            )

        timeout = timeout or self.timeout

        for attempt in range(
            self.retries + 1
        ):

            if debug:

                print(
                    f"\n[AT] >> {cmd}"
                )

            self.ser.reset_input_buffer()

            self.ser.write(
                (cmd + "\r").encode()
            )

            self.ser.flush()

            start = time.time()

            response = ""

            while (
                time.time() - start
                < timeout
            ):

                data = self.ser.readline()

                if not data:
                    continue

                text = data.decode(
                    "utf-8",
                    errors="ignore"
                )

                response += text

                if debug:

                    print(
                        "[AT] <<",
                        repr(text.strip())
                    )

                # --------------------------------------------
                # Command completed
                # --------------------------------------------

                if (
                    "\r\nOK\r\n" in response
                    or response.endswith("\nOK")
                ):
                    break

                if (
                    "\r\nERROR\r\n" in response
                    or response.endswith("\nERROR")
                ):
                    break

                if "+CME ERROR:" in response:
                    break

            response = response.strip()

            if response:

                return response

            # Retry

            if attempt < self.retries:

                print(
                    f"[AT] Retry {attempt + 1}"
                )

                time.sleep(0.5)

        return response

    # --------------------------------------------------------
    # AT
    # --------------------------------------------------------

    def is_alive(self):

        response = self.command(
            "AT",
            timeout=2
        )

        return (
            response == "OK"
            or response.endswith("OK")
        )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    def get_model(self):

        return self.command(
            "ATI",
            timeout=5
        )

    # --------------------------------------------------------
    # IMEI
    # --------------------------------------------------------

    def get_imei(self):

        response = self.command(
            "AT+CGSN",
            timeout=5
        )

        for line in response.splitlines():

            line = line.strip()

            if re.fullmatch(
                r"\d{10,20}",
                line
            ):

                return line

        return None

    # --------------------------------------------------------
    # IMSI
    # --------------------------------------------------------

    def get_imsi(self):

        response = self.command(
            "AT+CIMI",
            timeout=5
        )

        for line in response.splitlines():

            line = line.strip()

            if re.fullmatch(
                r"\d{10,20}",
                line
            ):

                return line

        return None

    # --------------------------------------------------------
    # SIM STATUS
    # --------------------------------------------------------

    def get_sim_status(self):

        response = self.command(
            "AT+CPIN?",
            timeout=5
        )

        if "+CPIN: READY" in response:

            return "READY"

        if "+CPIN: SIM PIN" in response:

            return "SIM_PIN"

        if "+CPIN: SIM PUK" in response:

            return "SIM_PUK"

        return "UNKNOWN"

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    def get_signal(self):

        response = self.command(
            "AT+CSQ",
            timeout=5
        )

        match = re.search(
            r"\+CSQ:\s*(\d+),(\d+)",
            response
        )

        if not match:

            return None

        rssi = int(
            match.group(1)
        )

        ber = int(
            match.group(2)
        )

        # RSSI 99 = unknown

        if rssi == 99:

            dbm = None

        else:

            dbm = -113 + (
                2 * rssi
            )

        return {
            "rssi": rssi,
            "dbm": dbm,
            "ber": ber
        }

    # --------------------------------------------------------
    # OPERATOR
    # --------------------------------------------------------

    def get_operator(self):

        response = self.command(
            "AT+COPS?",
            timeout=10
        )

        match = re.search(
            r'\+COPS:\s*\d+,\s*\d+,\s*"([^"]+)"',
            response
        )

        if match:

            return match.group(1)

        return None

    # --------------------------------------------------------
    # OPERATOR NUMERIC
    # --------------------------------------------------------

    def get_operator_numeric(self):

        response = self.command(
            "AT+COPS?",
            timeout=10
        )

        match = re.search(
            r'\+COPS:\s*\d+,\s*\d+,\s*"(\d+)"',
            response
        )

        if match:

            return match.group(1)

        return None

    # --------------------------------------------------------
    # NETWORK REGISTRATION
    # --------------------------------------------------------

    def get_registration(self):

        response = self.command(
            "AT+CREG?",
            timeout=5
        )

        match = re.search(
            r"\+CREG:\s*\d+,(\d+)",
            response
        )

        if not match:

            return "UNKNOWN"

        status = int(
            match.group(1)
        )

        return {
            0: "NOT_REGISTERED",
            1: "REGISTERED_HOME",
            2: "SEARCHING",
            3: "REGISTRATION_DENIED",
            4: "UNKNOWN",
            5: "REGISTERED_ROAMING",
        }.get(
            status,
            "UNKNOWN"
        )

    # --------------------------------------------------------
    # PACKET REGISTRATION
    # --------------------------------------------------------

    def get_packet_registration(self):

        response = self.command(
            "AT+CGREG?",
            timeout=5
        )

        match = re.search(
            r"\+CGREG:\s*\d+,(\d+)",
            response
        )

        if not match:

            return "UNKNOWN"

        status = int(
            match.group(1)
        )

        return {
            0: "NOT_REGISTERED",
            1: "REGISTERED_HOME",
            2: "SEARCHING",
            3: "REGISTRATION_DENIED",
            4: "UNKNOWN",
            5: "REGISTERED_ROAMING",
        }.get(
            status,
            "UNKNOWN"
        )

    # --------------------------------------------------------
    # DATA ATTACH
    # --------------------------------------------------------

    def get_attach_status(self):

        response = self.command(
            "AT+CGATT?",
            timeout=5
        )

        match = re.search(
            r"\+CGATT:\s*(\d+)",
            response
        )

        if not match:

            return None

        return int(
            match.group(1)
        ) == 1

    # --------------------------------------------------------
    # PDP CONTEXT
    # --------------------------------------------------------

    def get_pdp_context(self):

        return self.command(
            "AT+CGDCONT?",
            timeout=5
        )

    # --------------------------------------------------------
    # PDP ACTIVE
    # --------------------------------------------------------

    def get_pdp_active(self):

        return self.command(
            "AT+CGACT?",
            timeout=5
        )


# ============================================================
# DETECT OPERATOR
# ============================================================

def detect_operator(imsi):

    if not imsi:

        return "unknown"

    if len(imsi) < 5:

        return "unknown"

    mcc_mnc = imsi[:5]

    return OPERATORS.get(
        mcc_mnc,
        "unknown"
    )


# ============================================================
# SMS SETUP
# ============================================================

def setup_sms(modem):

    print(
        "\n[SMS] Configuring SMS text mode"
    )

    modem.command(
        "AT+CMGF=1",
        timeout=5
    )

    modem.command(
        'AT+CPMS="SM","SM","SM"',
        timeout=5
    )


# ============================================================
# SEND SMS
# ============================================================

def send_sms(
    modem,
    phone_number,
    message
):

    if not phone_number:

        print(
            "[SMS] Phone number is empty"
        )

        return False

    print(
        f"[SMS] Sending SMS to {phone_number}"
    )

    modem.ser.reset_input_buffer()

    # --------------------------------------------------------
    # Text mode
    # --------------------------------------------------------

    modem.ser.write(
        b"AT+CMGF=1\r"
    )

    modem.ser.flush()

    time.sleep(0.5)

    modem.ser.read_all()

    # --------------------------------------------------------
    # CMGS
    # --------------------------------------------------------

    modem.ser.write(
        f'AT+CMGS="{phone_number}"\r'.encode()
    )

    modem.ser.flush()

    # --------------------------------------------------------
    # Wait >
    # --------------------------------------------------------

    start = time.time()

    prompt = ""

    while (
        time.time() - start
        < 5
    ):

        data = modem.ser.read(1)

        if not data:

            continue

        text = data.decode(
            "utf-8",
            errors="ignore"
        )

        prompt += text

        if ">" in prompt:

            break

    if ">" not in prompt:

        print(
            "[SMS] No > prompt"
        )

        print(
            "[SMS] Response:",
            repr(prompt)
        )

        return False

    # --------------------------------------------------------
    # Send message
    # --------------------------------------------------------

    modem.ser.write(
        message.encode()
    )

    # Ctrl + Z
    modem.ser.write(
        b"\x1A"
    )

    modem.ser.flush()

    # --------------------------------------------------------
    # Wait result
    # --------------------------------------------------------

    start = time.time()

    response = ""

    while (
        time.time() - start
        < 30
    ):

        data = modem.ser.readline()

        if not data:

            continue

        text = data.decode(
            "utf-8",
            errors="ignore"
        )

        response += text

        print(
            "[SMS] <<",
            repr(text.strip())
        )

        if "OK" in response:

            print(
                "[SMS] SMS sent successfully"
            )

            return True

        if "ERROR" in response:

            print(
                "[SMS] SMS send failed"
            )

            return False

    print(
        "[SMS] Timeout"
    )

    return False


# ============================================================
# WAIT SMS
# ============================================================

def wait_for_sms(
    modem,
    duration=60
):

    print(
        f"\n[SMS] Waiting for SMS "
        f"({duration}s)..."
    )

    # --------------------------------------------------------
    # New SMS direct to TE
    # --------------------------------------------------------

    modem.command(
        "AT+CNMI=2,2,0,0,0",
        timeout=5
    )

    start = time.time()

    sender = None

    message_lines = []

    receiving_sms = False

    while (
        time.time() - start
        < duration
    ):

        line = modem.ser.readline()

        if not line:

            continue

        text = line.decode(
            "utf-8",
            errors="ignore"
        ).strip()

        if not text:

            continue

        print(
            "[SMS] <<",
            text
        )

        # ====================================================
        # SMS HEADER
        # ====================================================

        if text.startswith("+CMT:"):

            match = re.search(
                r'\+CMT:\s*"([^"]+)"',
                text
            )

            if match:

                sender = match.group(1)

            message_lines = []

            receiving_sms = True

            continue

        # ====================================================
        # SMS CONTENT
        # ====================================================

        if receiving_sms:

            if text == "OK":

                continue

            message_lines.append(
                text
            )

            # ------------------------------------------------
            # Đọc tiếp dữ liệu đang có trong serial buffer
            # ------------------------------------------------

            last_data_time = time.time()

            while (
                time.time() - last_data_time
                < 1.0
            ):

                if not modem.ser.in_waiting:

                    time.sleep(0.05)

                    continue

                extra = modem.ser.readline()

                if not extra:

                    continue

                extra_text = extra.decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if not extra_text:

                    continue

                print(
                    "[SMS] <<",
                    extra_text
                )

                last_data_time = time.time()

                if extra_text == "OK":

                    continue

                # Nếu có +CMT mới thì không đưa vào
                # message hiện tại

                if extra_text.startswith("+CMT:"):

                    break

                message_lines.append(
                    extra_text
                )

            # ------------------------------------------------
            # Ghép message
            # ------------------------------------------------

            message = "\n".join(
                message_lines
            ).strip()

            # ------------------------------------------------
            # Chuẩn hóa CR/LF
            # ------------------------------------------------

            message = message.replace(
                "\r",
                ""
            )

            message = re.sub(
                r"\n{3,}",
                "\n\n",
                message
            )

            # ------------------------------------------------
            # Result
            # ------------------------------------------------

            return {
                "sender": sender,
                "message": message
            }

    print(
        "[SMS] Timeout"
    )

    return None


# ============================================================
# PARSE VIETTEL
# ============================================================

def parse_viettel_data_sms(
    message
):

    result = {
        "data_remaining": None,
        "data_unit": None,
        "expiry": None,
    }

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(GB|MB|KB)",
        message,
        re.IGNORECASE
    )

    if match:

        value = match.group(1)

        value = value.replace(
            ",",
            "."
        )

        result["data_remaining"] = float(
            value
        )

        result["data_unit"] = (
            match.group(2).upper()
        )

    # --------------------------------------------------------
    # Expiry
    # --------------------------------------------------------

    match = re.search(
        r"(?:Han su dung|HSD|het han|den ngay)"
        r"\s*:?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        message,
        re.IGNORECASE
    )

    if match:

        result["expiry"] = (
            match.group(1)
        )

    return result


# ============================================================
# GENERIC DATA PARSER
# ============================================================

def parse_data_sms(
    operator,
    sender,
    message
):

    result = {
        "operator": operator,
        "sender": sender,
        "data_remaining": None,
        "data_unit": None,
        "expiry": None,
        "raw_message": message,
    }

    # KIỂM TRA VÀ TỰ ĐỘNG GIẢI MÃ NẾU LÀ TIN NHẮN MÃ HÓA PDU HEX
    actual_message = message
    if is_hex_pdu(message):
        actual_message = decode_pdu(message)
        # Cập nhật lại tin nhắn đã giải mã vào kết quả nếu muốn log
        result["decoded_message"] = actual_message 

    # ========================================================
    # VIETTEL
    # ========================================================

    if operator == "viettel":

        parsed = parse_viettel_data_sms(
            message
        )

        result.update(
            parsed
        )

    # ========================================================
    # MOBIFONE
    # ========================================================

    elif operator == "mobifone":

        match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(GB|MB|KB)",
            message,
            re.IGNORECASE
        )

        if match:

            result["data_remaining"] = float(
                match.group(1).replace(
                    ",",
                    "."
                )
            )

            result["data_unit"] = (
                match.group(2).upper()
            )

    # ========================================================
    # VINAPHONE
    # ========================================================

    elif operator == "vinaphone":

        match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(GB|MB|KB)",
            message,
            re.IGNORECASE
        )

        if match:

            result["data_remaining"] = float(
                match.group(1).replace(
                    ",",
                    "."
                )
            )

            result["data_unit"] = (
                match.group(2).upper()
            )

    return result


def is_hex_pdu(s):
    """
    Kiểm tra xem chuỗi có phải là chuỗi mã hóa PDU Hex không.
    Dấu hiệu: Chỉ chứa ký tự hex, độ dài chẵn và thường lớn hơn 20 ký tự.
    """
    if not isinstance(s, str):
        return False
    s = s.strip()
    # PDU hex chỉ chứa ký tự 0-9, a-f, A-F và độ dài phải là số chẵn
    if not re.match(r'^[0-9a-fA-F]+\$', s) or len(s) % 2 != 0:
        return False
    # Tin nhắn SMS PDU thường dài (ít nhất > 20 ký tự để chứa header và nội dung)
    return len(s) > 20


def decode_pdu(pdu_hex):
    """
    Giải mã chuỗi PDU Hex thô thành văn bản chữ đọc được.
    Hỗ trợ tự động nhận diện bảng mã UCS2 hoặc GSM 7-bit.
    """
    try:
        pdu_bytes = binascii.unhexlify(pdu_hex.strip())
        
        # 1. Bỏ qua phần SMSC (Trung tâm nhắn tin)
        smsc_len = pdu_bytes[0]
        cursor = 1 + smsc_len # Nhảy qua SMSC
        
        # 2. Bỏ qua First octet của SMS-DELIVER
        cursor += 1 
        
        # 3. Bỏ qua Số điện thoại người gửi (Sender Address)
        sender_len = pdu_bytes[cursor]
        # Số byte của số điện thoại = (độ dài số + 1) // 2 + 1 (byte định dạng số)
        sender_bytes_len = ((sender_len + 1) // 2) + 1 
        cursor += 1 + sender_bytes_len
        
        # 4. Bỏ qua Protocol Identifier (TP-PID) và Data Coding Scheme (TP-DCS)
        tp_pid = pdu_bytes[cursor]
        tp_dcs = pdu_bytes[cursor + 1]
        cursor += 2
        
        # 5. Bỏ qua Service Centre Time Stamp (TP-SCTS) - 7 bytes
        cursor += 7
        
        # 6. Đọc độ dài nội dung (User Data Length)
        user_data_len = pdu_bytes[cursor]
        cursor += 1
        
        # Lấy phần data thô còn lại
        user_data = pdu_bytes[cursor:]
        
        # 7. Giải mã dựa trên TP-DCS (Data Coding Scheme)
        # Nếu dcs == 0x08 hoặc các byte dữ liệu chứa ký tự null phổ biến của UCS2
        if tp_dcs == 0x08 or tp_dcs & 0x0C == 0x08:
            # Mã hóa UCS2 (UTF-16 Big Endian)
            return user_data[:user_data_len * 2].decode('utf-16-be', errors='ignore')
        else:
            # Mặc định thử giải mã theo GSM 7-bit nếu không phải UCS2
            # (Hoặc bạn có thể thêm logic unpack 7-bit septets ở đây nếu cần)
            return user_data.decode('utf-8', errors='ignore')
            
    except Exception as ex:
        # Nếu giải mã PDU lỗi, trả về chuỗi gốc để tránh crash
        print(ex)
        return pdu_hex


# ============================================================
# CHECK DATA
# ============================================================

def check_data(
    modem,
    operator
):

    config = DATA_CHECK_SMS.get(
        operator
    )

    if not config:

        print(
            f"[DATA] Unsupported operator: "
            f"{operator}"
        )

        return None

    number = config["number"]

    message = config["message"]

    if not number or not message:

        print(
            f"[DATA] SMS config missing "
            f"for {operator}"
        )

        return None

    # --------------------------------------------------------
    # SMS setup
    # --------------------------------------------------------

    setup_sms(
        modem
    )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    success = send_sms(
        modem,
        number,
        message
    )

    if not success:

        return None

    # --------------------------------------------------------
    # Wait response
    # --------------------------------------------------------

    sms = wait_for_sms(
        modem,
        duration=60
    )

    if not sms:

        return None

    # --------------------------------------------------------
    # Parse
    # --------------------------------------------------------

    result = parse_data_sms(
        operator=operator,
        sender=sms["sender"],
        message=sms["message"]
    )

    return result


# ============================================================
# CHECK SIM
# ============================================================

def check_sim(modem):

    result = {

        "alive": False,

        "model": None,

        "imei": None,

        "imsi": None,

        "sim_status": None,

        "operator": None,

        "operator_numeric": None,

        "signal": None,

        "registration": None,

        "packet_registration": None,

        "attached": None,

        "pdp_context": None,

        "pdp_active": None,
    }

    # --------------------------------------------------------
    # Modem
    # --------------------------------------------------------

    result["alive"] = (
        modem.is_alive()
    )

    if not result["alive"]:

        print(
            "[ERROR] Modem không phản hồi"
        )

        return result

    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------

    result["model"] = (
        modem.get_model()
    )

    # --------------------------------------------------------
    # IMEI
    # --------------------------------------------------------

    result["imei"] = (
        modem.get_imei()
    )

    # --------------------------------------------------------
    # SIM
    # --------------------------------------------------------

    result["sim_status"] = (
        modem.get_sim_status()
    )

    if result["sim_status"] != "READY":

        print(
            "[SIM] SIM chưa READY"
        )

        return result

    # --------------------------------------------------------
    # IMSI
    # --------------------------------------------------------

    result["imsi"] = (
        modem.get_imsi()
    )

    # --------------------------------------------------------
    # Operator
    # --------------------------------------------------------

    result["operator_numeric"] = (
        modem.get_operator_numeric()
    )

    result["operator"] = (
        detect_operator(
            result["imsi"]
        )
    )

    # --------------------------------------------------------
    # Signal
    # --------------------------------------------------------

    result["signal"] = (
        modem.get_signal()
    )

    # --------------------------------------------------------
    # Registration
    # --------------------------------------------------------

    result["registration"] = (
        modem.get_registration()
    )

    result["packet_registration"] = (
        modem.get_packet_registration()
    )

    # --------------------------------------------------------
    # Data attach
    # --------------------------------------------------------

    result["attached"] = (
        modem.get_attach_status()
    )

    # --------------------------------------------------------
    # PDP
    # --------------------------------------------------------

    result["pdp_context"] = (
        modem.get_pdp_context()
    )

    result["pdp_active"] = (
        modem.get_pdp_active()
    )

    return result


# ============================================================
# PRINT MODEM RESULT
# ============================================================

def print_modem_result(result):

    print()

    print(
        "=" * 60
    )

    print(
        "SIM / MODEM INFORMATION"
    )

    print(
        "=" * 60
    )

    print(
        "Modem alive        :",
        result["alive"]
    )

    print(
        "Model              :",
        result["model"]
    )

    print(
        "IMEI               :",
        result["imei"]
    )

    print(
        "IMSI               :",
        result["imsi"]
    )

    print(
        "SIM status         :",
        result["sim_status"]
    )

    print(
        "Operator           :",
        result["operator"]
    )

    print(
        "Operator MCC/MNC   :",
        result["operator_numeric"]
    )

    print(
        "Signal             :",
        result["signal"]
    )

    print(
        "Registration       :",
        result["registration"]
    )

    print(
        "Packet registration:",
        result["packet_registration"]
    )

    print(
        "Data attached      :",
        result["attached"]
    )

    print(
        "PDP context        :",
        result["pdp_context"]
    )

    print(
        "PDP active         :",
        result["pdp_active"]
    )

    print(
        "=" * 60
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Check SIM operator and "
            "data package via SMS"
        )
    )

    parser.add_argument(
        "--port",
        default=PORT,
        help="Serial port"
    )

    parser.add_argument(
        "--baudrate",
        type=int,
        default=BAUDRATE
    )

    parser.add_argument(
        "--no-sms",
        action="store_true",
        help="Không gửi SMS kiểm tra data"
    )

    args = parser.parse_args()

    modem = ATModem(
        port=args.port,
        baudrate=args.baudrate,
        timeout=2,
        retries=2
    )

    try:

        # ====================================================
        # OPEN MODEM
        # ====================================================

        modem.open()

        # ====================================================
        # CHECK SIM
        # ====================================================

        sim_result = check_sim(
            modem
        )

        print_modem_result(
            sim_result
        )

        # ====================================================
        # CHECK DATA
        # ====================================================

        if (
            sim_result["sim_status"] == "READY"
            and sim_result["operator"] != "unknown"
            and not args.no_sms
        ):

            operator = (
                sim_result["operator"]
            )

            print(
                "\n[DATA] Detected operator:",
                operator
            )

            data_result = check_data(
                modem,
                operator
            )

            if data_result:

                print()

                print(
                    "=" * 60
                )

                print(
                    "DATA JSON"
                )

                print(
                    "=" * 60
                )

                print(
                    json.dumps(
                        data_result,
                        ensure_ascii=False,
                        indent=4
                    )
                )

                print(
                    "=" * 60
                )

        else:

            print(
                "\n[DATA] Skip SMS check"
            )

    except KeyboardInterrupt:

        print(
            "\n[MAIN] Stopped"
        )

    except Exception as e:

        print(
            "\n[ERROR]",
            repr(e)
        )

    finally:

        modem.close()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
