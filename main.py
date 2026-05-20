from logging import getLogger

import uvicorn
from fastapi import FastAPI
from magutils.logging import config_async_logging
from magutils.tree_import import build_root_fastapi

from src.env import Env

env = Env()
config_async_logging()
logger = getLogger()


async def lifespan(app: FastAPI):
    logger.info('Successfully start app')
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(build_root_fastapi('./routers'))

if __name__ == '__main__':
    uvicorn.run(app, host=env.API_HOST, port=env.API_PORT, log_config=None)