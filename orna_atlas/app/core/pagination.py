from typing import Annotated

from fastapi import Query


PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]
FeaturedLimit = Annotated[int, Query(ge=1, le=50)]
