from unittest.mock import MagicMock
import pytest
from app.schemas.analytics import PriceStatsResponse, PriceStatsGeneral, PriceStatsByArea
from app.services.listing_service import ListingService


def test_get_price_stats_general_and_by_area_schema():
    mock_db = MagicMock()
    mock_repo = MagicMock()

    # Mock repository price_aggregates: (total_count, avg, min, max)
    mock_repo.price_aggregates.return_value = (15, 4200000.0, 2500000.0, 8000000.0)
    mock_repo.count_and_average.side_effect = [
        (10, 4300000.0),  # current month (cur_count, cur_avg)
        (8, 4100000.0),   # prev month (prev_count, prev_avg)
    ]

    # Mock by_area query result
    mock_row_1 = MagicMock()
    mock_row_1.id = 101
    mock_row_1.name = "Phường Linh Trung"
    mock_row_1.total_listings = 5
    mock_row_1.average_price_vnd = 3500000.0
    mock_row_1.minimum_price_vnd = 2500000.0
    mock_row_1.maximum_price_vnd = 5000000.0

    mock_row_2 = MagicMock()
    mock_row_2.id = 102
    mock_row_2.name = "Phường Linh Xuân"
    mock_row_2.total_listings = 10
    mock_row_2.average_price_vnd = 4500000.0
    mock_row_2.minimum_price_vnd = 3000000.0
    mock_row_2.maximum_price_vnd = 8000000.0

    query_mock = MagicMock()
    query_mock.join.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.group_by.return_value = query_mock
    query_mock.all.return_value = [mock_row_1, mock_row_2]

    mock_db.query.return_value = query_mock

    service = ListingService(db=mock_db, repository=mock_repo)
    response = service.get_price_stats(city_id=79, district_id=769, room_type_id=1)

    assert isinstance(response, PriceStatsResponse)
    assert isinstance(response.price_stats_general, PriceStatsGeneral)
    assert response.price_stats_general.total_listings == 15
    assert response.price_stats_general.average_price_vnd == 4300000.0
    assert response.price_stats_general.minimum_price_vnd == 2500000.0
    assert response.price_stats_general.maximum_price_vnd == 8000000.0
    assert response.price_stats_general.price_fluctuation_month == 4.88  # ((4300000 - 4100000) / 4100000) * 100

    assert response.price_stats_by_area is not None
    assert len(response.price_stats_by_area) == 2
    assert response.price_stats_by_area[0].area == "Phường Linh Trung"
    assert response.price_stats_by_area[0].minimum_price_vnd == 2500000.0
    assert response.price_stats_by_area[0].average_price_vnd == 3500000.0
    assert response.price_stats_by_area[1].area == "Phường Linh Xuân"
    assert response.price_stats_by_area[1].minimum_price_vnd == 3000000.0
