#!/bin/bash

VIRTUAL_ENV="/opt/gvm/gvm"
SCRIPT_PATH="/opt/gvm/Targets_Tasks/run-task.py"

source "$VIRTUAL_ENV/bin/activate"
python3 "$SCRIPT_PATH"

deactivate

