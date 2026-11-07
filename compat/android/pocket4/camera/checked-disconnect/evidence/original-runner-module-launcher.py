#!/usr/bin/env python3
"""Use the actual installed JDK compiler module when its javac launcher is absent."""
import os
import sys

JAVA = "/usr/lib/jvm/java-17-openjdk-amd64/bin/java"
jvm = [arg[2:] for arg in sys.argv[1:] if arg.startswith("-J")]
compiler = [arg for arg in sys.argv[1:] if not arg.startswith("-J")]
os.execv(JAVA, [JAVA, *jvm, "-m", "jdk.compiler/com.sun.tools.javac.Main", *compiler])
