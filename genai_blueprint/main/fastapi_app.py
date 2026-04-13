"""
Entry point for the REST API

"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger  # type: ignore
from rich import print  # type: ignore  # noqa: F401

# fmt: off
[sys.path.append(str(path)) for path in [Path.cwd(), Path.cwd().parent, Path.cwd().parent/"python"] if str(path) not in sys.path]  # type: ignore # fmt: on

load_dotenv(verbose=True)
app = FastAPI()

@app.get("/echo/{message}")
def read_root(message:str):
    logger.info("received /echo/{}", message)
    return {"msg": message}
