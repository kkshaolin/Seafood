from fastapi import APIRouter, status
from api.stock.controller import upload_csv, get_stocks, get_summary, get_products, get_history
from api.stock.schema import (
    StockUploadResponse, 
    StockRecordResponse, 
    StockSummaryResponse, 
    StockHistoryResponse, 
    ProductListResponse
)

router = APIRouter(prefix="/stock", tags=["stock"])

router.add_api_route(
    "/upload", 
    upload_csv, 
    methods=["POST"], 
    response_model=StockUploadResponse, 
    status_code=status.HTTP_201_CREATED
)

router.add_api_route(
    "", 
    get_stocks, 
    methods=["GET"], 
    response_model=list[StockRecordResponse], 
    status_code=status.HTTP_200_OK
)

router.add_api_route(
    "/summary", 
    get_summary, 
    methods=["GET"], 
    response_model=StockSummaryResponse, 
    status_code=status.HTTP_200_OK
)

router.add_api_route(
    "/products", 
    get_products, 
    methods=["GET"], 
    response_model=ProductListResponse, 
    status_code=status.HTTP_200_OK
)

router.add_api_route(
    "/history", 
    get_history, 
    methods=["GET"], 
    response_model=StockHistoryResponse, 
    status_code=status.HTTP_200_OK
)
