from fastapi import APIRouter
from .controller import router as training_router

router = APIRouter()
router.include_router(training_router)