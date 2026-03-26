"""
Parse Reddit post files from /data/* subdirectories and export to JSONL.
Extracts post_id, subreddit, upvotes, title, and text (no multimedia).

JSONL format is ideal for:
- Iterating through posts one at a time
- Adding fields after LLM categorization
- Easy aggregation with pandas: pd.read_json('posts.jsonl', lines=True)
"""

import json
import re
from pathlib import Path
from urllib.parse import unquote


def extract_title_from_url(header_line: str) -> str:
    """Extract the post title from the Reddit URL in the header."""
    # URL pattern: https://www.reddit.com/r/sidehustle/comments/id/title_with_underscores/
    match = re.search(r'reddit\.com/r/\w+/comments/\w+/([^/)]+)', header_line)
    if match:
        title = unquote(match.group(1).replace('_', ' '))
        return title.strip()
    return ""


def extract_upvotes_from_filename(filename: str) -> int:
    """Parse upvote count from bdfr filename: '1012_redditor_postid_date.txt'"""
    try:
        return int(filename.split('_')[0])
    except (ValueError, IndexError):
        return 0


def extract_post_id_from_filename(filename: str) -> str:
    """Extract Reddit post ID (3rd token) from bdfr filename: '1012_redditor_postid_date.txt'"""
    parts = filename.split('_')
    return parts[2] if len(parts) > 2 else ""


def parse_post_file(file_path: Path, subreddit: str) -> dict | None:
    """Parse a single post file and return structured data."""
    content = file_path.read_text(encoding='utf-8')
    lines = content.strip().split('\n')

    if not lines:
        return None

    header_line = lines[0]
    title = extract_title_from_url(header_line)

    text_lines = []
    for line in lines[1:]:
        if line.strip() == '---':
            break
        text_lines.append(line)

    text = '\n'.join(text_lines).strip()
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if len(text) < 50:
        return None

    filename = file_path.stem  # name without extension
    return {
        'post_id': extract_post_id_from_filename(filename),
        'subreddit': subreddit,
        'upvotes': extract_upvotes_from_filename(filename),
        'title': title,
        'text': text,
    }


def load_existing_post_ids(output_file: Path) -> set[str]:
    """Return set of post_ids already in the output JSONL file."""
    if not output_file.exists():
        return set()
    ids = set()
    with open(output_file, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    post = json.loads(line)
                    if post.get('post_id'):
                        ids.add(post['post_id'])
                except json.JSONDecodeError:
                    pass
    return ids


def main(subreddits: list[str] | None = None):
    """
    Scan data/ subdirectories for post files and append new ones to posts.jsonl.
    If subreddits is provided, only process those subdirectories.
    """
    root = Path(__file__).parent
    data_dir = root / 'data'
    output_file = root / 'posts.jsonl'

    # Determine which subdirectories to scan
    if subreddits:
        sub_dirs = [data_dir / s for s in subreddits if (data_dir / s).exists()]
    else:
        sub_dirs = [d for d in sorted(data_dir.iterdir()) if d.is_dir()]

    if not sub_dirs:
        print(f"No data subdirectories found in {data_dir}")
        return

    existing_ids = load_existing_post_ids(output_file)
    print(f"Existing posts in {output_file.name}: {len(existing_ids)}")

    new_posts = []
    for sub_dir in sub_dirs:
        subreddit = sub_dir.name
        post_files = sorted(sub_dir.glob('*.txt'))
        print(f"\nr/{subreddit}: {len(post_files)} files")

        for file_path in post_files:
            post_id = extract_post_id_from_filename(file_path.stem)
            if post_id in existing_ids:
                continue
            try:
                post = parse_post_file(file_path, subreddit)
                if post:
                    new_posts.append(post)
                    existing_ids.add(post['post_id'])
            except Exception as e:
                print(f"  Error parsing {file_path.name}: {e}")

    if not new_posts:
        print("\nNo new posts to add.")
        return

    with open(output_file, 'a', encoding='utf-8') as f:
        for post in new_posts:
            f.write(json.dumps(post, ensure_ascii=False) + '\n')

    print(f"\nAppended {len(new_posts)} new posts to {output_file}")


if __name__ == '__main__':
    main()
