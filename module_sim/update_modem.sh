#!/bin/sh

usage() {
    echo "Firmware Upgrade Tool"
    echo
    echo "Usage:"
    echo "  $0 -m <MODEM> -v <FW_VERSION>"
    echo
    echo "MODEM:"
    echo "  A7600"
    echo "  CLM920"
    echo "  EC200A"
    echo
    echo "Examples:"
    echo "  $0 -m A7600 -v A81C4B04A7600M7"
    echo "  $0 -m CLM920 -v CLM920_JC3_V4.7"
    echo "  $0 -m EC200A -v EC200ACNLAR01A12M16_fbf"
    echo
    echo "Description:"
    echo "  This script upgrades the modem firmware to the specified version."
    echo "  Before upgrading, related services and processes will be stopped"
    echo "  to prevent the 4G module from restarting during the upgrade."
    echo
    exit 1
}

MODEM=""
VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        -m)
            MODEM="$2"
            shift 2
            ;;
        -v)
            VERSION="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            usage
            ;;
    esac
done

[ -z "$MODEM" ] && usage
[ -z "$VERSION" ] && usage

#BINFILE="BinFile_${VERSION}.bin"

case "$MODEM" in
    A7600)
        BASE_URL="http://repo.smatec.com.vn/modem/a7600"
        DOWNLOADER="fbfdownloader_a76xx"
        EXPECTED_VID="1e0e"
        EXPECTED_PID="9011"
        LOGFILE="/tmp/a7600_upgrade.log"
        BINFILE="BinFile_A7600C_${VERSION}.bin"

        echo "$VERSION" | grep -q "A7600" || {
            echo "ERROR: Firmware version does not match modem type A7600"
            exit 1
        }
        ;;

    CLM920)
        BASE_URL="http://repo.smatec.com.vn/modem/clm920"
        DOWNLOADER="fbfdownloader_clm920"
        EXPECTED_VID="1286"
        EXPECTED_PID="4e3c"
        LOGFILE="/tmp/clm920_upgrade.log"

        echo "$VERSION" | grep -qi "CLM920" || {
            echo "ERROR: Firmware version does not match modem type CLM920"
            exit 1
        }
        ;;

    EC200A)
        BASE_URL="http://repo.smatec.com.vn/modem/ec200a"
        DOWNLOADER="fbfdownloader_ec200a"
        EXPECTED_VID="2c7c"
        EXPECTED_PID="6005"
        LOGFILE="/tmp/ec200a_upgrade.log"

        echo "$VERSION" | grep -qi "EC200A" || {
            echo "ERROR: Firmware version does not match modem type EC200A"
            exit 1
        }
        ;;
    *)
        echo "ERROR: Unsupported modem type: $MODEM"
        exit 1
        ;;
esac

WD="/tmp"

check_usb_device()
{
    for dev in /sys/bus/usb/devices/*; do

        [ -f "$dev/idVendor" ] || continue
        [ -f "$dev/idProduct" ] || continue

        VID=$(cat "$dev/idVendor")
        PID=$(cat "$dev/idProduct")

        if [ "$VID" = "$EXPECTED_VID" ] && \
           [ "$PID" = "$EXPECTED_PID" ]; then

            echo "Detected modem: $MODEM ($VID:$PID)"
            return 0
        fi
    done

    echo "ERROR: Expected modem not found"
    echo "Expected VID:PID = $EXPECTED_VID:$EXPECTED_PID"

    return 1
}

cleanup()
{
    echo
    echo "Starting services..."

    /etc/init.d/cron start 2>/dev/null
    /etc/init.d/mgw8788 start 2>/dev/null
}

trap cleanup EXIT

echo "======================================="
echo "Modem   : $MODEM"
echo "Version : $VERSION"
echo "======================================="

echo "[0/5] Verifying modem..."

check_usb_device || exit 1

echo "[1/5] Stopping services..."

/etc/init.d/cron stop 2>/dev/null

pkill -9 -f "/usr/bin/mgwp_app" 2>/dev/null
pkill -9 -f "python /usr/lib/python3.9/site-packages/mgw3/mgwp.pyc" 2>/dev/null

sleep 2

cd "$WD" || exit 1

if [ ! -f "$DOWNLOADER" ]; then
    echo "[2/5] Downloading $DOWNLOADER ..."

    wget -O "$DOWNLOADER" "$BASE_URL/$DOWNLOADER" || {
        echo "ERROR: Download $DOWNLOADER failed"
        exit 1
    }

    chmod +x "$DOWNLOADER"
else
    echo "[2/5] Downloader already exists"
fi

echo "[3/5] Downloading $BINFILE ..."

wget -O "$BINFILE" "$BASE_URL/$BINFILE" || {
    echo "ERROR: Download $BINFILE failed"
    exit 1
}

echo "[4/5] Upgrading firmware ..."

./"$DOWNLOADER" -b "$BINFILE" 2>&1 | tee "$LOGFILE"

RET=$?

echo "[5/5] Checking result ..."

if [ $RET -ne 0 ]; then
    echo "ERROR: Downloader exited with code $RET"
    exit 1
fi

if grep -q "Burn Successfully" "$LOGFILE"; then

    echo
    echo "======================================="
    echo "Firmware upgrade SUCCESS"
    echo "======================================="

    echo "Restarting modem..."

    mraa-gpio set 37 0
    sleep 3
    mraa-gpio set 37 1

    echo "Modem rebooted"

else

    echo
    echo "======================================="
    echo "Firmware upgrade FAILED"
    echo "======================================="

    exit 1
fi

rm -f "$BINFILE"
rm -f "$DOWNLOADER"
rm -f "$LOGFILE"

exit 0
