set shell := ["bash", "-cu"]
py := ".venv/bin/python"

default:
    @just --list

setup:
    [ -d .venv ] || python3 -m venv .venv
    {{py}} -m pip install -q -U pip PySide6 pyqtgraph numpy pyserial

check:
    @ls /dev/ttyUSB* 2>/dev/null && echo "port série OK" || echo "aucun /dev/ttyUSB* : câble ? scope allumé ?"
    @id -nG | grep -qw dialout && echo "groupe dialout OK" || echo "ajoute-toi au groupe dialout"
    {{py}} hds_mirror.py --idn

run mode="":
    {{py}} hds_mirror.py {{mode}}

clean:
    rm -rf .venv __pycache__
