#!/bin/sh
set -e

make install
make all
make demo-users DEMO_PASSWORD="${DEMO_PASSWORD:-secure}"
make demo-outcomes
