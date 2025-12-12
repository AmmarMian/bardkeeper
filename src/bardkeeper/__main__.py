"""
Main entry point for running BardKeeper as a module.

Allows running: python -m bardkeeper
"""

from .cli.main import cli

if __name__ == '__main__':
    cli()
