import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from app.services.embedding import EmbeddingModel
from backend.scripts.embed_listings import prepare_embedding_text


def test_embedding_model_format_prefix():
    # Kiểm tra cơ chế tự động gắn prefix của họ E5
    with patch("app.services.embedding.SentenceTransformer") as mock_st:
        model = EmbeddingModel(model_name="intfloat/multilingual-e5-base")

        # 1. Query: thêm prefix 'query: ' nếu chưa có
        assert model._format_text("tìm phòng trọ quận 10", is_query=True) == "query: tìm phòng trọ quận 10"
        # Nếu đã có 'query: ', không bị nhân đôi
        assert model._format_text("query: tìm phòng trọ quận 10", is_query=True) == "query: tìm phòng trọ quận 10"

        # 2. Passage: thêm prefix 'passage: ' nếu chưa có
        assert model._format_text("Vị trí: 150 Bến Vân Đồn", is_query=False) == "passage: Vị trí: 150 Bến Vân Đồn"
        # Nếu đã có 'passage: ', không bị nhân đôi
        assert model._format_text("passage: Vị trí: 150 Bến Vân Đồn", is_query=False) == "passage: Vị trí: 150 Bến Vân Đồn"


def test_embedding_model_encode_query_and_passage():
    with patch("app.services.embedding.SentenceTransformer") as mock_st_cls:
        mock_st = MagicMock()
        mock_st_cls.return_value = mock_st
        # Giả lập vector 768 chiều chuẩn
        mock_st.encode.return_value = np.zeros(768, dtype=np.float32)

        model = EmbeddingModel(model_name="intfloat/multilingual-e5-base")

        # Encode query
        vec_query = model.encode_query("phòng trọ thủ đức")
        assert vec_query.shape == (768,)
        mock_st.encode.assert_called_with(
            "query: phòng trọ thủ đức",
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        # Encode passage
        vec_doc = model.encode_passage("phòng mới xây")
        assert vec_doc.shape == (768,)
        mock_st.encode.assert_called_with(
            "passage: phòng mới xây",
            convert_to_numpy=True,
            normalize_embeddings=True,
        )


def test_prepare_embedding_text_with_existing_text():
    sample = {
        "listing_id": "test_1",
        "embedding_text": "passage: Vị trí: Quận 1 | Giá: 3,000,000",
    }
    res = prepare_embedding_text(sample)
    assert res == "passage: Vị trí: Quận 1 | Giá: 3,000,000"


def test_prepare_embedding_text_fallback_generation():
    sample = {
        "listing_id": "test_2",
        "title": "Phòng đẹp quận 10",
        "description": "Có ban công thoáng mát",
        "street_name": "Đường 3/2",
        "district": "Quận 10",
        "city": "Tp Hồ Chí Minh",
        "price_vnd": 3000000,
        "area_m2": 25,
    }
    res = prepare_embedding_text(sample)
    assert "passage:" in res
    assert "Quận 10" in res
    assert "3,000,000 VND/tháng" in res
    assert "Có ban công thoáng mát" in res
