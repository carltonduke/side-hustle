import argparse
import subprocess
import time
from pathlib import Path

import yaml

import parse_posts


def get_bdfr_bin() -> Path:
    bdfr = Path(__file__).parent  / '.venv' / 'bin' / 'bdfr'
    if not bdfr.exists():
        raise FileNotFoundError(
            f"bdfr not found at {bdfr}.\n"
            "Setup: python -m venv .venv && .venv/bin/pip install bdfr"
        )
    return bdfr


def load_subreddits(config_path: Path) -> list[dict]:
    with open(config_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('subreddits', [])


def download_subreddit(bdfr_bin: Path, subreddit: str, data_dir: Path, limit: int = 1000) -> bool:
    print(f"\nDownloading r/{subreddit}...")
    result = subprocess.run(
        [
            str(bdfr_bin), 'download', str(data_dir),
            '--subreddit', subreddit,
            '--sort', 'top',
            '--time', 'all',
            '--limit', str(limit),
            '--skip', 'mp4', '--skip', 'avi', '--skip', 'mov',
            '--skip', 'gif', '--skip', 'jpg', '--skip', 'jpeg', '--skip', 'png',
            '--file-scheme', '{UPVOTES}_{REDDITOR}_{POSTID}_{DATE}',
            '--no-dupes',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  bdfr error: {result.stderr}")
        return False
    print(f"  Done: r/{subreddit}")
    return True


def run(download: bool = True, parse: bool = True, analyze: bool = False, delay: int = 5):
    root = Path(__file__).parent
    config_path = root / "config" / 'subreddits.yaml'
    data_dir = root / 'data'

    subreddits = load_subreddits(config_path)
    print(f"Loaded {len(subreddits)} subreddits from {config_path.name}")

    if download:
        bdfr_bin = get_bdfr_bin()
        for i, sub in enumerate(subreddits):
            res = download_subreddit(bdfr_bin, sub['name'], data_dir)
            if not res:
                raise SystemError()
            if i < len(subreddits) - 1:
                time.sleep(delay)

    if parse:
        sub_names = [s['name'] for s in subreddits]
        parse_posts.main(subreddits=sub_names)

    if analyze:
        import analyze
        import asyncio
        asyncio.run(analyze.run_analysis())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reddit pain point pipeline')
    parser.add_argument('--no-download', action='store_true', help='Skip download stage')
    parser.add_argument('--no-parse', action='store_true', help='Skip parse stage')
    parser.add_argument('--analyze', action='store_true', help='Run Claude analysis stage')
    parser.add_argument('--delay', type=int, default=5, help='Seconds between subreddit downloads')
    args = parser.parse_args()

    run(
        download=not args.no_download,
        parse=not args.no_parse,
        analyze=args.analyze,
        delay=args.delay,
    )
