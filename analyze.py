"""
Analyze parsed Reddit posts using the Claude API to extract pain points
and score software startup opportunities.

Usage:
    python analyze.py [--batch-size N] [--min-text N]

Requires ANTHROPIC_API_KEY environment variable.
Results are appended to analyzed.jsonl (idempotent — skips already-analyzed posts).
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import anthropic

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 20
MIN_TEXT_LENGTH = 100

EXTRACTION_PROMPT = """\
You are analyzing a Reddit post to identify software startup opportunities.

Post from r/{subreddit} ({upvotes} upvotes):
Title: {title}
Body: {text}

Extract structured data as JSON with these exact keys:
- "pain_points": array of strings, each a specific problem or friction mentioned (empty array if none)
- "industry": string, the primary domain (e.g. "accounting", "trucking", "real estate", "freelancing")
- "software_opportunity_score": integer 1-10, where:
    1-3 = venting/lifestyle post, no clear software angle
    4-6 = some manual process that could be improved with software
    7-9 = clear workflow pain with an obvious software solution
    10 = recurring, high-stakes problem with no good existing solution
- "opportunity_type": one of: automation, marketplace, analytics, communication,
    scheduling, financial_tools, compliance, crm, inventory, none
- "opportunity_summary": 1-2 sentence description of the software product idea, or "" if score < 4

Return ONLY valid JSON, no explanation, no markdown fences."""


async def analyze_post(client: anthropic.AsyncAnthropic, post: dict) -> dict:
    """Call Claude for a single post. Returns post merged with analysis fields."""
    prompt = EXTRACTION_PROMPT.format(
        subreddit=post.get('subreddit', 'unknown'),
        upvotes=post.get('upvotes', 0),
        title=post.get('title', ''),
        text=post.get('text', '')[:3000],  # cap at 3000 chars to control tokens
    )
    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [warn] JSON parse failed for post_id={post.get('post_id')} — storing score=0")
        analysis = {
            'pain_points': [],
            'industry': '',
            'software_opportunity_score': 0,
            'opportunity_type': 'none',
            'opportunity_summary': '',
        }
    except Exception as e:
        print(f"  [error] API error for post_id={post.get('post_id')}: {e}")
        analysis = {
            'pain_points': [],
            'industry': '',
            'software_opportunity_score': 0,
            'opportunity_type': 'none',
            'opportunity_summary': '',
        }

    return {**post, **analysis}


async def analyze_batch(client: anthropic.AsyncAnthropic, batch: list[dict]) -> list[dict]:
    return await asyncio.gather(*[analyze_post(client, post) for post in batch])


def load_analyzed_ids(analyzed_path: Path) -> set[str]:
    if not analyzed_path.exists():
        return set()
    ids = set()
    with open(analyzed_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    if record.get('post_id'):
                        ids.add(record['post_id'])
                except json.JSONDecodeError:
                    pass
    return ids


def load_unanalyzed_posts(posts_path: Path, analyzed_ids: set[str], min_text: int) -> list[dict]:
    posts = []
    with open(posts_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                post = json.loads(line)
                if post.get('post_id') in analyzed_ids:
                    continue
                if len(post.get('text', '')) < min_text:
                    continue
                posts.append(post)
            except json.JSONDecodeError:
                pass
    return posts


async def run_analysis(
    posts_path: Path = Path('posts.jsonl'),
    output_path: Path = Path('analyzed.jsonl'),
    batch_size: int = BATCH_SIZE,
    min_text: int = MIN_TEXT_LENGTH,
):
    analyzed_ids = load_analyzed_ids(output_path)
    posts = load_unanalyzed_posts(posts_path, analyzed_ids, min_text)

    if not posts:
        print("No new posts to analyze.")
        return

    total_batches = (len(posts) + batch_size - 1) // batch_size
    print(f"Analyzing {len(posts)} posts in {total_batches} batches (model: {MODEL})...")

    client = anthropic.AsyncAnthropic()

    with open(output_path, 'a', encoding='utf-8') as out:
        for i in range(0, len(posts), batch_size):
            batch = posts[i:i + batch_size]
            batch_num = i // batch_size + 1
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} posts)...", end=' ', flush=True)

            results = await analyze_batch(client, batch)

            for record in results:
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
            out.flush()

            scored = [r for r in results if r.get('software_opportunity_score', 0) >= 5]
            print(f"done ({len(scored)}/{len(batch)} scored ≥5)")

            if i + batch_size < len(posts):
                time.sleep(1)

    print(f"\nResults appended to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Analyze Reddit posts with Claude API')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE)
    parser.add_argument('--min-text', type=int, default=MIN_TEXT_LENGTH,
                        help='Minimum post text length to analyze')
    args = parser.parse_args()

    asyncio.run(run_analysis(batch_size=args.batch_size, min_text=args.min_text))


if __name__ == '__main__':
    main()
