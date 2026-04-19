"""Regression tests for logger configuration used by the MCP server."""

import logging
import sys

from perplexity.logger import setup_logger


def test_setup_logger_uses_stderr_and_disables_propagation(tmp_path) -> None:
    log_file = tmp_path / "perplexity.log"
    logger = setup_logger("perplexity.test", log_file=str(log_file))

    console_handlers = [
        handler for handler in logger.handlers if type(handler) is logging.StreamHandler
    ]
    assert len(console_handlers) == 1
    assert console_handlers[0].stream is sys.stderr
    assert logger.propagate is False
