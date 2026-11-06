#!/usr/bin/env python3
"""Prepare exact locked registry sources in one fresh private vendor tree; execute no crate or Cargo."""
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import ssl
import stat
import sys
import tarfile
import time
import tomllib

ROOT = Path("/home/alex/work/p4-retirement-wayland-vendor-prep01-20261106")
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
ARCHIVES = OUT/'archives'
VENDOR = OUT/'vendor'
CARGO_HOME = Path('/home/alex/.cargo')
DEADLINE = None
MEMORY_BUDGET = 536870912
MINIMUM_MEM_AVAILABLE = 1073741824
WORK_SECONDS = 300
MAX_ARCHIVE_BYTES = 32*1024*1024
MAX_ALL_ARCHIVE_BYTES = 512*1024*1024
MAX_NETWORK_BYTES = 128*1024*1024
MAX_MISSING_PACKAGES = 193
MAX_ALL_SOURCE_BYTES = 1024*1024*1024
LOCK_SHA = 'c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'
REGISTRY_ROWS_SHA = 'a86540f0e046028467072afadccac95565f294c399b43c02764cb86dba23f2b9'
CLEANUP_ERRORS = []
ACTIVE_FDS = set()
OBSERVED_SIGNALS = []

