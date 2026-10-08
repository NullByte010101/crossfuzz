from huggingface_hub import snapshot_download

from utils.config_loader import config

MODEL_REPO = "sentence-transformers/all-mpnet-base-v2"

if __name__ == "__main__":
    model_dir = config.get("paths.model_dir")
    snapshot_download(repo_id=MODEL_REPO, local_dir=model_dir)
    print(f"Model downloaded to {model_dir}")
