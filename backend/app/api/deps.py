from typing import Annotated

from fastapi import Depends, Request

from ..container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


Services = Annotated[Container, Depends(get_container)]
