import os
import sys
import pandas as pd
from sentence_transformers import SentenceTransformer
import re
import torch
import torch.nn.functional as F
import numpy as np

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'listings')
PROCESSED_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'listings_transform.csv')

ANCHOR_PHRASES = {
    "mezzanine_score": [
        "phòng có gác lửng",
        "có gác để ngủ",
        "thiết kế có gác xép",
        "phòng có tầng gác",
        "phòng trọ có gác"
    ],

    "parking_score": [
        "có chỗ để xe máy",
        "bãi đậu xe rộng rãi",
        "sân để xe thoải mái",
        "có chỗ giữ xe",
        "có khu vực để xe"
    ],
    "wifi_score": [
        "phòng có wifi tốc độ cao",
        "có sẵn mạng internet",
        "trang bị wifi miễn phí",
        "phòng lắp sẵn mạng cáp quang",
        "có kết nối internet ổn định",
    ],

    "aircon_score": [
        "phòng có máy lạnh",
        "có sẵn điều hòa",
        "trang bị máy lạnh",
        "phòng được trang bị điều hòa",
        "có máy điều hòa"
    ],

    "elevator_score": [
        "tòa nhà có thang máy",
        "có thang máy tiện di chuyển",
        "chung cư có thang máy",
        "tòa nhà được trang bị thang máy"
    ],

    "security_safety_score": [
        "khu vực an ninh tốt",
        "có bảo vệ 24/24",
        "lắp camera an ninh",
        "khu dân cư an toàn yên tĩnh",
        "cửa khóa vân tay an toàn"
    ],

    "free_hours_score": [
        "giờ giấc tự do thoải mái",
        "không giới hạn giờ giấc ra vào",
        "tự do giờ giấc",
        "ra vào tự do",
        "không giới hạn thời gian ra vào"
    ]
}

MODEL_NAME = "keepitreal/vietnamese-sbert"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

LABEL_KEYWORDS = {
    "has_mezzanine": ["gác", "gác lửng", "gác xép", "tầng gác"],
    "has_parking": ["để xe", "bãi xe", "giữ xe", "đậu xe", "sân xe", "hầm xe"],
    "has_aircon": ["máy lạnh", "điều hòa"],
    "has_wifi": [
        "wifi",
        "wi-fi",
        "internet",
        "mạng",
        "cáp quang",
        ],
    "has_elevator": ["thang máy"],
    "security_safety": ["an ninh", "bảo vệ", "camera", "vân tay"],
    "free_hours": [
        "giờ giấc tự do",
        "tự do giờ",
        "ra vào tự do",
        "không chung chủ",
        "giờ giấc",
    ],
}

def load_model(model_name=MODEL_NAME, device=DEVICE):
    model = SentenceTransformer(model_name, device=device)
    return model

def precompute_anchor_embeddings(
    model: SentenceTransformer, anchor_dict: dict, device: str
) -> dict[str, torch.Tensor]:
    """Tính sẵn Embeddings cho các Anchor Phrases để dùng lại nhiều lần."""
    anchor_embeddings = {}
    with torch.no_grad():
        for label, phrases in anchor_dict.items():
            embs = model.encode(phrases, convert_to_tensor=True, device=device)
            anchor_embeddings[label] = F.normalize(embs, p=2, dim=-1)
    return anchor_embeddings

def compute_dense_scores(
    model: SentenceTransformer,
    texts: list[str],
    anchor_embeddings: dict[str, torch.Tensor],
    batch_size: int = 64,
    device: str = "cpu",
) -> dict[str, np.ndarray]:
    """Batch Encoding văn bản và tính Max Cosine Similarity qua Matrix Multiplication."""
    with torch.no_grad():
        # Encode toàn bộ dữ liệu theo Batch
        text_embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_tensor=True,
            device=device,
        )
        text_embeddings = F.normalize(text_embeddings, p=2, dim=-1)

        dense_scores = {}
        for label, anchor_embs in anchor_embeddings.items():
            # Ma trận nhân: (N_texts, Dim) x (Dim, N_anchors) -> (N_texts, N_anchors)
            sim_matrix = torch.mm(text_embeddings, anchor_embs.T)
            max_sims, _ = torch.max(sim_matrix, dim=1)
            dense_scores[label] = max_sims.cpu().numpy()

    return dense_scores

def compute_lexical_matches(
    df: pd.DataFrame, text_column: str, label_keywords: dict
) -> dict[str, np.ndarray]:
    """Kiểm tra Exact Matching Keyword bằng Pandas Vectorized Regex."""
    texts_lower = df[text_column].str.lower()
    lexical_matches = {}

    for label, keywords in label_keywords.items():
        if keywords:
            pattern = (
                r"\b(" + "|".join([re.escape(kw) for kw in keywords]) + r")\b"
            )
            matches = (
                texts_lower.str.contains(pattern, regex=True).astype(float).values
            )
        else:
            matches = np.zeros(len(df))
        lexical_matches[label] = matches

    return lexical_matches

def transform_listings():
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    
    if not os.path.exists(RAW_DIR):
        print("Chưa có dữ liệu đã được dọn dẹp.", flush=True)
        return
        
    model = load_model(model_name=MODEL_NAME, device=DEVICE)

    df = pd.read_csv(PROCESSED_FILE)

    df["title"] = df["title"].fillna("")
    df["description"] = df["description"].fillna("")

    df["text"] = (
        df["title"].str.strip()
        + ". "
        + df["description"].str.strip()
    )

    df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()



if __name__ == "__main__":
    transform_listings()
