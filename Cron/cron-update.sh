#!/bin/bash

VIRTUAL_ENV="/opt/gvm/gvm"
SCRIPT_PATH="/opt/gvm/Update/update-versiones.py"

source "$VIRTUAL_ENV/bin/activate"
sudo python3 "$SCRIPT_PATH"

deactivate

