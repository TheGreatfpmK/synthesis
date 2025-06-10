#!/bin/bash

source prerequisites/venv/bin/activate

cd prerequisites/storm/build
cmake ..
make storm-cli storm-pomdp --jobs 4
cd -

cd prerequisites/stormpy
python3 setup.py build_ext --storm-dir="/home/fpmk/synthesis-playground/prerequisites/storm/build" --jobs 4 develop
cd -

cd payntbind
python3 setup.py build_ext --storm-dir="/home/fpmk/synthesis-playground/prerequisites/storm/build" --jobs 4 develop
cd -
