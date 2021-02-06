#!/bin/bash

# merlin:
# wget https://www.stud.fit.vutbr.cz/~xandri03/synthesis.zip
# git:
# https://github.com/gargantophob/synthesis/archive/master.zip
# zenodo 0.1:
# wget https://zenodo.org/record/4422544/files/synthesis.zip
# zenodo 0.11: https://zenodo.org/record/4425438
# wget https://zenodo.org/record/4425438/files/synthesis.zip
# zenodo 0.12: TODO

# compilation parameters

export COMPILE_JOBS=$(nproc)
export SYNTHESIS_TACAS21=true
export SYNTHESIS_INSTALL_DEPENDENCIES=false

# environment variables

export SYNTHESIS=`pwd`
export PREREQUISITES=$SYNTHESIS/prerequisites
export SYNTHESIS_ENV=$SYNTHESIS/env

export STORM_DIR=$SYNTHESIS/storm
export STORM_SRC=$STORM_DIR/src
export STORM_BLD=$STORM_DIR/build

export STORMPY_DIR=$SYNTHESIS/stormpy
export DYNASTY_DIR=$SYNTHESIS/dynasty

### TACAS 2021 #################################################################

tacas21-prepare-artifact() {
    cd synthesis/prerequisites/tacas-dependencies

    DEP_DIR=$PWD

    # download apt-packages
    mkdir -p apt-packages
    sudo apt-get update
    sudo apt-get install --print-uris libgmp-dev libglpk-dev libhwloc-dev z3 libboost-all-dev libeigen3-dev libginac-dev libpython3-dev automake python3-virtualenv | grep -oP "(?<=').*(?=')" > packages.uri
    cd $apt-packages
    wget -i ../packages.uri
    cd $DEP_DIR

    # download pip packages
    pip3 download -d pip-packages -r python-requirements
    cd ..

    # zip everything
    zip -r tacas-dependencies.zip tacas-dependencies
    rm -rf tacas-dependencies
    cd ..
    zip -r synthesis.zip synthesis
}

### storm patch ################################################################

dynasty-patch-create() {
    echo "NOT IMPLEMENTED YET"
}

dynasty-patch() {
    rsync -av $SYNTHESIS/patch/ $SYNTHESIS/
}

### preparing prerequisites ####################################################

carl-build() {
    mkdir -p $PREREQUISITES/carl/build
    cd $PREREQUISITES/carl/build
    cmake -DUSE_CLN_NUMBERS=ON -DUSE_GINAC=ON -DTHREAD_SAFE=ON ..
    make lib_carl --jobs $COMPILE_JOBS
    # make test
    cd $OLDPWD
}

pycarl-build() {
    cd $PREREQUISITES/pycarl
    source $SYNTHESIS_ENV/bin/activate
    python3 setup.py build_ext --carl-dir $PREREQUISITES/carl/build --jobs $COMPILE_JOBS develop
    # python setup.py test
    deactivate
    cd $OLDPWD
}

### storm and stormpy ##########################################################

storm-config() {
    mkdir -p $STORM_BLD
    cd $STORM_BLD
    cmake ..
    # cmake -DSTORM_USE_LTO=OFF ..
    cd -
}

storm-build() {
    cd $STORM_BLD
    make storm-main --jobs $COMPILE_JOBS
    # make check --jobs $COMPILE_JOBS
    cd -
}

stormpy-build() {
    cd $STORMPY_DIR
    source $SYNTHESIS_ENV/bin/activate
    python3 setup.py build_ext --storm-dir $STORM_BLD --jobs $COMPILE_JOBS develop
    # python setup.py test
    deactivate
    cd -
}

dynasty-install() {
    cd $DYNASTY_DIR
    source $SYNTHESIS_ENV/bin/activate
    python3 setup.py install
    # python3 setup.py test
    deactivate
    cd $OLDPWD
}

# aggregated functions

synthesis-install() {
    carl-build
    pycarl-build

    dynasty-patch
    storm-config
    storm-build
    stormpy-build

    dynasty-install
}

synthesis-full() {
    synthesis-dependencies
    synthesis-install
}

### development ################################################################

# recompilation

storm-rebuild() {
    storm-config
    storm-build
}

stormpy-rebuild() {
    storm-rebuild
    stormpy-build
}

# aliases

alias sc='storm-config'
alias sb='storm-build'
alias pb='stormpy-build'
alias sr='storm-rebuild'

alias synthesis='cd $SYNTHESIS'

alias enva='source $SYNTHESIS_ENV/bin/activate'
alias envd='deactivate'

alias tb='cd $DYNASTY_DIR; enva; subl $SYNTHESIS/dynasty/dynasty/family_checkers/integrated_checker.py; subl $SYNTHESIS/dynasty/execute.sh'
alias tf='envd'

### execution $$################################################################

export WORKSPACE=$SYNTHESIS/workspace
export DYNASTY_LOG=$WORKSPACE/log

function dynasty() {
    local core=0
    if [ -n "$1" ]; then
        core=$1
    fi
    local exp_sh=$WORKSPACE/execute.sh
    local run_sh=$DYNASTY_LOG/run_${core}.sh

    cd $SYNTHESIS
    mkdir -p $DYNASTY_LOG
    cp $exp_sh $run_sh
    enva
    bash $run_sh $core
    envd
    cd ~-
}
function d() {
    dynasty $1
}
function db() {
    dynasty $1 & disown
}

alias dpid='pgrep -f "^python dynasty.py .*"'
alias dtime='ps -aux | grep "python dynasty.py"'
alias dshow='pgrep -af "^python dynasty.py .*"'
alias dcount='pgrep -afc "^python dynasty.py .*"'
alias dkill='dpid | xargs kill'

dlog() {
    cat $DYNASTY_LOG/log_$1.txt
}

dhead() {
    dlog $1 | head -n 50
}
dtail() {
    dlog $1 | tail -n 50
}

dgrep() {
    cat $DYNASTY_LOG/log_grep_$1.txt
}

diter() {
    dlog $1 | grep "iteration " | tail -n 1
}
diteri() {
    dlog $1 | grep "CEGIS: iteration " | tail -n 1
}
ditera() {
    dlog $1 | grep "CEGAR: iteration " | tail -n 1
}

dfamily() {
    dlog $1 | grep "family size" | tail -n 1
}
ddtmc() {
    dlog $1 | grep "Constructed DTMC"
}

dopt() {
    dlog $1 | grep "Optimal value" | tail -n 1
}

dbounds() {
    dlog $1 | grep "Result for initial"
}
dces() {
    dlog $1 | grep "generalized"
}
dperf() {
     dlog $1 | grep "Performance" | tail -n 1
}

dholes() {
    dlog $1 | grep "hole assignment:" | awk '{print $3}'
}

### binds ###

bind '"\ei"':"\"storm-config \C-m\""
bind '"\eo"':"\"storm-build \C-m\""
bind '"\ep"':"\"stormpy-build \C-m\""

bind '"\ed"':"\"db \C-m\""
bind '"\e1"':"\"db 1 \C-m\""
bind '"\e2"':"\"db 2 \C-m\""
bind '"\e3"':"\"db 3 \C-m\""
bind '"\e4"':"\"db 4 \C-m\""
bind '"\e5"':"\"db 5 \C-m\""
bind '"\e6"':"\"db 6 \C-m\""
bind '"\e7"':"\"db 7 \C-m\""
bind '"\e8"':"\"db 8 \C-m\""

### tmp ################################################################

storm() {
    cd $STORM_BLD/bin
    local cmd="./storm --explchecks --build-overlapping-guards-label $1"
    eval $cmd
    cd -
}

storm-jani() {
    storm "--jani $DYNASTY_DIR/output_1.jani --prop $DYNASTY_DIR/workspace/examples/cav/maze/orig/compute.properties"
}

storm-eval() {
    storm "$1 --prop $2 --constants $3"
}

export DPM=$DYNASTY_DIR/workspace/examples/cav/dpm-main
export DICE=$DYNASTY_DIR/workspace/examples/cav/dice
export MAZE=$DYNASTY_DIR/workspace/examples/cav/maze

dice() {
    storm-eval "--prism $DICE/sketch.templ" $DICE/compute.properties "CMAX=0,THRESHOLD=0,$1"
}
dpm() {
    storm-eval "--prism $DPM/sketch.templ" $DPM/compute.properties "CMAX=10,THRESHOLD=0,T2=5,$1"
}

