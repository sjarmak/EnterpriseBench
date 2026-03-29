"""Allow running as: python -m eb_verify <command>"""
import sys
from eb_verify.cli import main

sys.exit(main())
