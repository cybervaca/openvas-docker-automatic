#!/bin/bash

VIRTUAL_ENV="/opt/gvm/gvm"
SCRIPT_PATH="/opt/gvm/Update/update-script.py"

source "$VIRTUAL_ENV/bin/activate"
python3 "$SCRIPT_PATH"
rm "/opt/gvm/tasksend.txt"
deactivate

