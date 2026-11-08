"""Exact initial-input function, dependency-injected only by isolated tests."""
import argparse

from contextlib import redirect_stderr, redirect_stdout

import fcntl

import hashlib

import io as string_io

import json

import os

from pathlib import Path

import re

import signal

import stat

import sys

import time

import traceback

import types

HERE = Path(__file__).resolve().parent


def initial_inputs(io, model, packet, manifest_ref):
    witness = source_witness(io, model, packet, manifest_ref)
    known, _ = witness.read({'path': str(HERE / 'known-actual-inputs.json'), 'sha256': model.KNOWN_SHA}, json=True)
    base = model.baseline(io, witness)
    model.audio.baseline(io, witness, model, base)
    checks = runner(io, model).validate(base['values']['deployment/manifest.json'],
                                        base['values']['deployment/transaction-plan.json'])
    io.need(checks == {'checksums_verified': 43, 'install_count': 28,
                      'file_overrides': 47, 'runtime_directories': 4}, 'ACTUAL_OLD_RUNNER_VALIDATION')
    framework = model.framework(io, witness, known, HERE / 'framework-maintenance-gate.json')
    camera = model.camera(io, witness, known)
    return witness, known, base, framework, camera, checks
