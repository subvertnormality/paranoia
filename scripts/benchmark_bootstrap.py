"""Source-only benchmark imports using standard interpreter cache controls.

Entry scripts execute this file with runpy.run_path before importing any owned
harness or production module. run_path reads this .py source directly. A fresh
empty cache prefix prevents existing timestamp-valid bytecode from overriding
validated source; disabling writes keeps that prefix empty. Standard-library
and interpreter integrity remain part of the trusted-OS boundary.
"""
import atexit
import sys
from tempfile import TemporaryDirectory

cache = TemporaryDirectory(prefix="paranoia-benchmark-pycache-")
sys.pycache_prefix = cache.name
sys.dont_write_bytecode = True
atexit.register(cache.cleanup)
