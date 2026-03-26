"""
Aggregate analyzed posts into ranked startup opportunity report.

Usage:
    python aggregate.py [--min-score N] [--top N] [--no-md]

Reads analyzed.jsonl, ranks by weighted score, clusters recurring pain points,
writes report.md and prints a terminal table.
"""

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'it', 'i', 'my', 'we', 'you', 'that', 'this',
    'have', 'has', 'do', 'not', 'be', 'are', 'was', 'by', 'from', 'just',
    'so', 'can', 'get', 'no', 'up', 'all', 'any', 'if', 'as', 'its',
}


def load_analyzed(path: Path, min_score: int = 5) -> list[dict]:
    posts = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get('software_opportunity_score', 0) >= min_score:
                    posts.append(record)
            except json.JSONDecodeError:
                pass
    return posts


def compute_weighted_score(post: dict) -> float:
    score = post.get('software_opportunity_score', 0)
    upvotes = post.get('upvotes', 0)
    return score * math.log(1 + upvotes)


def rank_opportunities(posts: list[dict], top_n: int = 20) -> list[dict]:
    for post in posts:
        post['weighted_score'] = compute_weighted_score(post)
    return sorted(posts, key=lambda p: p['weighted_score'], reverse=True)[:top_n]


def normalize_tokens(text: str) -> list[str]:
    words = re.findall(r'[a-z]+', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def extract_bigrams(tokens: list[str]) -> list[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


def cluster_pain_points(posts: list[dict]) -> list[tuple[str, list[dict]]]:
    """
    Group posts by recurring pain point bigrams.
    Returns list of (bigram, [posts]) sorted by frequency desc.
    """
    bigram_posts: dict[str, list[dict]] = defaultdict(list)

    for post in posts:
        seen_bigrams = set()
        for pain in post.get('pain_points', []):
            tokens = normalize_tokens(pain)
            for bigram in extract_bigrams(tokens):
                if bigram not in seen_bigrams:
                    bigram_posts[bigram].append(post)
                    seen_bigrams.add(bigram)

    # Keep only bigrams that appear in 2+ posts
    clusters = [(bg, ps) for bg, ps in bigram_posts.items() if len(ps) >= 2]
    return sorted(clusters, key=lambda x: len(x[1]), reverse=True)[:15]


def render_terminal_table(opportunities: list[dict]) -> None:
    col_w = [4, 14, 6, 5, 14, 55]
    headers = ['Rank', 'Subreddit', 'Score', 'Upvt', 'Type', 'Opportunity Summary']
    sep = '-+-'.join('-' * w for w in col_w)

    def row(cells):
        parts = []
        for cell, w in zip(cells, col_w):
            s = str(cell)
            parts.append(s[:w].ljust(w))
        print(' | '.join(parts))

    print()
    row(headers)
    print(sep)
    for i, post in enumerate(opportunities, 1):
        row([
            i,
            post.get('subreddit', '')[:col_w[1]],
            post.get('software_opportunity_score', 0),
            post.get('upvotes', 0),
            post.get('opportunity_type', '')[:col_w[4]],
            post.get('opportunity_summary', '')[:col_w[5]],
        ])
    print()


def render_markdown_report(
    opportunities: list[dict],
    clusters: list[tuple[str, list[dict]]],
    output_path: Path,
) -> None:
    lines = ['# Reddit Startup Opportunity Report\n']

    lines.append('## Top Opportunities\n')
    lines.append('| Rank | Subreddit | Score | Upvotes | Type | Summary |')
    lines.append('|------|-----------|-------|---------|------|---------|')
    for i, post in enumerate(opportunities, 1):
        summary = post.get('opportunity_summary', '').replace('|', '-')
        lines.append(
            f"| {i} | r/{post.get('subreddit','')} "
            f"| {post.get('software_opportunity_score',0)} "
            f"| {post.get('upvotes',0):,} "
            f"| {post.get('opportunity_type','')} "
            f"| {summary} |"
        )

    lines.append('\n## Recurring Pain Points\n')
    lines.append('Pain points that appeared across multiple posts:\n')
    for bigram, posts in clusters:
        lines.append(f"### \"{bigram}\" — {len(posts)} posts\n")
        for post in posts[:3]:
            title = post.get('title', '').replace('|', '-')
            sub = post.get('subreddit', '')
            lines.append(f"- [{title}] (r/{sub}, {post.get('upvotes',0):,} upvotes)")
        if len(posts) > 3:
            lines.append(f"- *...and {len(posts)-3} more*")
        lines.append('')

    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Report written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Aggregate Reddit opportunity analysis')
    parser.add_argument('--min-score', type=int, default=5)
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--no-md', action='store_true', help='Skip writing report.md')
    args = parser.parse_args()

    analyzed_path = Path('analyzed.jsonl')
    if not analyzed_path.exists():
        print("analyzed.jsonl not found. Run analyze.py first.")
        return

    posts = load_analyzed(analyzed_path, min_score=args.min_score)
    print(f"Loaded {len(posts)} posts with score >= {args.min_score}")

    if not posts:
        print("No posts above threshold.")
        return

    opportunities = rank_opportunities(posts, top_n=args.top)
    clusters = cluster_pain_points(posts)

    render_terminal_table(opportunities)

    if not args.no_md:
        render_markdown_report(opportunities, clusters, Path('report.md'))


if __name__ == '__main__':
    main()
