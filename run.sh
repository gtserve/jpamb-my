#!/bin/bash

set -x

TIMESTAMP=$(date +"%y-%m-%d:%H-%M")

if [[ $1 -eq "static" ]]; then 
    if [[ $2 -eq "interpret" ]]; then
        jpamb $2 --report "../reports/$1-$2-$TIMESTAMP.sexp" "$1"-interpreter
    fi

    if [[ $2 -eq "analyse" ]]; then
        jpamb $2 --report "../reports/$1-$2-$TIMESTAMP.sexp" "$1"-analysis
    fi
else
    echo "Unknown option!"
fi
