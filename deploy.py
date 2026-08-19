#!/usr/bin/env python3
"""Deploy to Hugging Face Spaces in one command.

Usage:
    python deploy.py                    # deploy with defaults
    python deploy.py --space myuser/myspace
    
Requires: pip install huggingface-hub
Auth: run `huggingface-cli login` once, or set HF_TOKEN env var.
"""

import argparse
from huggingface_hub import HfApi

SPACE_ID = "rakuten-aakashtembhare/notemaker"  # change to your space

# Files to deploy (relative paths)
DEPLOY_FILES = [
    "app.py",
    "requirements.txt",
    "README.md",
]


def deploy(space_id: str):
    api = HfApi()
    print(f"Deploying to https://huggingface.co/spaces/{space_id}")

    api.upload_folder(
        folder_path=".",
        repo_id=space_id,
        repo_type="space",
        allow_patterns=DEPLOY_FILES,
        commit_message="Deploy update",
    )

    print(f"Done! https://huggingface.co/spaces/{space_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", default=SPACE_ID)
    args = parser.parse_args()
    deploy(args.space)
