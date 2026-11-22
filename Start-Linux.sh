#!/bin/bash
# ChromIQ instrument probe: Linux launcher.
#
# Double-click this if your file manager allows it, otherwise open a terminal
# in this folder and run:   bash Start-Linux.sh

cd "$(dirname "$0")" || exit 1

clear
echo
echo "  ChromIQ instrument probe (Linux)"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "  Python 3 is not installed."
    echo
    echo "  Install it with your package manager, for example:"
    echo "      Debian / Ubuntu :  sudo apt install python3"
    echo "      Fedora          :  sudo dnf install python3"
    echo "      Arch            :  sudo pacman -S python"
    echo
    read -n 1 -s -r -p "  Press any key to close..."
    echo
    exit 1
fi

# A USB recording needs Linux's usbmon module; the tool says how to load it
# (sudo modprobe usbmon) when it is missing. This launcher loads nothing.

# --no-pause: this script waits at the end itself, so the tool must not.
python3 instrument_probe.py --no-pause
status=$?

echo
if [ $status -ne 0 ]; then
    echo "  The tool ended with code $status. The text above says why."
    echo "  If it looks like a fault, please copy this window's contents into a GitHub issue."
    echo
fi
read -n 1 -s -r -p "  Press any key to close..."
echo
